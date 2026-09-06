"""Stronger off-the-shelf router baselines (roadmap item 7).

Adds Qiskit optimization_level=2 and 3 default-sabre arms (the preset at level 3
additionally runs VF2PostLayout, the VF2-family layout refinement) and compares
them, per canonical task and seed (K=20), against the committed arms:

    sabre_def      - o1 default SABRE (canonical Tables 1-2)
    faq_tket       - FAQ layout -> PyTKET RoutingPass   (canonical)
    faq_soft_sabre - FAQ layout as one trial in SABRE's pool (soft-candidate report)
    sabre_o2 / sabre_o3 - NEW: stronger default routers, seeded identical

Question this answers: is FAQ pre-placement worth pursuing versus simply turning
up Qiskit's optimization level (which is what an off-the-shelf user would do)?

Run in slices (each writes its own partials), merge manually:
    uv run python benchmarks/benchmark_baselines.py --tasks 0,10,19 --out benchmarks/results/baseline_part0
then merge the partials and re-run the paired analysis over the merged raw log
(mirrors benchmark_dependence_a / benchmark_soft_sabre workflows).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, List, Tuple

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
if _BENCH_DIR not in sys.path:
    sys.path.insert(0, _BENCH_DIR)

import numpy as np
from benchmark_eval import BENCHMARK_TASKS, SEEDS, get_hardware_topology
from benchmark_soft_sabre import load_holdout_circuit, load_mqt_circuit
from qiskit import transpile
from qiskit.transpiler import CouplingMap


def compile_default(level: int, circuit, M, coupling_list, seed: int):
    t0 = time.perf_counter()
    cm = CouplingMap(coupling_list)
    res = transpile(circuit, coupling_map=cm, seed_transpiler=seed, optimization_level=level)
    t = time.perf_counter() - t0
    return res.count_ops().get("swap", 0), t, res.depth()


def run_one_task(task: Tuple) -> Tuple[Dict, List[Dict]]:
    arch_name, _, bench_label, n_q, suite_type = task
    M, coupling_list, errs = get_hardware_topology(arch_name)
    try:
        qc = load_mqt_circuit(task[1], n_q) if suite_type == "mqt" else load_holdout_circuit(task[1], n_q)
    except Exception as e:  # noqa: BLE001
        print(f"  [SKIP] {bench_label} N={n_q}: {e}", flush=True)
        return {}, []
    record: Dict = {"architecture": arch_name, "benchmark": bench_label, "qubits": n_q}
    logs: List[Dict] = []
    for method, level in (("sabre_o2", 2), ("sabre_o3", 3)):
        swaps, times, statuses = [], [], []
        for seed in SEEDS:
            try:
                sw, t, d = compile_default(level, qc, M, coupling_list, seed)
                swaps.append(int(sw))
                times.append(t)
                statuses.append("success")
                logs.append({"task": bench_label, "qubits": n_q, "arch": arch_name,
                             "seed": seed, "method": method, "status": "success",
                             "swaps": int(sw), "time_sec": t, "depth": int(d),
                             "failure_reason": "None"})
            except Exception as e:  # noqa: BLE001
                swaps.append(-1)
                times.append(None)
                statuses.append("failed")
                logs.append({"task": bench_label, "qubits": n_q, "arch": arch_name,
                             "seed": seed, "method": method, "status": "failed",
                             "swaps": None, "time_sec": None, "depth": None,
                             "failure_reason": "PASS_EXCEPTION", "error": str(e)})
        valid = [s for s in swaps if s >= 0]
        record[method] = {"n_total": len(swaps), "n_success": len(valid),
                          "mean_swaps": float(np.mean(valid)) if valid else None,
                          "std_swaps": float(np.std(valid)) if len(valid) > 1 else 0.0,
                          "ci95_swaps": float(_ci(valid)) if len(valid) > 1 else 0.0}
    return record, logs


def _ci(vals: List[int]) -> float:
    from scipy import stats
    sem = float(stats.sem(vals))
    return float(stats.t.ppf(0.975, df=len(vals) - 1) * sem)


def analyze_baselines(baseline_logs: List[Dict]) -> Dict:
    """Paired Wilcoxon of o2/o3 vs committed default/FAQ arms (per seed)."""
    from collections import defaultdict

    from scipy import stats as sps

    committed = []
    for fname in ("benchmark_eval_raw_seeds.json", "benchmark_soft_sabre_raw.json"):
        committed.extend(json.load(open(os.path.join(_BENCH_DIR, "results", fname))))
    by_key = defaultdict(dict)  # (method, task, qubits, arch) -> seed -> swaps
    for e in committed:
        if e.get("status") == "success":
            by_key[(e["method"], e["task"], int(e["qubits"]), e["arch"])][int(e["seed"])] = int(e["swaps"])
    for e in baseline_logs:
        if e.get("status") == "success":
            by_key[(e["method"], e["task"], int(e["qubits"]), e["arch"])][int(e["seed"])] = int(e["swaps"])

    # comparisons: o3 vs each relevant committed arm; o2 vs o1 default
    comparisons = [
        ("o3_vs_o1", "sabre_o3", "sabre_def"),
        ("o2_vs_o1", "sabre_o2", "sabre_def"),
        ("o3_vs_soft", "sabre_o3", "faq_soft_sabre"),
        ("o3_vs_tket", "sabre_o3", "faq_tket"),
        ("o2_vs_tket", "sabre_o2", "faq_tket"),
    ]
    rows, pvals = [], []
    cells = sorted({(t, q, a) for (_, t, q, a) in by_key})
    for task, qubits, arch in cells:
        rec = {"task": task, "qubits": qubits, "architecture": arch}
        for pname, base_m, faq_m in comparisons:
            base = by_key.get((base_m, task, qubits, arch), {})
            faq = by_key.get((faq_m, task, qubits, arch), {})
            common = sorted(set(base) & set(faq))
            # diff = new_arm - old_arm (negative => new arm better)
            d = np.asarray([by_key[(base_m, task, qubits, arch)][s] - by_key[(faq_m, task, qubits, arch)][s]
                            for s in common], float)
            entry = {"n_paired": len(common),
                     "mean_diff_new_minus_old": float(np.mean(d)) if len(d) else None,
                     "old_mean": float(np.mean([base[s] for s in common])) if common else None,
                     "new_mean": float(np.mean([faq[s] for s in common])) if common else None}
            if len(d) and float(np.ptp(d)) > 0:
                res = sps.wilcoxon(d, zero_method="wilcox", alternative="two-sided")
                p = float(res.pvalue)
                entry.update({"p_value": p, "statistic": float(res.statistic)})
                pvals.append(p)
            else:
                entry.update({"p_value": None})
            rec[pname] = entry
        rows.append(rec)

    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    q = [0.0] * len(pvals)
    prev = float("inf")
    for pos in range(len(pvals) - 1, -1, -1):
        i = order[pos]
        qv = len(pvals) * pvals[i] / (pos + 1)
        q[i] = min(qv, prev)
        prev = q[i]
    idx = 0
    for rr in rows:
        for pname, _, _ in comparisons:
            if rr[pname].get("p_value") is None:
                continue
            rr[pname]["q_value_bh"] = q[idx]
            rr[pname]["significant_bh"] = bool(q[idx] < 0.05)
            idx += 1
    return {"alpha": 0.05, "n_tested": len(pvals), "rows": rows, "comparisons": comparisons}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="all")
    ap.add_argument("--out", default=os.path.join(_BENCH_DIR, "results", "baseline_part"))
    args = ap.parse_args()
    task_indices = list(range(len(BENCHMARK_TASKS))) if args.tasks == "all" \
        else [int(i) for i in args.tasks.split(",")]
    results, raw_logs = [], []
    t_start = time.time()
    for idx in task_indices:
        task = BENCHMARK_TASKS[idx]
        print(f"[task {idx}] {task[2]} N={task[3]} ...", flush=True)
        rec, logs = run_one_task(task)
        if rec:
            results.append((idx, rec))
        raw_logs.extend(logs)
        print(f"   done ({time.time() - t_start:.0f}s)", flush=True)
    with open(args.out + "_results.json", "w") as f:
        json.dump(results, f, indent=2)
    with open(args.out + "_raw.json", "w") as f:
        json.dump(raw_logs, f, indent=2)
    sig = analyze_baselines(raw_logs)
    with open(args.out + "_significance.json", "w") as f:
        json.dump(sig, f, indent=2)
    print(f"\n=== DONE ({time.time() - t_start:.0f}s) -> {args.out}_*.json ===")


if __name__ == "__main__":
    main()
