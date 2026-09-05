"""
Extended Circuit Benchmark: Grover, QPE (exact), Bernstein-Vazirani
All 10 methods | IBM Heavy-Hex + Rigetti Grid + IonQ | K=5, 95% CI
Incremental save enabled after every configuration.
"""

import json, os, time
from typing import List, Tuple
import numpy as np
from scipy import stats
import mqt.bench as mqt_bench
import networkx as nx
from qiskit import transpile
from qiskit.transpiler import CouplingMap

from qap_compiler.pipeline import FAQCompilerPipeline


def compute_ci95(values):
    arr = np.array([v for v in values if v >= 0], dtype=float)
    n = len(arr)
    if n == 0:
        return -1.0, 0.0
    mean = float(np.mean(arr))
    if n < 2 or np.std(arr, ddof=1) == 0:
        return mean, 0.0
    ci = stats.sem(arr) * stats.t.ppf(0.975, n - 1)
    return mean, float(ci)


def build_hardware_profiles(seed=42):
    profiles = {}
    rng = np.random.default_rng(seed)

    ibm_cm = CouplingMap.from_heavy_hex(distance=7)
    ibm_edges = list(ibm_cm.get_edges())
    M_ibm = max(max(u, v) for u, v in ibm_edges) + 1
    ibm_errors = {}
    for u, v in ibm_edges:
        err = float(rng.uniform(0.005, 0.025))
        ibm_errors[(u, v)] = err
        ibm_errors[(v, u)] = err
    profiles["IBM_HeavyHex"] = (M_ibm, ibm_edges, ibm_errors)

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
    try:
        _, m = fn(*args, **kwargs)
        return m["swaps"], m["total_time"]
    except Exception:
        return -1, -1.0


METHOD_NAMES = [
    "sabre_default", "qmap_default", "tket_default",
    "faq_sabre", "faq_tket", "faq_qmap",
    "fgea_faq_sabre", "fgea_faq_tket", "fgea_faq_qmap",
    "paper_method",
]

NEW_CIRCUITS = [
    ("grover",   "Grover's Search",    [8, 10, 12]),
    ("qpeexact", "QPE (Exact)",        [10, 20, 50]),
    ("bv",       "Bernstein-Vazirani", [10, 20, 50]),
]

ARCHITECTURES = ["IBM_HeavyHex", "Rigetti_Grid"]
K             = 5

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "benchmark_new_circuits_results.json")

# Load existing results if resuming
if os.path.exists(out_path):
    try:
        with open(out_path, "r") as f:
            results = json.load(f)
    except Exception:
        results = []
else:
    results = []

completed_keys = set((r["architecture"], r["benchmark"], r["qubits"]) for r in results)

print("\n" + "=" * 110)
print("  EXTENDED BENCHMARK: Grover | QPE | BV  —  All 10 Methods, K=5, 95% CI")
print("=" * 110 + "\n")

