"""Benchmark FAQ pre-placement with the transitive-dependence-weighted matrix A (variant A2).

Roadmap item 5: the current QAP objective (A = raw time-decayed interaction frequency)
has no established relationship to the router's SWAP count, unlike dependence-aware
lower bounds in the literature. This experiment A/Bs the two interaction matrices on the
*downstream* routing metric, holding every other element fixed:

    A0 (baseline)  - DAGInteractionMatrixBuilder.build_matrix
    A2             - build_matrix_dependence_weighted (each two-qubit gate scaled by
                     (1 + dependence depth d(g)) in addition to the temporal decay)

For every canonical task and seed (K=20, identical FAQ random multi-start + 2-opt,
same seeds and routers as the committed canonical datasets) we compile two arms:
  faq_tket_a2  - FAQ layout (A2) embedded into PyTKET RoutingPass  [vs committed A0: faq_tket]
  faq_soft_a2  - FAQ layout (A2) as one extra trial in SABRE's pool  [vs committed A0: faq_soft_sabre]
The A0 counterparts are already committed (benchmark_eval_raw_seeds.json method
faq_tket; benchmark_soft_sabre_raw.json method faq_soft_sabre) with identical seeds, so
the paired comparison is exact.

Run in slices to parallelise (each writes its own partials):
  uv run python benchmarks/benchmark_dependence_a.py --tasks 0,10,19 --out benchmarks/results/dep_a_part0
then merge the partials and run benchmarks/analyze_dependence_a.py --merge 6.
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
from pytket.architecture import Architecture
from pytket.extensions.qiskit import qiskit_to_tk, tk_to_qiskit
from pytket.passes import RoutingPass
from qiskit import QuantumCircuit, transpile
from qiskit.transpiler import CouplingMap
from qiskit.transpiler.basepasses import AnalysisPass
from qiskit.transpiler.layout import Layout
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

from qap_compiler.module_a_dag import DAGInteractionMatrixBuilder
from qap_compiler.module_b_hardware import HardwareMatrixBuilder
from qap_compiler.module_c_faq import AdaptiveFAQSolver


class _SetSabreStartingLayouts(AnalysisPass):
    """Seeds SabreLayout's extra-trial pool (identical to benchmark_soft_sabre)."""

    def __init__(self, layouts: List[Layout]):
        super().__init__()
        self.layouts = layouts

    def run(self, dag):
        self.property_set["sabre_starting_layouts"] = list(self.layouts)
        return dag


def faq_mapping_a2(circuit: QuantumCircuit, M: int, coupling_list: List, errs: Dict,
                   seed: int, weighted: bool):
    """FAQ solve with A0 (weighted=False) or A2 (weighted=True). Returns (mapping, cost)."""
    dag_builder = DAGInteractionMatrixBuilder(gamma=0.9)
    hw_builder = HardwareMatrixBuilder(alpha=1.0)
    solver = AdaptiveFAQSolver(num_starts=5, start_mode="random", enable_2opt=True, seed=seed)
    matrix_a = (dag_builder.build_matrix_dependence_weighted(circuit) if weighted
                else dag_builder.build_matrix(circuit))
    matrix_b = hw_builder.build_matrix(M, coupling_list, errs, is_directed=True)
    return solver.solve(matrix_a, matrix_b)


