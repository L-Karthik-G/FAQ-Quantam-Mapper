"""
Soft-candidate FAQ injection into SABRE's own trial pool (roadmap item 4).

Mechanism under test
--------------------
Tables 1-2 show that *hard-constraining* SABRE with the FAQ layout as `initial_layout`
usually makes routing worse: it removes SABRE's freedom to search its own layout space.
Qiskit's SabreLayout natively supports the softer alternative the roadmap hypothesises:
if the property-set field ``sabre_starting_layouts`` is a list of Layouts, those Layouts
are run as **additional layout trials in SABRE's own randomized trial pool**
(``partial_layouts`` in the Rust sabre_layout_and_routing call), alongside the usual
``layout_trials`` random starts; the trial with the fewest SWAPs wins. The FAQ layout is
therefore *one candidate among SABRE's trials* instead of a forced initial layout -- it
can only help or tie relative to default SABRE when SABRE's own search is weaker, and it
cannot force a worse-than-default outcome the way the hard constraint can.

This benchmark compares, per canonical task and seed:
    sabre_def      default SABRE (identical to the canonical Tables 1-2 arm)
    faq_sabre      FAQ layout hard-constrained (initial_layout) - canonical arm
    faq_soft_sabre FAQ layout injected as one extra trial (sabre_starting_layouts)

All three arms use Qiskit optimization_level=1 with layout_method="sabre",
routing_method="sabre" and the same seed_transpiler, so any difference vs sabre_def is
solely the FAQ candidate in the trial pool.

Usage (parallel over tasks via a process Pool is NOT used; this runner is serial over
tasks but each task's seeds are serial too -- launch multiple slices via
benchmark_eval_strided-style remainders if needed):

    uv run python benchmarks/benchmark_soft_sabre.py [--tasks all|subset] [--out ...]

Output:
    benchmarks/results/benchmark_soft_sabre_results.json    (per-task summaries)
    benchmarks/results/benchmark_soft_sabre_raw.json        (per-seed logs)
    benchmarks/results/benchmark_soft_sabre_significance.json (paired Wilcoxon + BH)
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
from benchmark_eval import (
    BENCHMARK_TASKS,
    SEEDS,
    compile_faq_pipeline,
    compile_sabre_def,
    get_hardware_topology,
)
from qiskit import QuantumCircuit, transpile
from qiskit.transpiler import CouplingMap
from qiskit.transpiler.basepasses import AnalysisPass
from qiskit.transpiler.layout import Layout
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

from qap_compiler.module_a_dag import DAGInteractionMatrixBuilder
from qap_compiler.module_b_hardware import HardwareMatrixBuilder
from qap_compiler.module_c_faq import AdaptiveFAQSolver

FAQ_START_MODE = "random"  # must match the canonical dataset (benchmark_eval.FAQ_START_MODE)


class _SetSabreStartingLayouts(AnalysisPass):
    """AnalysisPass that seeds SabreLayout's extra-trial pool from the property set.

    SabreLayout reads ``property_set["sabre_starting_layouts"]`` in its run(); this pass
    is prepended to the preset pass manager's layout stage so the list is present when
    SabreLayout executes. AnalysisPass semantics: the circuit dag is returned unchanged.
    """

    def __init__(self, layouts: List[Layout]):
        super().__init__()
        self.layouts = layouts

    def run(self, dag):
        self.property_set["sabre_starting_layouts"] = list(self.layouts)
        return dag


def _faq_layout(circuit: QuantumCircuit, M: int, coupling_list: List, errs: Dict, seed: int) -> Tuple[Layout, float]:
    """Runs the FAQ QAP pre-placement (identical to the canonical FAQ arm) and returns a
    Qiskit Layout plus the discrete polished QAP cost."""
    dag_builder = DAGInteractionMatrixBuilder(gamma=0.9)
    hw_builder = HardwareMatrixBuilder(alpha=1.0)
    faq_solver = AdaptiveFAQSolver(num_starts=5, start_mode=FAQ_START_MODE, enable_2opt=True, seed=seed)
    matrix_a = dag_builder.build_matrix(circuit)
    matrix_b = hw_builder.build_matrix(M, coupling_list, errs, is_directed=True)
    mapping, cost = faq_solver.solve(matrix_a, matrix_b)
    layout = Layout({circuit.qubits[i]: int(mapping[i]) for i in range(len(circuit.qubits))})
    return layout, cost


def compile_soft_faq_sabre(circuit: QuantumCircuit, M: int, coupling_list: List, errs: Dict, seed: int):
    """Default-o1 SABRE pipeline whose layout stage receives the FAQ layout as one
    additional trial in SabreLayout's own trial pool."""
    t0 = time.perf_counter()
    cm = CouplingMap(coupling_list)
    layout, cost = _faq_layout(circuit, M, coupling_list, errs, seed)
    prep_time = time.perf_counter() - t0

    pm = generate_preset_pass_manager(
        optimization_level=1,
        coupling_map=cm,
        layout_method="sabre",
        routing_method="sabre",
        seed_transpiler=seed,
    )
    # prepend the trial-seeding pass to the layout stage (property set flows through the
    # whole StagedPassManager run, so ordering before SetLayout/SabreLayout is fine)
    pm.layout._tasks.insert(0, [_SetSabreStartingLayouts([layout])])
    res = pm.run(circuit)
    total_time = time.perf_counter() - t0
    return res.count_ops().get("swap", 0), total_time, prep_time, res.depth(), cost