for arch_name in ARCHITECTURES:
    print(f"\n>>> Architecture: {arch_name}")
    print("-" * 110)

    for bench_key, bench_label, qubit_scales in NEW_CIRCUITS:
        for N in qubit_scales:
            if (arch_name, bench_key, N) in completed_keys:
                print(f"[{arch_name[:6]}] {bench_label:<22} N={N:<2} | Already completed, skipping.")
                continue

            hw0 = build_hardware_profiles(seed=42)[arch_name]
            M = hw0[0]
            if N > M:
                continue

            try:
                raw_circuit = mqt_bench.get_benchmark(bench_key, mqt_bench.BenchmarkLevel.ALG, N)
                decomp_circuit = transpile(raw_circuit, basis_gates=["cx", "h", "rz", "x", "sx"], optimization_level=0)
            except Exception as e:
                print(f"  [SKIP] {bench_label} N={N}: {e}")
                continue

            collectors = {m: ([], []) for m in METHOD_NAMES}

            for k in range(K):
                run_seed = 42 + k * 17
                profiles = build_hardware_profiles(seed=run_seed)
                _, coupling_map, error_rates = profiles[arch_name]
                p = FAQCompilerPipeline(threshold_qubits=10, num_faq_starts=3,
                                        seed=run_seed, fgea_buffer=4)

                sw, t = safe_run(p.compile_baseline_qiskit_sabre, decomp_circuit, M, coupling_map)
                collectors["sabre_default"][0].append(sw); collectors["sabre_default"][1].append(t)

                sw, t = safe_run(p.compile_baseline_vanilla_qmap, decomp_circuit, M, coupling_map)
                collectors["qmap_default"][0].append(sw); collectors["qmap_default"][1].append(t)

                sw, t = safe_run(p.compile_baseline_tket, decomp_circuit, M, coupling_map)
                collectors["tket_default"][0].append(sw); collectors["tket_default"][1].append(t)

                sw, t = safe_run(p.compile_faq_sabre, decomp_circuit, M, coupling_map, error_rates)
                collectors["faq_sabre"][0].append(sw); collectors["faq_sabre"][1].append(t)

                sw, t = safe_run(p.compile_faq_tket, decomp_circuit, M, coupling_map, error_rates)
                collectors["faq_tket"][0].append(sw); collectors["faq_tket"][1].append(t)

                sw, t = safe_run(p.compile, decomp_circuit, M, coupling_map, error_rates, force_faq=(N >= 10))
                collectors["faq_qmap"][0].append(sw); collectors["faq_qmap"][1].append(t)

                sw, t = safe_run(p.compile_fgea_faq_sabre, decomp_circuit, M, coupling_map, error_rates)
                collectors["fgea_faq_sabre"][0].append(sw); collectors["fgea_faq_sabre"][1].append(t)

                sw, t = safe_run(p.compile_fgea_faq_tket, decomp_circuit, M, coupling_map, error_rates)
                collectors["fgea_faq_tket"][0].append(sw); collectors["fgea_faq_tket"][1].append(t)

                sw, t = safe_run(p.compile_fgea_faq_qmap, decomp_circuit, M, coupling_map, error_rates)
                collectors["fgea_faq_qmap"][0].append(sw); collectors["fgea_faq_qmap"][1].append(t)

                sw, t = safe_run(p.compile_paper_method, decomp_circuit, M, coupling_map, error_rates)
                collectors["paper_method"][0].append(sw); collectors["paper_method"][1].append(t)

            record = {
                "architecture": arch_name,
                "benchmark": bench_key,
                "benchmark_label": bench_label,
                "qubits": N,
                "physical_qubits": M,
            }
            for method in METHOD_NAMES:
                ms, ci_s = compute_ci95(collectors[method][0])
                mt, ci_t = compute_ci95(collectors[method][1])
                record[f"{method}_swap_mean"] = ms
                record[f"{method}_swap_ci95"] = ci_s
                record[f"{method}_time_mean"] = mt
                record[f"{method}_time_ci95"] = ci_t

            results.append(record)
            completed_keys.add((arch_name, bench_key, N))

            # Incremental save
            with open(out_path, "w") as f:
                json.dump(results, f, indent=2)

            r = record
            sabre = r["sabre_default_swap_mean"]
            tket  = r["faq_tket_swap_mean"]
            qmap  = r["faq_qmap_swap_mean"]
            paper = r["paper_method_swap_mean"]
            diff_t = sabre - tket
            pct_t  = (diff_t / sabre * 100) if sabre > 0 else 0
            print(
                f"[{arch_name[:6]}] {bench_label:<22} N={N:<2} | "
                f"SABRE:{sabre:7.1f} | FAQ-T:{tket:7.1f} ({pct_t:+.1f}%) "
                f"| FAQ-Q:{qmap:7.1f} | Paper:{paper:7.1f}"
            )

print(f"\n\nAll results saved → {out_path}")