def compile_tket_a2(circuit: QuantumCircuit, M: int, coupling_list: List, errs: Dict,
                    seed: int, weighted: bool):
    """FAQ-embed + PyTKET RoutingPass (mirrors benchmark_eval compile_faq_pipeline/tket)."""
    t0 = time.perf_counter()
    mapping, cost = faq_mapping_a2(circuit, M, coupling_list, errs, seed, weighted)
    prep_time = time.perf_counter() - t0
    qubit_indices = {q: i for i, q in enumerate(circuit.qubits)}
    clbit_indices = {c: i for i, c in enumerate(circuit.clbits)}
    seeded = QuantumCircuit(M, circuit.num_clbits)
    for inst in circuit.data:
        q_args = [seeded.qubits[mapping[qubit_indices[q]]] for q in inst.qubits]
        c_args = [seeded.clbits[clbit_indices[c]] for c in inst.clbits]
        seeded.append(inst.operation, q_args, c_args)
    tk_circ = qiskit_to_tk(seeded)
    arc = Architecture(coupling_list)
    RoutingPass(arc).apply(tk_circ)
    res = tk_to_qiskit(tk_circ)
    total_time = time.perf_counter() - t0
    return res.count_ops().get("swap", 0), total_time, prep_time, res.depth(), cost


def compile_soft_a2(circuit: QuantumCircuit, M: int, coupling_list: List, errs: Dict,
                    seed: int, weighted: bool):
    """FAQ-as-one-trial SABRE (mirrors benchmark_soft_sabre compile_soft_faq_sabre)."""
    t0 = time.perf_counter()
    cm = CouplingMap(coupling_list)
    mapping, cost = faq_mapping_a2(circuit, M, coupling_list, errs, seed, weighted)
    prep_time = time.perf_counter() - t0
    layout = Layout({circuit.qubits[i]: int(mapping[i]) for i in range(len(circuit.qubits))})
    pm = generate_preset_pass_manager(optimization_level=1, coupling_map=cm,
                                      layout_method="sabre", routing_method="sabre",
                                      seed_transpiler=seed)
    pm.layout._tasks.insert(0, [_SetSabreStartingLayouts([layout])])
    res = pm.run(circuit)
    total_time = time.perf_counter() - t0
    return res.count_ops().get("swap", 0), total_time, prep_time, res.depth(), cost