def run_one_task(task: Tuple, methods: Tuple[str, ...]) -> Tuple[Dict, List[Dict]]:
    """Serial runner over all seeds for one task and the requested methods."""
    arch_name, bench_key, bench_label, n_q, suite_type = task
    logs: List[Dict] = []
    M, coupling_list, errs = get_hardware_topology(arch_name)

    try:
        if suite_type == "mqt":
            qc = load_mqt_circuit(bench_key, n_q)
        else:
            qc = load_holdout_circuit(bench_key, n_q)
    except Exception as e:
        print(f"  [SKIP] {bench_label} N={n_q}: {e}", flush=True)
        return {}, []

    record: Dict = {"architecture": arch_name, "benchmark": bench_key, "benchmark_label": bench_label,
                    "qubits": n_q, "suite_type": suite_type, "num_physical_qubits": M}

    for method in methods:
        swaps, times, prep_times, statuses = [], [], [], []
        for seed in SEEDS:
            try:
                if method == "sabre_def":
                    sw, t, d = compile_sabre_def(qc, M, coupling_list, seed)
                    sw_out, t_out, prep_out, d_out = sw, t, None, d
                elif method == "faq_sabre":
                    sw_out, t_out, prep_out, d_out, _ = compile_faq_pipeline(qc, M, coupling_list, errs, "sabre", FAQ_START_MODE, seed)
                elif method == "faq_soft_sabre":
                    sw_out, t_out, prep_out, d_out, _ = compile_soft_faq_sabre(qc, M, coupling_list, errs, seed)
                else:
                    raise ValueError(f"unknown method {method}")
                swaps.append(int(sw_out))
                times.append(t_out)
                prep_times.append(prep_out)
                statuses.append("success")
                logs.append({"task": bench_label, "qubits": n_q, "arch": arch_name, "seed": seed,
                             "method": method, "status": "success", "swaps": int(sw_out),
                             "time_sec": t_out, "prep_time_sec": prep_out,
                             "depth": int(d_out), "failure_reason": "None"})
            except Exception as e:
                swaps.append(-1)
                times.append(None)
                prep_times.append(None)
                statuses.append("failed")
                logs.append({"task": bench_label, "qubits": n_q, "arch": arch_name, "seed": seed,
                             "method": method, "status": "failed", "swaps": None, "time_sec": None,
                             "prep_time_sec": None, "depth": None,
                             "failure_reason": "PASS_EXCEPTION", "error": str(e)})
        valid = [s for s in swaps if s >= 0]
        n_succ = len(valid)
        record[method] = {
            "n_total": len(swaps), "n_success": n_succ,
            "mean_swaps": float(np.mean(valid)) if valid else None,
            "std_swaps": float(np.std(valid)) if n_succ > 1 else 0.0,
            "ci95_swaps": float(_ci(valid)) if n_succ > 1 else 0.0,
        }
    return record, logs


def _ci(vals: List[int]) -> float:
    from scipy import stats
    sem = float(stats.sem(vals))
    return float(stats.t.ppf(0.975, df=len(vals) - 1) * sem)


def load_mqt_circuit(bench_key: str, n_qubits: int) -> QuantumCircuit:
    from mqt import bench as mqt_bench
    raw = mqt_bench.get_benchmark(bench_key, mqt_bench.BenchmarkLevel.ALG, n_qubits)
    return transpile(raw, basis_gates=["cx", "h", "rz", "x", "sx"], optimization_level=0)


