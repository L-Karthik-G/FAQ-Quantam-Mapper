"""
Paired-Seed Quantum Placement & Compilation Benchmark Suite (Phase 2 Hardened Edition)
Evaluates FAQ-Layout pre-placement against standard default routers:
  - SABRE Default vs. FAQ + SABRE
  - PyTKET Default vs. FAQ + PyTKET
  - QMAP Default vs. FAQ + QMAP
Includes explicit FailureReason Enums, raw per-seed result logs (benchmark_eval_raw_seeds.json),
unseen hand-crafted holdout circuits, and IBM FakeBrisbane hardware snapshots.
"""

import json
import os
import sys
import time
from enum import Enum
from typing import Dict, List, Tuple

# Ensure the repository root is importable regardless of the working directory
# (this file lives in <repo>/benchmarks/).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import networkx as nx
import numpy as np
from mqt import bench as mqt_bench
from mqt import qmap
from pytket.architecture import Architecture
from pytket.extensions.qiskit import qiskit_to_tk, tk_to_qiskit
from pytket.passes import PlacementPass, RoutingPass
from pytket.placement import GraphPlacement
from qiskit import QuantumCircuit, transpile
from qiskit.transpiler import CouplingMap
from scipy import stats

from qap_compiler.module_a_dag import DAGInteractionMatrixBuilder
from qap_compiler.module_b_hardware import HardwareMatrixBuilder, load_ibm_fake_brisbane_snapshot
from qap_compiler.module_c_faq import AdaptiveFAQSolver


class FailureReason(str, Enum):
    NONE = "None"
    TIMEOUT_EXCEEDED = "TIMEOUT_EXCEEDED"
    SUBGRAPH_EXHAUSTION = "SUBGRAPH_EXHAUSTION"
    ROUTING_UNSATISFIABLE = "ROUTING_UNSATISFIABLE"
    PASS_EXCEPTION = "PASS_EXCEPTION"


def compute_run_statistics(raw_swap_results: List[int], raw_statuses: List[str]) -> Dict:
    """
    Computes statistical metrics over paired runs with explicit failure accounting.
    """
    n_total = len(raw_swap_results)
    valid_swaps = [s for s in raw_swap_results if s >= 0]
    n_success = len(valid_swaps)
    n_failure = n_total - n_success
    success_rate = (n_success / n_total) * 100.0 if n_total > 0 else 0.0

    if n_success == 0:
        return {
            "n_total": n_total,
            "n_success": 0,
            "n_failure": n_failure,
            "success_rate": 0.0,
            "mean_swaps": None,
            "std_swaps": None,
            "ci95_swaps": None,
        }

    mean_val = float(np.mean(valid_swaps))
    std_val = float(np.std(valid_swaps)) if n_success > 1 else 0.0

    if n_success <= 1:
        ci_val = 0.0
    else:
        sem = float(stats.sem(valid_swaps))
        ci_val = float(stats.t.ppf(0.975, df=n_success - 1) * sem)

    return {
        "n_total": n_total,
        "n_success": n_success,
        "n_failure": n_failure,
        "success_rate": success_rate,
        "mean_swaps": mean_val,
        "std_swaps": std_val,
        "ci95_swaps": ci_val,
    }


def get_hardware_topology(arch_name: str) -> Tuple[int, List[Tuple[int, int]], Dict[Tuple[int, int], float]]:
    if arch_name == "IBM_Eagle_127_Brisbane":
        return load_ibm_fake_brisbane_snapshot()

    elif arch_name == "Rigetti_Grid_80":
        M = 80
        rng = np.random.default_rng(12345)
        grid_G = nx.convert_node_labels_to_integers(nx.grid_2d_graph(8, 10))
        rigetti_edges, rigetti_errors = [], {}
        for u, v in grid_G.edges():
            err = float(rng.uniform(0.01, 0.03))
            rigetti_edges.extend([(u, v), (v, u)])
            rigetti_errors[(u, v)] = err
            rigetti_errors[(v, u)] = err
        return M, rigetti_edges, rigetti_errors

    raise ValueError(f"Unknown architecture: {arch_name}")


def load_benchmark_circuit(bench_key: str, n_qubits: int) -> QuantumCircuit:
    raw_circ = mqt_bench.get_benchmark(bench_key, mqt_bench.BenchmarkLevel.ALG, n_qubits)
    decomp_circ = transpile(raw_circ, basis_gates=["cx", "h", "rz", "x", "sx"], optimization_level=0)
    return decomp_circ


