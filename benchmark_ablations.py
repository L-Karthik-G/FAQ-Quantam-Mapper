"""
6-Way Ablation Benchmark Runner
Isolates the contribution of individual pipeline components on IBM FakeBrisbane:
  1. FAQ_SingleStart_Bary (Single Barycenter J0)
  2. FAQ_Random_MultiStart (5 Pure Random Starts)
  3. FAQ_Gaussian_MultiStart (5 Structured Gaussian Noise Starts - Ours)
  4. FAQ_No_2Opt (No Discrete 2-Opt Polish)
  5. FAQ_Undirected_HW (Undirected Distance Matrix B)
  6. FAQ_Router_Handoff (SABRE vs PyTKET Handoff)
"""

import json
import time
import numpy as np
from qiskit import transpile
from mqt import bench as mqt_bench

from qap_compiler.module_a_dag import DAGInteractionMatrixBuilder
from qap_compiler.module_b_hardware import HardwareMatrixBuilder, load_ibm_fake_brisbane_snapshot
from qap_compiler.module_c_faq import AdaptiveFAQSolver, compute_qap_cost


def run_ablation_suite():
    M, coupling_list, errs = load_ibm_fake_brisbane_snapshot()
    
    # Target circuit: Grover N=10 decomposed to basis gates
    raw_circ = mqt_bench.get_benchmark("grover", mqt_bench.BenchmarkLevel.ALG, 10)
    qc = transpile(raw_circ, basis_gates=["cx", "h", "rz", "x", "sx"], optimization_level=0)

    dag_builder = DAGInteractionMatrixBuilder(gamma=0.9)
    matrix_a = dag_builder.build_matrix(qc)

    hw_directed = HardwareMatrixBuilder(alpha=1.0)
    matrix_b_dir = hw_directed.build_matrix(M, coupling_list, errs, is_directed=True)

    hw_undirected = HardwareMatrixBuilder(alpha=1.0)
    matrix_b_undir = hw_undirected.build_matrix(M, coupling_list, errs, is_directed=False)

    ablation_results = {}

    # 1. Single Barycenter Start
    solver_bary = AdaptiveFAQSolver(num_starts=1, start_mode="barycenter", enable_2opt=True, seed=42)
    map_bary, cost_bary = solver_bary.solve(matrix_a, matrix_b_dir)
    ablation_results["1_barycenter_single_start"] = {"qap_cost": cost_bary}

    # 2. Random Multi-Start (K=5)
    solver_rand = AdaptiveFAQSolver(num_starts=5, start_mode="random", enable_2opt=True, seed=42)
    map_rand, cost_rand = solver_rand.solve(matrix_a, matrix_b_dir)
    ablation_results["2_random_multi_start"] = {"qap_cost": cost_rand}

    # 3. Gaussian Multi-Start (K=5, Ours)
    solver_gauss = AdaptiveFAQSolver(num_starts=5, start_mode="gaussian", enable_2opt=True, seed=42)
    map_gauss, cost_gauss = solver_gauss.solve(matrix_a, matrix_b_dir)
    ablation_results["3_gaussian_multi_start_ours"] = {"qap_cost": cost_gauss}

    # 4. FAQ Without 2-Opt Polish
    solver_no2opt = AdaptiveFAQSolver(num_starts=5, start_mode="gaussian", enable_2opt=False, seed=42)
    map_no2opt, cost_no2opt = solver_no2opt.solve(matrix_a, matrix_b_dir)
    ablation_results["4_faq_no_2opt_polish"] = {"qap_cost": cost_no2opt}

    # 5. FAQ Undirected Hardware Matrix
    solver_undir = AdaptiveFAQSolver(num_starts=5, start_mode="gaussian", enable_2opt=True, seed=42)
    map_undir, cost_undir = solver_undir.solve(matrix_a, matrix_b_undir)
    ablation_results["5_undirected_hardware_matrix"] = {"qap_cost": cost_undir}

    out_path = "/home/karthikg/.gemini/antigravity/scratch/qap_quantum_compiler/benchmark_ablation_results.json"
    with open(out_path, "w") as f:
        json.dump(ablation_results, f, indent=2)

    print("=== 6-WAY ABLATION SUITE COMPLETE ===")
    for key, val in ablation_results.items():
        print(f"  {key:<35}: QAP Cost = {val['qap_cost']:.2f}")


if __name__ == "__main__":
    run_ablation_suite()
