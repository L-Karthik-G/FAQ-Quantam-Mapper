"""
6-Way Component Isolation Ablation Runner
Evaluates and isolates individual pipeline components on IBM FakeBrisbane:
  1. Single Barycenter Start (J0)
  2. Pure Random Multi-Start (K=5)
  3. Structured Gaussian Multi-Start (K=5, Ours)
  4. FAQ Without 2-Opt Polish
  5. FAQ Undirected Hardware Matrix
"""

import json
import numpy as np
from qiskit import transpile
from mqt import bench as mqt_bench

from qap_compiler.module_a_dag import DAGInteractionMatrixBuilder
from qap_compiler.module_b_hardware import HardwareMatrixBuilder, load_ibm_fake_brisbane_snapshot
from qap_compiler.module_c_faq import AdaptiveFAQSolver, sinkhorn_knopp


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
    ablation_results["1_barycenter_single_start"] = {
        "qap_cost": float(cost_bary),
        "raw_faq_cost": float(solver_bary.last_run_stats["best_faq_continuous_cost"]),
    }

    # 2. Pure Random Multi-Start (K=5)
    solver_rand = AdaptiveFAQSolver(num_starts=5, start_mode="random", enable_2opt=True, seed=42)
    map_rand, cost_rand = solver_rand.solve(matrix_a, matrix_b_dir)
    ablation_results["2_random_multi_start"] = {
        "qap_cost": float(cost_rand),
        "raw_faq_cost": float(solver_rand.last_run_stats["best_faq_continuous_cost"]),
    }

    # 3. Structured Gaussian Perturbation Multi-Start (K=5, Ours)
    rng = np.random.default_rng(12345)
    J0 = np.ones((M, M), dtype=float) / M
    sigma = 0.08 / M
    
    gauss_costs = []
    gauss_raw_costs = []
    A_padded = np.pad(matrix_a, ((0, M - matrix_a.shape[0]), (0, M - matrix_a.shape[1])))
    for s_idx in range(5):
        noise = rng.normal(0.0, sigma, size=(M, M))
        p0 = sinkhorn_knopp(J0 + noise)
        perm, raw_c, polished_c = solver_bary._solve_single_start(A_padded, matrix_b_dir, p0)
        gauss_costs.append(polished_c)
        gauss_raw_costs.append(raw_c)
        
    best_gauss_cost = float(min(gauss_costs))
    ablation_results["3_gaussian_multi_start_ours"] = {
        "qap_cost": best_gauss_cost,
        "best_raw_faq_cost": float(min(gauss_raw_costs)),
        "all_candidate_polished_costs": [float(c) for c in gauss_costs],
        "all_candidate_raw_faq_costs": [float(c) for c in gauss_raw_costs],
    }

    # 4. FAQ Without 2-Opt Polish
    solver_no2opt = AdaptiveFAQSolver(num_starts=5, start_mode="barycenter", enable_2opt=False, seed=42)
    map_no2opt, cost_no2opt = solver_no2opt.solve(matrix_a, matrix_b_dir)
    ablation_results["4_faq_no_2opt_polish"] = {
        "qap_cost": float(cost_no2opt),
        "raw_faq_cost": float(solver_no2opt.last_run_stats["best_faq_continuous_cost"]),
    }

    # 5. FAQ Undirected Hardware Matrix
    solver_undir = AdaptiveFAQSolver(num_starts=5, start_mode="gaussian", enable_2opt=True, seed=42)
    map_undir, cost_undir = solver_undir.solve(matrix_a, matrix_b_undir)
    ablation_results["5_undirected_hardware_matrix"] = {
        "qap_cost": float(cost_undir),
        "raw_faq_cost": float(solver_undir.last_run_stats["best_faq_continuous_cost"]),
    }

    out_path = "/home/karthikg/.gemini/antigravity/scratch/qap_quantum_compiler/benchmark_ablation_results.json"
    with open(out_path, "w") as f:
        json.dump(ablation_results, f, indent=2)

    print("=== 6-WAY ABLATION SUITE COMPLETE ===")
    for key, val in ablation_results.items():
        raw_c = val.get('raw_faq_cost', val.get('best_raw_faq_cost', 0))
        print(f"  {key:<35}: Raw FAQ Cost = {raw_c:.2f} | Final Polished Cost = {val['qap_cost']:.2f}")


if __name__ == "__main__":
    run_ablation_suite()
