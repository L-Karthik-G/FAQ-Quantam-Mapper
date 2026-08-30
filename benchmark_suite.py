"""
Extended Benchmark Suite: 10-Method Comparison
All 3 Defaults | All 3 FAQ | All 3 FAQ+FGEA | Original IEEE QCE 2023 Paper Method
K=5 multi-seed runs with 95% Confidence Intervals across all 36 test configurations.
"""

import json
import os
import time
from typing import Dict, List, Tuple

import numpy as np
from scipy import stats
import mqt.bench as mqt_bench
import networkx as nx
from qiskit.transpiler import CouplingMap

from qap_compiler.pipeline import FAQCompilerPipeline


def compute_ci95(values: List[float]) -> Tuple[float, float]:
    arr = np.array([v for v in values if v >= 0], dtype=float)
    n = len(arr)
    if n == 0:
        return -1.0, 0.0
    mean = float(np.mean(arr))
    if n < 2 or np.std(arr, ddof=1) == 0:
        return mean, 0.0
    ci_half = stats.sem(arr) * stats.t.ppf((1 + 0.95) / 2.0, n - 1)
    return mean, float(ci_half)


def build_hardware_profiles(seed: int = 42) -> Dict:
    profiles = {}
    rng = np.random.default_rng(seed)

    ibm_cm = CouplingMap.from_heavy_hex(distance=7)
    ibm_edges = list(ibm_cm.get_edges())
    num_ibm = max(max(u, v) for u, v in ibm_edges) + 1
    ibm_errors = {}
    for u, v in ibm_edges:
        err = float(rng.uniform(0.005, 0.025))
        ibm_errors[(u, v)] = err
        ibm_errors[(v, u)] = err
    profiles["IBM_HeavyHex"] = (num_ibm, ibm_edges, ibm_errors)

    grid_G = nx.convert_node_labels_to_integers(nx.grid_2d_graph(8, 10))
    rigetti_edges, rigetti_errors = [], {}
    for u, v in grid_G.edges():
        err = float(rng.uniform(0.01, 0.04))
        rigetti_edges.extend([(u, v), (v, u)])
        rigetti_errors[(u, v)] = err
        rigetti_errors[(v, u)] = err
    profiles["Rigetti_Grid"] = (80, rigetti_edges, rigetti_errors)

    ionq_G = nx.complete_graph(50)
    ionq_edges, ionq_errors = [], {}
    for u, v in ionq_G.edges():
        err = float(rng.uniform(0.001, 0.005))
        ionq_edges.extend([(u, v), (v, u)])
        ionq_errors[(u, v)] = err
        ionq_errors[(v, u)] = err
    profiles["IonQ_AllToAll"] = (50, ionq_edges, ionq_errors)

    return profiles


def safe_run(fn, *args, **kwargs):
    """Runs a compiler method safely, returns (swaps, time) or (-1, -1.0) on failure."""
    try:
        _, m = fn(*args, **kwargs)
        return m["swaps"], m["total_time"]
    except Exception:
        return -1, -1.0


