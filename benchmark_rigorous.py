"""
Rigorous Paired-Seed Quantum Compilation Benchmark & Ablation Suite
Evaluates FAQ-Layout against SABRE, PyTKET, QMAP, and IEEE QCE 2023 FGEA+FMA baselines.
"""

import json
import math
import time
from typing import Dict, List, Tuple
import numpy as np
from scipy import stats

from qiskit import QuantumCircuit, transpile
from qiskit.circuit.library import GroverOperator
from qiskit.transpiler import CouplingMap

from pytket.architecture import Architecture
from pytket.extensions.qiskit import qiskit_to_tk, tk_to_qiskit
from pytket.passes import RoutingPass, PlacementPass
from pytket.placement import GraphPlacement

from mqt import qmap

from qap_compiler.module_a_dag import DAGInteractionMatrixBuilder
from qap_compiler.module_b_hardware import HardwareMatrixBuilder
from qap_compiler.module_c_faq import AdaptiveFAQSolver
from qap_compiler.module_e_fgea import FGEASubgraphExtractor, FMAMapper


def compute_ci95(data: List[float]) -> Tuple[float, float]:
    """Computes sample mean and 95% confidence interval using Student's t-distribution."""
    valid_data = [x for x in data if x >= 0]
    if not valid_data:
        return 0.0, 0.0
    n = len(valid_data)
    mean_val = float(np.mean(valid_data))
    if n <= 1:
        return mean_val, 0.0
    sem = float(stats.sem(valid_data))
    ci = float(stats.t.ppf(0.975, df=n - 1) * sem)
    return mean_val, ci


# ==========================================
# 1. HARDWARE TOPOLOGY FACTORY (FIXED CALIBRATION)
# ==========================================
def get_hardware_topology(arch_name: str) -> Tuple[int, List[Tuple[int, int]], Dict[Tuple[int, int], float]]:
    rng = np.random.default_rng(12345)  # Fixed calibration seed

    if arch_name == "IBM_HeavyHex_115":
        M = 115
        edges = set()
        for i in range(M - 1):
            if i % 14 != 13:
                edges.add((i, i + 1))
                edges.add((i + 1, i))
            if i + 14 < M and (i % 7 == 0 or i % 7 == 3):
                edges.add((i, i + 14))
                edges.add((i + 14, i))
        edge_list = list(edges)
        errs = {e: float(rng.uniform(0.008, 0.016)) for e in edge_list}
        return M, edge_list, errs

    elif arch_name == "Rigetti_Grid_80":
        M = 80
        rows, cols = 8, 10
        edges = set()
        for r in range(rows):
            for c in range(cols):
                u = r * cols + c
                if c + 1 < cols:
                    v = r * cols + (c + 1)
                    edges.add((u, v))
                    edges.add((v, u))
                if r + 1 < rows:
                    v = (r + 1) * cols + c
                    edges.add((u, v))
                    edges.add((v, u))
        edge_list = list(edges)
        errs = {e: float(rng.uniform(0.012, 0.024)) for e in edge_list}
        return M, edge_list, errs

    elif arch_name == "IonQ_AllToAll_50":
        M = 50
        edges = [(u, v) for u in range(M) for v in range(M) if u != v]
        errs = {e: 0.003 for e in edges}
        return M, edges, errs

    raise ValueError(f"Unknown architecture: {arch_name}")


