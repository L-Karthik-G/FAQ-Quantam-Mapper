"""
Benchmark 2: Independent Replication Study
Runs multi-seed (K=5) benchmarks with a completely independent seed set
(seeds = [2024, 2025, 2026, 2027, 2028]) across IBM Heavy-Hex, Rigetti Grid, and IonQ.
Saves results independently to benchmark_2_results.json.
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


def build_hardware_profiles(seed=2024):
    profiles = {}
    rng = np.random.default_rng(seed)

    # IBM Heavy-Hex (115 physical qubits, distance 7)
    ibm_cm = CouplingMap.from_heavy_hex(distance=7)
    ibm_edges = list(ibm_cm.get_edges())
    M_ibm = max(max(u, v) for u, v in ibm_edges) + 1
    ibm_errors = {}
    for u, v in ibm_edges:
        err = float(rng.uniform(0.005, 0.025))
        ibm_errors[(u, v)] = err
        ibm_errors[(v, u)] = err
    profiles["IBM_HeavyHex"] = (M_ibm, ibm_edges, ibm_errors)

    # Rigetti Grid (80 physical qubits, 8x10 grid)
    grid_G = nx.convert_node_labels_to_integers(nx.grid_2d_graph(8, 10))
    rigetti_edges, rigetti_errors = [], {}
    for u, v in grid_G.edges():
        err = float(rng.uniform(0.01, 0.04))
        rigetti_edges.extend([(u, v), (v, u)])
        rigetti_errors[(u, v)] = err
        rigetti_errors[(v, u)] = err
    profiles["Rigetti_Grid"] = (80, rigetti_edges, rigetti_errors)

    # IonQ All-to-All (50 physical qubits)
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
    except Exception as e:
        return -1, -1.0


# Representative benchmark test cases covering small, medium, and large scales
TEST_SUITE = [
    # (bench_key, label, qubits, architectures)
    ("grover",       "Grover's Search",    8,  ["IBM_HeavyHex", "Rigetti_Grid"]),
    ("grover",       "Grover's Search",    10, ["IBM_HeavyHex", "Rigetti_Grid"]),
    ("grover",       "Grover's Search",    12, ["IBM_HeavyHex", "Rigetti_Grid"]),
    ("vqe_real_amp", "VQE (RealAmplitudes)", 20, ["IBM_HeavyHex", "Rigetti_Grid"]),
    ("vqe_real_amp", "VQE (RealAmplitudes)", 50, ["IBM_HeavyHex", "Rigetti_Grid"]),
    ("ghz",          "GHZ State",          20, ["IBM_HeavyHex", "Rigetti_Grid"]),
    ("ghz",          "GHZ State",          50, ["IBM_HeavyHex", "Rigetti_Grid"]),
    ("bv",           "Bernstein-Vazirani", 10, ["IBM_HeavyHex", "Rigetti_Grid"]),
    ("bv",           "Bernstein-Vazirani", 50, ["IBM_HeavyHex", "Rigetti_Grid"]),
    ("qft",          "QFT",                20, ["IBM_HeavyHex", "Rigetti_Grid"]),
    ("qft",          "QFT",                50, ["IBM_HeavyHex", "Rigetti_Grid"]),
    ("qpeexact",     "QPE (Exact)",        50, ["IBM_HeavyHex", "Rigetti_Grid"]),
    ("qaoa",         "QAOA",               50, ["IBM_HeavyHex", "Rigetti_Grid"]),
    # IonQ verification
    ("qft",          "QFT",                50, ["IonQ_AllToAll"]),
    ("vqe_real_amp", "VQE (RealAmplitudes)", 50, ["IonQ_AllToAll"]),
    ("ghz",          "GHZ State",          50, ["IonQ_AllToAll"]),
]

METHODS = ["sabre_default", "qmap_default", "tket_default", "faq_tket", "faq_qmap", "paper_fgea_fma"]
SEEDS = [2024, 2025, 2026, 2027, 2028]
K = len(SEEDS)

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmark_2_results.json")
results = []

print("=" * 115)
print(f"  BENCHMARK 2: INDEPENDENT REPLICATION STUDY (K={K} Fresh Seeds: {SEEDS})")
print("=" * 115 + "\n")

start_all = time.time()

for bench_key, bench_label, N, arch_list in TEST_SUITE:
    for arch_name in arch_list:
        hw0 = build_hardware_profiles(seed=2024)[arch_name]
        M = hw0[0]

        try:
            raw_circuit = mqt_bench.get_benchmark(bench_key, mqt_bench.BenchmarkLevel.ALG, N)
            decomp_circuit = transpile(raw_circuit, basis_gates=["cx", "h", "rz", "x", "sx"], optimization_level=0)
        except Exception as e:
            print(f"[SKIP] {bench_label} N={N} on {arch_name}: {e}")
            continue

        collectors = {m: ([], []) for m in METHODS}

        for k, run_seed in enumerate(SEEDS):
            profiles = build_hardware_profiles(seed=run_seed)
            _, coupling_map, error_rates = profiles[arch_name]
            p = FAQCompilerPipeline(threshold_qubits=10, num_faq_starts=3, seed=run_seed)

            # 1. SABRE Default
            sw, t = safe_run(p.compile_baseline_qiskit_sabre, decomp_circuit, M, coupling_map)
            collectors["sabre_default"][0].append(sw); collectors["sabre_default"][1].append(t)

            # 2. QMAP Default (skip on Grover to prevent A* memory explosion)
            if N <= 50 and bench_key not in ["grover"]:
                sw, t = safe_run(p.compile_baseline_vanilla_qmap, decomp_circuit, M, coupling_map)
            else:
                sw, t = -1, -1.0
            collectors["qmap_default"][0].append(sw); collectors["qmap_default"][1].append(t)

            # 3. PyTKET Default
            sw, t = safe_run(p.compile_baseline_tket, decomp_circuit, M, coupling_map)
            collectors["tket_default"][0].append(sw); collectors["tket_default"][1].append(t)

            # 4. FAQ + PyTKET
            sw, t = safe_run(p.compile_faq_tket, decomp_circuit, M, coupling_map, error_rates)
            collectors["faq_tket"][0].append(sw); collectors["faq_tket"][1].append(t)

            # 5. FAQ + QMAP (skip on Grover 10/12 for timeout)
            if bench_key not in ["grover"] or N <= 8:
                sw, t = safe_run(p.compile, decomp_circuit, M, coupling_map, error_rates, force_faq=True)
            else:
                sw, t = -1, -1.0
            collectors["faq_qmap"][0].append(sw); collectors["faq_qmap"][1].append(t)

            # 6. Paper Method (FGEA + FMA)
            sw, t = safe_run(p.compile_paper_method, decomp_circuit, M, coupling_map, error_rates)
            collectors["paper_fgea_fma"][0].append(sw); collectors["paper_fgea_fma"][1].append(t)

        record = {
            "architecture": arch_name,
            "benchmark": bench_key,
            "benchmark_label": bench_label,
            "qubits": N,
            "physical_qubits": M,
        }
        for method in METHODS:
            ms, ci_s = compute_ci95(collectors[method][0])
            mt, ci_t = compute_ci95(collectors[method][1])
            record[f"{method}_swap_mean"] = ms
            record[f"{method}_swap_ci95"] = ci_s
            record[f"{method}_time_mean"] = mt
            record[f"{method}_time_ci95"] = ci_t

        results.append(record)

        # Incremental save
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)

        sabre_s = record["sabre_default_swap_mean"]
        tket_s = record["tket_default_swap_mean"]
        faq_tket_s = record["faq_tket_swap_mean"]
        faq_qmap_s = record["faq_qmap_swap_mean"]

        valid_faq = [s for s in [faq_tket_s, faq_qmap_s] if s >= 0]
        best_faq = min(valid_faq) if valid_faq else 0.0
        valid_def = [s for s in [sabre_s, tket_s] if s >= 0]
        best_def = min(valid_def) if valid_def else 0.0

        pct = ((best_def - best_faq) / best_def * 100) if best_def > 0 else 0.0

        print(
            f"[{arch_name[:6]}] {bench_label:<20} N={N:<2} | "
            f"SABRE:{sabre_s:7.1f} | TKET Def:{tket_s:7.1f} | "
            f"FAQ+TKET:{faq_tket_s:7.1f} | FAQ+QMAP:{faq_qmap_s:7.1f} | "
            f"Best FAQ vs Def: {pct:+.1f}%"
        )

total_elapsed = time.time() - start_all
print(f"\n✅ Benchmark 2 completed in {total_elapsed:.1f}s. Results saved to {out_path}")