def run_10method_benchmark(
    num_runs: int = 5,
    benchmark_names: List[str] = ["qft", "ghz", "qaoa", "vqe_real_amp"],
    qubit_scales: List[int] = [10, 20, 50],
) -> List[Dict]:

    results = []
    METHOD_NAMES = [
        "sabre_default", "qmap_default", "tket_default",
        "faq_sabre", "faq_tket", "faq_qmap",
        "fgea_faq_sabre", "fgea_faq_tket", "fgea_faq_qmap",
        "paper_method",
    ]

    print("\n" + "=" * 110)
    print("  10-METHOD BENCHMARK SUITE (K=5 Runs, 95% CI) — Defaults | FAQ | FAQ+FGEA | Paper Method  ")
    print("=" * 110 + "\n")

    for arch_name in ["IBM_HeavyHex", "Rigetti_Grid", "IonQ_AllToAll"]:
        print(f"\n>>> Architecture: {arch_name}")
        print("-" * 110)

        for bench_name in benchmark_names:
            for N in qubit_scales:

                hw_sample = build_hardware_profiles(seed=42)[arch_name]
                M = hw_sample[0]
                if N > M:
                    continue

                try:
                    raw_circuit = mqt_bench.get_benchmark(bench_name, mqt_bench.BenchmarkLevel.ALG, N)
                except Exception:
                    continue

                # Collectors: {method_name: (swaps_list, times_list)}
                collectors = {m: ([], []) for m in METHOD_NAMES}

                for k in range(num_runs):
                    run_seed = 42 + k * 17
                    profiles = build_hardware_profiles(seed=run_seed)
                    _, coupling_map, error_rates = profiles[arch_name]
                    p = FAQCompilerPipeline(threshold_qubits=10, num_faq_starts=3, seed=run_seed, fgea_buffer=4)

                    # 1. SABRE Default
                    sw, t = safe_run(p.compile_baseline_qiskit_sabre, raw_circuit, M, coupling_map)
                    collectors["sabre_default"][0].append(sw); collectors["sabre_default"][1].append(t)

                    # 2. QMAP Default
                    sw, t = safe_run(p.compile_baseline_vanilla_qmap, raw_circuit, M, coupling_map)
                    collectors["qmap_default"][0].append(sw); collectors["qmap_default"][1].append(t)

                    # 3. PyTKET Default
                    sw, t = safe_run(p.compile_baseline_tket, raw_circuit, M, coupling_map)
                    collectors["tket_default"][0].append(sw); collectors["tket_default"][1].append(t)

                    # 4. FAQ + SABRE
                    sw, t = safe_run(p.compile_faq_sabre, raw_circuit, M, coupling_map, error_rates)
                    collectors["faq_sabre"][0].append(sw); collectors["faq_sabre"][1].append(t)

                    # 5. FAQ + PyTKET
                    sw, t = safe_run(p.compile_faq_tket, raw_circuit, M, coupling_map, error_rates)
                    collectors["faq_tket"][0].append(sw); collectors["faq_tket"][1].append(t)

                    # 6. FAQ + QMAP
                    sw, t = safe_run(p.compile, raw_circuit, M, coupling_map, error_rates, force_faq=(N >= 10))
                    collectors["faq_qmap"][0].append(sw); collectors["faq_qmap"][1].append(t)

                    # 7. FAQ + FGEA + SABRE
                    sw, t = safe_run(p.compile_fgea_faq_sabre, raw_circuit, M, coupling_map, error_rates)
                    collectors["fgea_faq_sabre"][0].append(sw); collectors["fgea_faq_sabre"][1].append(t)

                    # 8. FAQ + FGEA + PyTKET
                    sw, t = safe_run(p.compile_fgea_faq_tket, raw_circuit, M, coupling_map, error_rates)
                    collectors["fgea_faq_tket"][0].append(sw); collectors["fgea_faq_tket"][1].append(t)

                    # 9. FAQ + FGEA + QMAP
                    sw, t = safe_run(p.compile_fgea_faq_qmap, raw_circuit, M, coupling_map, error_rates)
                    collectors["fgea_faq_qmap"][0].append(sw); collectors["fgea_faq_qmap"][1].append(t)

                    # 10. Paper Method (FGEA + FMA + SABRE)
                    sw, t = safe_run(p.compile_paper_method, raw_circuit, M, coupling_map, error_rates)
                    collectors["paper_method"][0].append(sw); collectors["paper_method"][1].append(t)

                # Compute stats for all methods
                record = {
                    "architecture": arch_name,
                    "benchmark": bench_name,
                    "qubits": N,
                    "physical_qubits": M,
                }
                for method in METHOD_NAMES:
                    sw_mean, sw_ci = compute_ci95(collectors[method][0])
                    t_mean, t_ci = compute_ci95(collectors[method][1])
                    record[f"{method}_swap_mean"] = sw_mean
                    record[f"{method}_swap_ci95"] = sw_ci
                    record[f"{method}_time_mean"] = t_mean
                    record[f"{method}_time_ci95"] = t_ci

                results.append(record)

                # Print summary row
                s = record
                print(
                    f"[{arch_name[:6]}] {bench_name.upper():<12} N={N:<2} | "
                    f"SABRE:{s['sabre_default_swap_mean']:6.1f} "
                    f"| FAQ-T:{s['faq_tket_swap_mean']:6.1f} "
                    f"| FGEA-FAQ-T:{s['fgea_faq_tket_swap_mean']:6.1f} "
                    f"| FGEA-FAQ-Q:{s['fgea_faq_qmap_swap_mean']:6.1f} "
                    f"| Paper:{s['paper_method_swap_mean']:6.1f}"
                )

    return results


def print_markdown_table(results: List[Dict]) -> str:
    lines = []
    lines.append("# 10-Method Benchmark Results (K=5 Runs, 95% CI)\n")
    lines.append("| Arch | Circuit | N | SABRE Def | QMAP Def | **FAQ+SABRE** | **FAQ+TKET** | **FAQ+QMAP** | **FGEA+FAQ+SABRE** | **FGEA+FAQ+TKET** | **FGEA+FAQ+QMAP** | **Paper (FGEA+FMA)** |")
    lines.append("|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|")

    def fmt(mean, ci):
        if mean < 0:
            return "CRASH"
        return f"{mean:.1f}±{ci:.1f}"

    for r in results:
        lines.append(
            f"| {r['architecture']} | {r['benchmark'].upper()} | {r['qubits']} "
            f"| {fmt(r['sabre_default_swap_mean'], r['sabre_default_swap_ci95'])} "
            f"| {fmt(r['qmap_default_swap_mean'], r['qmap_default_swap_ci95'])} "
            f"| **{fmt(r['faq_sabre_swap_mean'], r['faq_sabre_swap_ci95'])}** "
            f"| **{fmt(r['faq_tket_swap_mean'], r['faq_tket_swap_ci95'])}** "
            f"| **{fmt(r['faq_qmap_swap_mean'], r['faq_qmap_swap_ci95'])}** "
            f"| **{fmt(r['fgea_faq_sabre_swap_mean'], r['fgea_faq_sabre_swap_ci95'])}** "
            f"| **{fmt(r['fgea_faq_tket_swap_mean'], r['fgea_faq_tket_swap_ci95'])}** "
            f"| **{fmt(r['fgea_faq_qmap_swap_mean'], r['fgea_faq_qmap_swap_ci95'])}** "
            f"| **{fmt(r['paper_method_swap_mean'], r['paper_method_swap_ci95'])}** |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    results = run_10method_benchmark(num_runs=5)

    out_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(out_dir, "benchmark_fgea_results.json")
    md_path = os.path.join(out_dir, "benchmark_fgea_summary.md")

    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)

    md = print_markdown_table(results)
    with open(md_path, "w") as f:
        f.write(md)

    print("\n\n" + md)
    print(f"\nJSON  → {json_path}")
    print(f"Table → {md_path}")