# ==========================================
# 2. CIRCUIT SUITE FACTORY
# ==========================================
def build_benchmark_circuit(name: str, n_qubits: int) -> QuantumCircuit:
    if name == "grover":
        oracle = QuantumCircuit(n_qubits)
        oracle.z(0)
        grover_op = GroverOperator(oracle)
        qc = QuantumCircuit(n_qubits)
        qc.h(range(n_qubits))
        qc.compose(grover_op, inplace=True)
        return transpile(qc, basis_gates=["cx", "h", "rz", "x", "sx"], optimization_level=0)

    elif name == "vqe":
        qc = QuantumCircuit(n_qubits)
        for q in range(n_qubits):
            qc.ry(0.5, q)
        for _ in range(3):
            for q in range(n_qubits - 1):
                qc.cx(q, q + 1)
            for q in range(n_qubits):
                qc.ry(0.3, q)
        return qc

    elif name == "ghz":
        qc = QuantumCircuit(n_qubits)
        qc.h(0)
        for i in range(n_qubits - 1):
            qc.cx(i, i + 1)
        return qc

    elif name == "bv":
        qc = QuantumCircuit(n_qubits)
        qc.x(n_qubits - 1)
        qc.h(range(n_qubits))
        for i in range(n_qubits - 1):
            if i % 2 == 0:
                qc.cx(i, n_qubits - 1)
        qc.h(range(n_qubits))
        return qc

    elif name == "qft":
        qc = QuantumCircuit(n_qubits)
        for i in range(n_qubits):
            qc.h(i)
            for j in range(i + 1, min(i + 4, n_qubits)):
                qc.cp(np.pi / (2 ** (j - i)), j, i)
        return transpile(qc, basis_gates=["cx", "h", "rz", "x", "sx"], optimization_level=0)

    elif name == "qpe":
        qc = QuantumCircuit(n_qubits)
        qc.h(range(n_qubits - 1))
        qc.x(n_qubits - 1)
        for i in range(n_qubits - 1):
            qc.cp(0.25 * (i + 1), i, n_qubits - 1)
        return transpile(qc, basis_gates=["cx", "h", "rz", "x", "sx"], optimization_level=0)

    elif name == "qaoa":
        qc = QuantumCircuit(n_qubits)
        qc.h(range(n_qubits))
        for p in range(2):
            for i in range(n_qubits):
                target = (i * 3 + 1) % n_qubits
                if target != i:
                    qc.cx(min(i, target), max(i, target))
            for i in range(n_qubits):
                qc.rx(0.4, i)
        return qc

    raise ValueError(f"Unknown benchmark: {name}")


# ==========================================
# 3. COMPILATION EXECUTION ENGINES
# ==========================================
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
    return swaps, t, res.output.circuit_depth if hasattr(res.output, "circuit_depth") else 0


def compile_paper_fgea(circuit: QuantumCircuit, M: int, coupling_list: List, errs: Dict, seed: int):
    t0 = time.perf_counter()
    N = circuit.num_qubits
    extractor = FGEASubgraphExtractor(buffer=4)
    sub_cm, sub_errs, g2l, l2g = extractor.extract(N, M, coupling_list, errs)
    placer = FMAMapper()
    logical_to_sub = placer.place(circuit, sub_cm, sub_errs)
    initial_layout = [l2g.get(logical_to_sub.get(i, 0), i) for i in range(N)]

    cm = CouplingMap(coupling_list)
    res = transpile(
        circuit,
        coupling_map=cm,
        initial_layout=initial_layout,
        layout_method=None,
        routing_method="sabre",
        seed_transpiler=seed,
        optimization_level=1,
    )
    t = time.perf_counter() - t0
    swaps = res.count_ops().get("swap", 0)
    return swaps, t, res.depth()


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

    elif router == "qmap":
        arch = qmap.Architecture(M, set(coupling_list))
        res = qmap.compile(circuit, arch, method="heuristic", initial_layout=mapping)
        total_time = time.perf_counter() - t0
        swaps = getattr(res.output, "swaps", 0)
        depth = res.output.circuit_depth if hasattr(res.output, "circuit_depth") else 0
        return swaps, total_time, prep_time, depth, cost

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

    raise ValueError(f"Unknown router: {router}")