def load_circuit(task: Tuple) -> QuantumCircuit:
    arch, bench_key, _, n_q, suite_type = task
    if suite_type == "mqt":
        from mqt import bench as mqt_bench
        raw = mqt_bench.get_benchmark(bench_key, mqt_bench.BenchmarkLevel.ALG, n_q)
    else:
        import networkx as nx
        qc = QuantumCircuit(n_q)
        if bench_key == "ripple_carry_adder":
            for i in range(n_q - 1):
                qc.h(i)
                qc.cx(i, i + 1)
                qc.rz(0.1, i + 1)
                qc.cx(i, i + 1)
        elif bench_key == "qram_bucket_brigade":
            for i in range(n_q // 2):
                lft, rgt = 2 * i + 1, 2 * i + 2
                if lft < n_q:
                    qc.cx(i, lft)
                if rgt < n_q:
                    qc.cx(i, rgt)
        elif bench_key == "random_3_regular":
            G = nx.random_regular_graph(3, n_q, seed=12345)
            for u, v in G.edges():
                qc.cx(u, v)
                qc.rz(0.2, v)
                qc.cx(u, v)
        else:
            raise ValueError(bench_key)
        return transpile(qc, basis_gates=["cx", "h", "rz", "x", "sx"], optimization_level=0)
    return transpile(raw, basis_gates=["cx", "h", "rz", "x", "sx"], optimization_level=0)


def run_one_task(task: Tuple) -> Tuple[Dict, List[Dict]]:
    arch_name, _, bench_label, n_q, suite_type = task
    M, coupling_list, errs = get_hardware_topology(arch_name)
    try:
        qc = load_circuit(task)
    except Exception as e:  # noqa: BLE001
        print(f"  [SKIP] {bench_label} N={n_q}: {e}", flush=True)
        return {}, []
    record: Dict = {"architecture": arch_name, "benchmark": bench_label, "qubits": n_q}
    logs: List[Dict] = []
    for method in ("faq_tket_a2", "faq_soft_a2"):
        swaps, times, preps, statuses = [], [], [], []
        for seed in SEEDS:
            try:
                if method == "faq_tket_a2":
                    sw, t, tp, d, cost = compile_tket_a2(qc, M, coupling_list, errs, seed, True)
                else:
                    sw, t, tp, d, cost = compile_soft_a2(qc, M, coupling_list, errs, seed, True)
                swaps.append(int(sw))
                times.append(t)
                preps.append(tp)
                statuses.append("success")
                logs.append({"task": bench_label, "qubits": n_q, "arch": arch_name,
                             "seed": seed, "method": method, "status": "success",
                             "swaps": int(sw), "time_sec": t, "prep_time_sec": tp,
                             "depth": int(d), "failure_reason": "None"})
            except Exception as e:  # noqa: BLE001
                swaps.append(-1)
                times.append(None)
                preps.append(None)
                statuses.append("failed")
                logs.append({"task": bench_label, "qubits": n_q, "arch": arch_name,
                             "seed": seed, "method": method, "status": "failed",
                             "swaps": None, "time_sec": None, "prep_time_sec": None,
                             "depth": None, "failure_reason": "PASS_EXCEPTION", "error": str(e)})
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


def analyze_a2_vs_a0(a2_logs: List[Dict]) -> Dict:
    """Paired Wilcoxon (A2 - A0 per seed) per (task, qubits, router); A0 values come from the
    committed canonical logs that share seeds and every other setting."""
    import json as _json
    from collections import defaultdict

    from scipy import stats as sps

    canon = _json.load(open(os.path.join(_BENCH_DIR, "results", "benchmark_eval_raw_seeds.json")))
    soft = _json.load(open(os.path.join(_BENCH_DIR, "results", "benchmark_soft_sabre_raw.json")))
    a0_by = defaultdict(dict)  # (method, task, qubits, arch) -> seed -> swaps
    for e in canon + soft:
        if e.get("method") in ("faq_tket", "faq_soft_sabre") and e.get("status") == "success":
            a0_by[(e["method"], e["task"], int(e["qubits"]), e["arch"])][int(e["seed"])] = int(e["swaps"])
    a2_by = defaultdict(dict)
    for e in a2_logs:
        if e.get("status") == "success":
            a2_by[(e["method"], e["task"], int(e["qubits"]), e["arch"])][int(e["seed"])] = int(e["swaps"])

    mapping = {"faq_tket_a2": ("faq_tket", "tket"), "faq_soft_a2": ("faq_soft_sabre", "sabre_soft")}
    rows, pvals = [], []
    for (method, task, qubits, arch), seeds in sorted(a2_by.items()):
        a0_m, pair = mapping[method]
        a0 = a0_by.get((a0_m, task, qubits, arch), {})
        common = sorted(set(seeds) & set(a0))
        d = np.asarray([a2_by[(method, task, qubits, arch)][s] - a0[s] for s in common], float)
        rec = {"task": task, "qubits": qubits, "architecture": arch, "pair": pair,
               "n_paired": len(common),
               "mean_diff_a2_minus_a0": float(np.mean(d)) if len(d) else None}
        if len(d) and float(np.ptp(d)) > 0:
            res = sps.wilcoxon(d, zero_method="wilcox", alternative="two-sided")
            p = float(res.pvalue)
            rec.update({"p_value": p, "statistic": float(res.statistic)})
            pvals.append(p)
        else:
            rec.update({"p_value": None, "note": "constant difference"})
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
        if rr.get("p_value") is None:
            continue
        rr["q_value_bh"] = q[idx]
        rr["significant_bh"] = bool(q[idx] < 0.05)
        idx += 1
    return {"alpha": 0.05, "n_tested": len(pvals), "rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="all")
    ap.add_argument("--out", default=os.path.join(_BENCH_DIR, "results", "dep_a_part"))
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
    sig = analyze_a2_vs_a0(raw_logs)
    with open(args.out + "_significance.json", "w") as f:
        json.dump(sig, f, indent=2)
    print(f"\n=== DONE ({time.time() - t_start:.0f}s) -> {args.out}_*.json ===")


if __name__ == "__main__":
    main()