def load_holdout_circuit(circuit_name: str, n_qubits: int) -> QuantumCircuit:
    import networkx as nx
    qc = QuantumCircuit(n_qubits)
    if circuit_name == "ripple_carry_adder":
        for i in range(n_qubits - 1):
            qc.h(i)
            qc.cx(i, i + 1)
            qc.rz(0.1, i + 1)
            qc.cx(i, i + 1)
    elif circuit_name == "qram_bucket_brigade":
        for i in range(n_qubits // 2):
            left, right = 2 * i + 1, 2 * i + 2
            if left < n_qubits:
                qc.cx(i, left)
            if right < n_qubits:
                qc.cx(i, right)
    elif circuit_name == "random_3_regular":
        G = nx.random_regular_graph(3, n_qubits, seed=12345)
        for u, v in G.edges():
            qc.cx(u, v)
            qc.rz(0.2, v)
            qc.cx(u, v)
    else:
        raise ValueError(circuit_name)
    return transpile(qc, basis_gates=["cx", "h", "rz", "x", "sx"], optimization_level=0)


# --- significance (paired Wilcoxon + BH), mirrors benchmarks/analyze_significance.py ---
def analyze_pairs(raw_logs: List[Dict], pairs: List[Tuple[str, str, str]]) -> Dict:
    from collections import OrderedDict, defaultdict

    from scipy import stats as sps
    cells: "OrderedDict[Tuple, Dict[str, List[int]]]" = OrderedDict()
    by_key = defaultdict(lambda: defaultdict(dict))
    for row in raw_logs:
        if row.get("status") != "success":
            continue
        by_key[(row["task"], int(row["qubits"]), row["arch"])][row["method"]][int(row["seed"])] = int(row["swaps"])
    for key in sorted(by_key.keys()):
        cells[key] = {m: [seed_map.get(s, np.nan) for s in sorted({s for mm in by_key[key].values() for s in mm})]
                      for m, seed_map in by_key[key].items()}

    rows = []
    pvals = []
    for key, methods in cells.items():
        task, qubits, arch = key
        rec = {"task": task, "qubits": qubits, "architecture": arch}
        for pname, base_m, faq_m in pairs:
            base, faq = methods.get(base_m, []), methods.get(faq_m, [])
            d = np.asarray(faq, float) - np.asarray(base, float)
            entry = {"base_mean": float(np.mean(base)) if base else None,
                     "faq_mean": float(np.mean(faq)) if faq else None,
                     "mean_diff_faq_minus_base": float(np.mean(d)) if len(d) else None}
            if len(d) == 0 or float(np.ptp(d)) == 0:
                entry.update({"test": "constant", "p_value": None, "note": "constant per-seed difference or missing"})
            else:
                res = sps.wilcoxon(d, zero_method="wilcox", alternative="two-sided")
                p = float(res.pvalue)
                entry.update({"test": "wilcoxon_signed_rank", "statistic": float(res.statistic),
                              "p_value": p, "n_zero_diffs_dropped": int(np.sum(d == 0))})
                pvals.append(p)
            rec[pname] = entry
        rows.append(rec)

    # BH across all tested comparisons
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
        for pname, _, _ in pairs:
            if rr[pname].get("p_value") is None:
                continue
            rr[pname]["q_value_bh"] = q[idx]
            rr[pname]["significant_bh"] = bool(q[idx] < 0.05)
            idx += 1
    return {"alpha": 0.05, "n_tested": len(pvals), "rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--methods", default="sabre_def,faq_sabre,faq_soft_sabre")
    ap.add_argument("--out", default=os.path.join(_BENCH_DIR, "results", "benchmark_soft_sabre"))
    ap.add_argument("--tasks", default="all", help="'all' or comma list of task indices")
    args = ap.parse_args()
    methods = tuple(args.methods.split(","))
    task_indices = list(range(len(BENCHMARK_TASKS))) if args.tasks == "all" else [int(i) for i in args.tasks.split(",")]

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    results, raw_logs = [], []
    t_start = time.time()
    for idx in task_indices:
        task = BENCHMARK_TASKS[idx]
        print(f"[task {idx}/{len(BENCHMARK_TASKS)}] {task[2]} N={task[3]} on {task[0]} ...", flush=True)
        rec, logs = run_one_task(task, methods)
        if rec:
            results.append(rec)
        raw_logs.extend(logs)
        print(f"   done in {time.time()-t_start:.0f}s", flush=True)

    with open(args.out + "_results.json", "w") as f:
        json.dump(results, f, indent=2)
    with open(args.out + "_raw.json", "w") as f:
        json.dump(raw_logs, f, indent=2)

    pairs = [("def_vs_soft", "sabre_def", "faq_soft_sabre"),
             ("hard_vs_soft", "faq_sabre", "faq_soft_sabre"),
             ("def_vs_hard", "sabre_def", "faq_sabre")]
    sig = analyze_pairs(raw_logs, [p for p in pairs if p[1] in methods and p[2] in methods])
    with open(args.out + "_significance.json", "w") as f:
        json.dump(sig, f, indent=2)
    print(f"\n=== SOFT-CANDIDATE SABRE BENCHMARK DONE ({time.time()-t_start:.0f}s) ===")
    for r in sorted(results, key=lambda x: (x["architecture"], x["qubits"])):
        print(f"{r['benchmark_label'][:34]:34s} {r['qubits']:3d} "
              f"def={r['sabre_def']['mean_swaps'] if 'sabre_def' in r else float('nan')} "
              f"hard={r.get('faq_sabre', {}).get('mean_swaps')} "
              f"soft={r.get('faq_soft_sabre', {}).get('mean_swaps')}")
    for rr in sig["rows"]:
        line = f"{rr['task'][:28]:28s} N={rr['qubits']:3d} "
        for pname in ("def_vs_soft", "hard_vs_soft", "def_vs_hard"):
            e = rr.get(pname)
            if e and e.get("p_value") is not None:
                line += f"| {pname}: mdd={e['mean_diff_faq_minus_base']:+.2f} q={e['q_value_bh']:.4f} sig={e['significant_bh']} "
        print(line)


if __name__ == "__main__":
    main()