def load_holdout_circuit(circuit_name: str, n_qubits: int) -> QuantumCircuit:
    """
    Constructs hand-crafted structural circuits outside MQT-Bench to test layout generalization.
    """
    qc = QuantumCircuit(n_qubits)

    if circuit_name == "ripple_carry_adder":
        # Hand-crafted linear chain interaction DAG
        for i in range(n_qubits - 1):
            qc.h(i)
            qc.cx(i, i + 1)
            qc.rz(0.1, i + 1)
            qc.cx(i, i + 1)

    elif circuit_name == "qram_bucket_brigade":
        # Hand-crafted binary tree interaction DAG
        for i in range(n_qubits // 2):
            left = 2 * i + 1
            right = 2 * i + 2
            if left < n_qubits:
                qc.cx(i, left)
            if right < n_qubits:
                qc.cx(i, right)

    elif circuit_name == "random_3_regular":
        # Hand-crafted 3-regular graph interaction DAG
        G = nx.random_regular_graph(3, n_qubits, seed=12345)
        for u, v in G.edges():
            qc.cx(u, v)
            qc.rz(0.2, v)
            qc.cx(u, v)

    else:
        raise ValueError(f"Unknown holdout circuit: {circuit_name}")

    return transpile(qc, basis_gates=["cx", "h", "rz", "x", "sx"], optimization_level=0)


def compile_sabre_def(circuit: QuantumCircuit, M: int, coupling_list: List, seed: int):
    t0 = time.perf_counter()
    cm = CouplingMap(coupling_list)
    res = transpile(
        circuit,
        coupling_map=cm,
        layout_method="sabre",
        routing_method="sabre",
        seed_transpiler=seed,
        optimization_level=1,
    )
    t = time.perf_counter() - t0
    swaps = res.count_ops().get("swap", 0)
    return swaps, t, res.depth()


def compile_tket_def(circuit: QuantumCircuit, M: int, coupling_list: List, seed: int):
    t0 = time.perf_counter()
    tk_circ = qiskit_to_tk(circuit)
    arc = Architecture(coupling_list)
    PlacementPass(GraphPlacement(arc)).apply(tk_circ)
    RoutingPass(arc).apply(tk_circ)
    res = tk_to_qiskit(tk_circ)
    t = time.perf_counter() - t0
    swaps = res.count_ops().get("swap", 0)
    return swaps, t, res.depth()


def compile_qmap_def(circuit: QuantumCircuit, M: int, coupling_list: List, seed: int):
    t0 = time.perf_counter()
    arch = qmap.Architecture(M, set(coupling_list))
    res = qmap.compile(circuit, arch, method="heuristic", initial_layout="identity")
    t = time.perf_counter() - t0
    swaps = getattr(res.output, "swaps", 0)
    depth = res.output.circuit_depth if hasattr(res.output, "circuit_depth") else 0
    return swaps, t, depth


def compile_faq_pipeline(circuit: QuantumCircuit, M: int, coupling_list: List, errs: Dict, router: str, start_mode: str, seed: int):
    t0 = time.perf_counter()
    N = circuit.num_qubits

    dag_builder = DAGInteractionMatrixBuilder(gamma=0.9)
    hw_builder = HardwareMatrixBuilder(alpha=1.0)
    faq_solver = AdaptiveFAQSolver(num_starts=5, start_mode=start_mode, enable_2opt=True, seed=seed)

    matrix_a = dag_builder.build_matrix(circuit)
    matrix_b = hw_builder.build_matrix(M, coupling_list, errs, is_directed=True)
    mapping, cost = faq_solver.solve(matrix_a, matrix_b)

    prep_time = time.perf_counter() - t0

    if router == "tket":
        qubit_indices = {q: i for i, q in enumerate(circuit.qubits)}
        clbit_indices = {c: i for i, c in enumerate(circuit.clbits)}
        seeded_circ = QuantumCircuit(M, circuit.num_clbits)
        for inst in circuit.data:
            q_args = [seeded_circ.qubits[mapping[qubit_indices[q]]] for q in inst.qubits]
            c_args = [seeded_circ.clbits[clbit_indices[c]] for c in inst.clbits]
            seeded_circ.append(inst.operation, q_args, c_args)
        tk_circ = qiskit_to_tk(seeded_circ)
        arc = Architecture(coupling_list)
        RoutingPass(arc).apply(tk_circ)
        res = tk_to_qiskit(tk_circ)
        total_time = time.perf_counter() - t0
        return res.count_ops().get("swap", 0), total_time, prep_time, res.depth(), cost

    elif router == "sabre":
        initial_layout_list = [mapping.get(i, i) for i in range(N)]
        cm = CouplingMap(coupling_list)
        res = transpile(
            circuit,
            coupling_map=cm,
            initial_layout=initial_layout_list,
            layout_method=None,
            routing_method="sabre",
            seed_transpiler=seed,
            optimization_level=1,
        )
        total_time = time.perf_counter() - t0
        return res.count_ops().get("swap", 0), total_time, prep_time, res.depth(), cost

    elif router == "qmap":
        arch = qmap.Architecture(M, set(coupling_list))
        res = qmap.compile(circuit, arch, method="heuristic", initial_layout=mapping)
        total_time = time.perf_counter() - t0
        swaps = getattr(res.output, "swaps", 0)
        depth = res.output.circuit_depth if hasattr(res.output, "circuit_depth") else 0
        return swaps, total_time, prep_time, depth, cost

    raise ValueError(f"Unknown router: {router}")


# --- Configuration shared by the serial and parallel drivers -----------------
SEEDS = list(range(20))  # K=20 paired seeds

BENCHMARK_TASKS = [
    # Standard MQT-Bench Suite
    ("IBM_Eagle_127_Brisbane", "grover", "Grover's Search", 8, "mqt"),
    ("IBM_Eagle_127_Brisbane", "grover", "Grover's Search", 10, "mqt"),
    ("IBM_Eagle_127_Brisbane", "grover", "Grover's Search", 12, "mqt"),
    ("IBM_Eagle_127_Brisbane", "vqe_real_amp", "VQE (RealAmplitudes)", 10, "mqt"),
    ("IBM_Eagle_127_Brisbane", "vqe_real_amp", "VQE (RealAmplitudes)", 20, "mqt"),
    ("IBM_Eagle_127_Brisbane", "vqe_real_amp", "VQE (RealAmplitudes)", 50, "mqt"),
    ("IBM_Eagle_127_Brisbane", "ghz", "GHZ State", 50, "mqt"),
    ("IBM_Eagle_127_Brisbane", "qft", "QFT", 20, "mqt"),
    ("IBM_Eagle_127_Brisbane", "qaoa", "QAOA", 10, "mqt"),
    ("IBM_Eagle_127_Brisbane", "qaoa", "QAOA", 20, "mqt"),

    ("Rigetti_Grid_80", "grover", "Grover's Search", 8, "mqt"),
    ("Rigetti_Grid_80", "grover", "Grover's Search", 10, "mqt"),
    ("Rigetti_Grid_80", "grover", "Grover's Search", 12, "mqt"),
    ("Rigetti_Grid_80", "vqe_real_amp", "VQE (RealAmplitudes)", 50, "mqt"),
    ("Rigetti_Grid_80", "qft", "QFT", 20, "mqt"),

    # Hand-Crafted Unseen Holdout Suite
    ("IBM_Eagle_127_Brisbane", "ripple_carry_adder", "Ripple-Carry Adder (Holdout)", 20, "holdout"),
    ("IBM_Eagle_127_Brisbane", "qram_bucket_brigade", "QRAM Decoder (Holdout)", 20, "holdout"),
    ("IBM_Eagle_127_Brisbane", "random_3_regular", "Random 3-Regular (Holdout)", 20, "holdout"),
    ("Rigetti_Grid_80", "ripple_carry_adder", "Ripple-Carry Adder (Holdout)", 20, "holdout"),
    ("Rigetti_Grid_80", "qram_bucket_brigade", "QRAM Decoder (Holdout)", 20, "holdout"),
]


def run_one_task(task: Tuple) -> Tuple[Dict, List[Dict]]:
    """Runs a single benchmark task across all K seeds and 4 router methods.

    Returns (task_record, seed_logs). task_record is None if the circuit could
    not be built (mirrors the serial runner's historical skip behaviour).
    Deterministic given the fixed seeds, so it is safe to call concurrently from
    multiple worker processes (each produces an identical result to the serial
    runner for the same task).
    """
    arch_name, bench_key, bench_label, n_q, suite_type = task
    logs: List[Dict] = []

    M, coupling_list, errs = get_hardware_topology(arch_name)

    try:
        if suite_type == "mqt":
            qc = load_benchmark_circuit(bench_key, n_q)
        else:
            qc = load_holdout_circuit(bench_key, n_q)
    except Exception as e:
        print(f"  [SKIP] Error loading circuit {bench_key} N={n_q}: {e}")
        return None, []

    task_record = {
        "architecture": arch_name,
        "benchmark": bench_key,
        "benchmark_label": bench_label,
        "qubits": n_q,
        "suite_type": suite_type,
        "num_physical_qubits": M,
        "original_gate_count": qc.size(),
        "original_depth": qc.depth(),
    }

    swaps_sabre_def, status_sabre_def = [], []
    swaps_faq_sabre, status_faq_sabre = [], []
    swaps_tket_def, status_tket_def = [], []
    swaps_faq_tket, status_faq_tket = [], []

    for seed in SEEDS:
        # 1. SABRE Default
        try:
            sw, t, d = compile_sabre_def(qc, M, coupling_list, seed)
            swaps_sabre_def.append(sw)
            status_sabre_def.append("success")
            logs.append({"task": bench_label, "qubits": n_q, "arch": arch_name, "seed": seed, "method": "sabre_def", "status": "success", "swaps": sw, "time_sec": t, "failure_reason": FailureReason.NONE})
        except Exception as e:
            swaps_sabre_def.append(-1)
            status_sabre_def.append("failed")
            logs.append({"task": bench_label, "qubits": n_q, "arch": arch_name, "seed": seed, "method": "sabre_def", "status": "failed", "swaps": None, "time_sec": None, "failure_reason": FailureReason.PASS_EXCEPTION, "error": str(e)})

        # 2. FAQ + SABRE
        try:
            sw, t, tp, d, cost = compile_faq_pipeline(qc, M, coupling_list, errs, "sabre", "gaussian", seed)
            swaps_faq_sabre.append(sw)
            status_faq_sabre.append("success")
            logs.append({"task": bench_label, "qubits": n_q, "arch": arch_name, "seed": seed, "method": "faq_sabre", "status": "success", "swaps": sw, "time_sec": t, "prep_time_sec": tp, "failure_reason": FailureReason.NONE})
        except Exception as e:
            swaps_faq_sabre.append(-1)
            status_faq_sabre.append("failed")
            logs.append({"task": bench_label, "qubits": n_q, "arch": arch_name, "seed": seed, "method": "faq_sabre", "status": "failed", "swaps": None, "time_sec": None, "failure_reason": FailureReason.PASS_EXCEPTION, "error": str(e)})

        # 3. PyTKET Default
        try:
            sw, t, d = compile_tket_def(qc, M, coupling_list, seed)
            swaps_tket_def.append(sw)
            status_tket_def.append("success")
            logs.append({"task": bench_label, "qubits": n_q, "arch": arch_name, "seed": seed, "method": "tket_def", "status": "success", "swaps": sw, "time_sec": t, "failure_reason": FailureReason.NONE})
        except Exception as e:
            swaps_tket_def.append(-1)
            status_tket_def.append("failed")
            logs.append({"task": bench_label, "qubits": n_q, "arch": arch_name, "seed": seed, "method": "tket_def", "status": "failed", "swaps": None, "time_sec": None, "failure_reason": FailureReason.PASS_EXCEPTION, "error": str(e)})

        # 4. FAQ + PyTKET
        try:
            sw, t, tp, d, cost = compile_faq_pipeline(qc, M, coupling_list, errs, "tket", "gaussian", seed)
            swaps_faq_tket.append(sw)
            status_faq_tket.append("success")
            logs.append({"task": bench_label, "qubits": n_q, "arch": arch_name, "seed": seed, "method": "faq_tket", "status": "success", "swaps": sw, "time_sec": t, "prep_time_sec": tp, "failure_reason": FailureReason.NONE})
        except Exception as e:
            swaps_faq_tket.append(-1)
            status_faq_tket.append("failed")
            logs.append({"task": bench_label, "qubits": n_q, "arch": arch_name, "seed": seed, "method": "faq_tket", "status": "failed", "swaps": None, "time_sec": None, "failure_reason": FailureReason.PASS_EXCEPTION, "error": str(e)})

    task_record["sabre_default"] = compute_run_statistics(swaps_sabre_def, status_sabre_def)
    task_record["faq_sabre"] = compute_run_statistics(swaps_faq_sabre, status_faq_sabre)
    task_record["tket_default"] = compute_run_statistics(swaps_tket_def, status_tket_def)
    task_record["faq_tket"] = compute_run_statistics(swaps_faq_tket, status_faq_tket)

    return task_record, logs


def main():
    all_results = []
    raw_seed_logs = []

    print(f"=== EVALUATING PHASE 2 HARDENED BENCHMARK SUITE ({len(BENCHMARK_TASKS)} tasks, K={len(SEEDS)} seeds) ===")

    for task_idx, task in enumerate(BENCHMARK_TASKS, 1):
        arch_name, _, bench_label, n_q, suite_type = task
        print(f"\n[{task_idx}/{len(BENCHMARK_TASKS)}] Running {bench_label} N={n_q} ({suite_type}) on {arch_name}...")

        task_record, logs = run_one_task(task)
        if task_record is None:
            continue

        all_results.append(task_record)
        raw_seed_logs.extend(logs)

        s_stats = task_record["faq_sabre"]
        t_stats = task_record["faq_tket"]
        print(f"  -> FAQ+SABRE: {s_stats['mean_swaps']} | FAQ+TKET: {t_stats['mean_swaps']} ± {t_stats['ci95_swaps']}")

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "benchmark_eval_results.json")
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)

    raw_path = os.path.join(out_dir, "benchmark_eval_raw_seeds.json")
    with open(raw_path, "w") as f:
        json.dump(raw_seed_logs, f, indent=2)

    print(f"\n=== BENCHMARK COMPLETE! Saved {len(all_results)} records to {out_path} and raw seed logs to {raw_path} ===")


if __name__ == "__main__":
    main()