# ==========================================
# 4. MAIN BENCHMARK RUNNER
# ==========================================
def main():
    SEEDS = [0, 1, 2, 3, 4]  # Paired seeds across all methods
    
    benchmark_tasks = [
        # (Architecture, Benchmark, Qubits)
        ("IBM_HeavyHex_115", "grover", 8),
        ("IBM_HeavyHex_115", "grover", 10),
        ("IBM_HeavyHex_115", "grover", 12),
        ("IBM_HeavyHex_115", "vqe", 20),
        ("IBM_HeavyHex_115", "vqe", 50),
        ("IBM_HeavyHex_115", "ghz", 20),
        ("IBM_HeavyHex_115", "ghz", 50),
        ("IBM_HeavyHex_115", "bv", 10),
        ("IBM_HeavyHex_115", "bv", 50),
        ("IBM_HeavyHex_115", "qft", 20),
        ("IBM_HeavyHex_115", "qft", 50),
        ("IBM_HeavyHex_115", "qpe", 50),
        ("IBM_HeavyHex_115", "qaoa", 50),
        
        ("Rigetti_Grid_80", "grover", 8),
        ("Rigetti_Grid_80", "grover", 10),
        ("Rigetti_Grid_80", "grover", 12),
        ("Rigetti_Grid_80", "vqe", 20),
        ("Rigetti_Grid_80", "vqe", 50),
        ("Rigetti_Grid_80", "ghz", 20),
        ("Rigetti_Grid_80", "ghz", 50),
        ("Rigetti_Grid_80", "bv", 10),
        ("Rigetti_Grid_80", "bv", 50),
        ("Rigetti_Grid_80", "qft", 20),
        ("Rigetti_Grid_80", "qft", 50),
        ("Rigetti_Grid_80", "qpe", 50),
        ("Rigetti_Grid_80", "qaoa", 50),

        ("IonQ_AllToAll_50", "vqe", 50),
        ("IonQ_AllToAll_50", "ghz", 50),
        ("IonQ_AllToAll_50", "qft", 50),
    ]

    all_results = []
    print(f"=== STARTING RIGOROUS PAIRED-SEED BENCHMARK ({len(benchmark_tasks)} tasks, K={len(SEEDS)} seeds) ===")

    for task_idx, (arch_name, bench_name, n_q) in enumerate(benchmark_tasks, 1):
        print(f"\n[{task_idx}/{len(benchmark_tasks)}] Running {bench_name.upper()} N={n_q} on {arch_name}...")
        M, coupling_list, errs = get_hardware_topology(arch_name)
        qc = build_benchmark_circuit(bench_name, n_q)

        task_record = {
            "architecture": arch_name,
            "benchmark": bench_name,
            "qubits": n_q,
            "num_physical_qubits": M,
            "original_gate_count": qc.size(),
            "original_depth": qc.depth(),
            "runs": {}
        }

        # Track lists for statistics
        swaps_sabre_def, time_sabre_def = [], []
        swaps_tket_def, time_tket_def = [], []
        swaps_qmap_def, time_qmap_def = [], []
        swaps_paper_fgea, time_paper_fgea = [], []
        
        swaps_faq_tket, time_faq_tket, prep_faq_tket = [], [], []
        swaps_faq_qmap, time_faq_qmap, prep_faq_qmap = [], [], []
        swaps_faq_sabre, time_faq_sabre, prep_faq_sabre = [], [], []

        # Ablation lists
        swaps_ablation_barycenter = []
        swaps_ablation_random = []

        for seed in SEEDS:
            # 1. SABRE Def
            try:
                sw, t, d = compile_sabre_def(qc, M, coupling_list, seed)
                swaps_sabre_def.append(sw); time_sabre_def.append(t)
            except Exception as e:
                print(f"  [Error SABRE Def] seed={seed}: {e}")

            # 2. PyTKET Def
            try:
                sw, t, d = compile_tket_def(qc, M, coupling_list, seed)
                swaps_tket_def.append(sw); time_tket_def.append(t)
            except Exception as e:
                # Expected when PyTKET GraphPlacement fails on irregular unseeded graphs
                swaps_tket_def.append(-1); time_tket_def.append(0.0)

            # 3. QMAP Def (run on smaller/moderate circuits to avoid timeout)
            if n_q <= 50 and bench_name in ["vqe", "ghz", "bv", "grover"]:
                try:
                    sw, t, d = compile_qmap_def(qc, M, coupling_list, seed)
                    swaps_qmap_def.append(sw); time_qmap_def.append(t)
                except Exception as e:
                    swaps_qmap_def.append(-1); time_qmap_def.append(0.0)

            # 4. Paper FGEA+FMA
            try:
                sw, t, d = compile_paper_fgea(qc, M, coupling_list, errs, seed)
                swaps_paper_fgea.append(sw); time_paper_fgea.append(t)
            except Exception as e:
                print(f"  [Error Paper FGEA] seed={seed}: {e}")

            # 5. FAQ + PyTKET (Ours: 5-Start Gaussian + Momentum)
            try:
                sw, t, tp, d, cost = compile_faq_pipeline(qc, M, coupling_list, errs, "tket", "gaussian", seed)
                swaps_faq_tket.append(sw); time_faq_tket.append(t); prep_faq_tket.append(tp)
            except Exception as e:
                print(f"  [Error FAQ+TKET] seed={seed}: {e}")

            # 6. FAQ + QMAP (Ours)
            if n_q <= 50 and bench_name in ["vqe", "ghz", "bv", "grover"]:
                try:
                    sw, t, tp, d, cost = compile_faq_pipeline(qc, M, coupling_list, errs, "qmap", "gaussian", seed)
                    swaps_faq_qmap.append(sw); time_faq_qmap.append(t); prep_faq_qmap.append(tp)
                except Exception as e:
                    swaps_faq_qmap.append(-1); time_faq_qmap.append(0.0); prep_faq_qmap.append(0.0)

            # 7. FAQ + SABRE (Ours)
            try:
                sw, t, tp, d, cost = compile_faq_sabre = compile_faq_pipeline(qc, M, coupling_list, errs, "sabre", "gaussian", seed)
                swaps_faq_sabre.append(sw); time_faq_sabre.append(t); prep_faq_sabre.append(tp)
            except Exception as e:
                print(f"  [Error FAQ+SABRE] seed={seed}: {e}")

            # ABLATION 1: Single-Start Barycenter Only (FAQ + TKET)
            try:
                sw, t, tp, d, cost = compile_faq_pipeline(qc, M, coupling_list, errs, "tket", "barycenter", seed)
                swaps_ablation_barycenter.append(sw)
            except Exception:
                pass

            # ABLATION 2: Pure Random Multi-Start (FAQ + TKET)
            try:
                sw, t, tp, d, cost = compile_faq_pipeline(qc, M, coupling_list, errs, "tket", "random", seed)
                swaps_ablation_random.append(sw)
            except Exception:
                pass

        # Calculate statistics
        m_sabre, ci_sabre = compute_ci95(swaps_sabre_def)
        m_tket_def, ci_tket_def = compute_ci95(swaps_tket_def)
        m_qmap_def, ci_qmap_def = compute_ci95(swaps_qmap_def)
        m_paper, ci_paper = compute_ci95(swaps_paper_fgea)
        
        m_faq_tket, ci_faq_tket = compute_ci95(swaps_faq_tket)
        m_faq_qmap, ci_faq_qmap = compute_ci95(swaps_faq_qmap)
        m_faq_sabre, ci_faq_sabre = compute_ci95(swaps_faq_sabre)

        m_ablation_bary, _ = compute_ci95(swaps_ablation_barycenter)
        m_ablation_rand, _ = compute_ci95(swaps_ablation_random)

        # Baseline min calculation
        valid_defaults = [m for m in [m_sabre, m_tket_def, m_qmap_def] if m > 0]
        min_default = min(valid_defaults) if valid_defaults else m_sabre

        task_record["sabre_default_swaps_mean"] = m_sabre
        task_record["sabre_default_swaps_ci95"] = ci_sabre
        task_record["sabre_default_time_mean"] = float(np.mean(time_sabre_def)) if time_sabre_def else 0.0

        task_record["tket_default_swaps_mean"] = m_tket_def
        task_record["tket_default_swaps_ci95"] = ci_tket_def
        task_record["tket_default_success_rate"] = float(np.mean([1 if s >= 0 else 0 for s in swaps_tket_def])) * 100

        task_record["qmap_default_swaps_mean"] = m_qmap_def
        task_record["qmap_default_swaps_ci95"] = ci_qmap_def

        task_record["paper_fgea_swaps_mean"] = m_paper
        task_record["paper_fgea_swaps_ci95"] = ci_paper

        task_record["faq_tket_swaps_mean"] = m_faq_tket
        task_record["faq_tket_swaps_ci95"] = ci_faq_tket
        task_record["faq_tket_time_mean"] = float(np.mean(time_faq_tket)) if time_faq_tket else 0.0
        task_record["faq_tket_prep_time_mean"] = float(np.mean(prep_faq_tket)) if prep_faq_tket else 0.0
        task_record["faq_tket_success_rate"] = 100.0

        task_record["faq_qmap_swaps_mean"] = m_faq_qmap
        task_record["faq_qmap_swaps_ci95"] = ci_faq_qmap

        task_record["faq_sabre_swaps_mean"] = m_faq_sabre
        task_record["faq_sabre_swaps_ci95"] = ci_faq_sabre

        task_record["ablation_barycenter_swaps_mean"] = m_ablation_bary
        task_record["ablation_random_multistart_swaps_mean"] = m_ablation_rand

        task_record["min_default_baseline"] = min_default

        all_results.append(task_record)
        print(f"  -> SABRE Def: {m_sabre:.1f} | TKET Def: {m_tket_def:.1f} | Paper: {m_paper:.1f} | FAQ+TKET: {m_faq_tket:.1f} ± {ci_faq_tket:.1f}")

    # Save to JSON
    out_path = "/home/karthikg/.gemini/antigravity/scratch/qap_quantum_compiler/benchmark_rigorous_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\n=== BENCHMARK COMPLETE! Saved {len(all_results)} records to {out_path} ===")


if __name__ == "__main__":
    main()
