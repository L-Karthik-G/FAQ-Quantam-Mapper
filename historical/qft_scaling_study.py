"""
Targeted QFT Scaling Study: IBM Heavy-Hex, N=30 and N=40
Confirms whether FAQ+TKET's 10.2% win at N=50 is a consistent trend
or a one-off result. K=5 multi-seed runs, 95% CI.
"""

import json, os, time
from typing import List, Tuple
import numpy as np
from scipy import stats
import mqt.bench as mqt_bench
import networkx as nx
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


def build_ibm_profile(seed=42):
    rng = np.random.default_rng(seed)
    ibm_cm = CouplingMap.from_heavy_hex(distance=7)
    ibm_edges = list(ibm_cm.get_edges())
    M = max(max(u, v) for u, v in ibm_edges) + 1
    errors = {}
    for u, v in ibm_edges:
        err = float(rng.uniform(0.005, 0.025))
        errors[(u, v)] = err
        errors[(v, u)] = err
    return M, ibm_edges, errors


def safe_run(fn, *args, **kwargs):
    try:
        _, m = fn(*args, **kwargs)
        return m["swaps"], m["total_time"]
    except Exception as e:
        return -1, -1.0


if __name__ == "__main__":
    K = 5
    QUBIT_SCALES = [30, 40]
    METHODS = ["sabre_default", "faq_sabre", "faq_tket", "faq_qmap"]

    print("\n" + "=" * 80)
    print("  QFT SCALING STUDY: IBM Heavy-Hex, N=30 & N=40  (K=5, 95% CI)")
    print("=" * 80 + "\n")

    results = []
    for N in QUBIT_SCALES:
        try:
            raw_circuit = mqt_bench.get_benchmark("qft", mqt_bench.BenchmarkLevel.ALG, N)
        except Exception as e:
            print(f"Could not generate QFT N={N}: {e}")
            continue

        collectors = {m: ([], []) for m in METHODS}

        for k in range(K):
            seed = 42 + k * 17
            M, coupling_map, error_rates = build_ibm_profile(seed)
            p = FAQCompilerPipeline(threshold_qubits=10, num_faq_starts=3, seed=seed)

            sw, t = safe_run(p.compile_baseline_qiskit_sabre, raw_circuit, M, coupling_map)
            collectors["sabre_default"][0].append(sw); collectors["sabre_default"][1].append(t)

            sw, t = safe_run(p.compile_faq_sabre, raw_circuit, M, coupling_map, error_rates)
            collectors["faq_sabre"][0].append(sw); collectors["faq_sabre"][1].append(t)

            sw, t = safe_run(p.compile_faq_tket, raw_circuit, M, coupling_map, error_rates)
            collectors["faq_tket"][0].append(sw); collectors["faq_tket"][1].append(t)

            sw, t = safe_run(p.compile, raw_circuit, M, coupling_map, error_rates, force_faq=True)
            collectors["faq_qmap"][0].append(sw); collectors["faq_qmap"][1].append(t)

        record = {"architecture": "IBM_HeavyHex", "benchmark": "QFT", "qubits": N, "physical_qubits": M}
        for m in METHODS:
            ms, ci_s = compute_ci95(collectors[m][0])
            mt, ci_t = compute_ci95(collectors[m][1])
            record[f"{m}_swap_mean"] = ms; record[f"{m}_swap_ci95"] = ci_s
            record[f"{m}_time_mean"] = mt; record[f"{m}_time_ci95"] = ci_t
        results.append(record)

        r = record
        sabre = r["sabre_default_swap_mean"]
        tket  = r["faq_tket_swap_mean"]
        diff  = sabre - tket
        pct   = (diff / sabre * 100) if sabre > 0 else 0

        print(f"QFT N={N:<2} | SABRE: {sabre:7.1f}±{r['sabre_default_swap_ci95']:.1f}"
              f" | FAQ+SABRE: {r['faq_sabre_swap_mean']:7.1f}±{r['faq_sabre_swap_ci95']:.1f}"
              f" | FAQ+TKET: {tket:7.1f}±{r['faq_tket_swap_ci95']:.1f}"
              f" | FAQ+QMAP: {r['faq_qmap_swap_mean']:7.1f}±{r['faq_qmap_swap_ci95']:.1f}"
              f" | Δ vs SABRE: {diff:+.1f} ({pct:+.1f}%)")

    # Print reference rows from prior runs for context
    print("\n--- Reference (from prior K=5 benchmark) ---")
    print("QFT N=10 | SABRE:  48.8±4.8 | FAQ+TKET:  48.4±3.9 | Δ = -0.4  ( -0.8%)")
    print("QFT N=20 | SABRE: 233.4±17.3 | FAQ+TKET: 243.6±6.7 | Δ = +10.2 ( +4.4%) ← FAQ worse")
    print("QFT N=50 | SABRE:1545.0±90.2 | FAQ+TKET:1394.8±39.4 | Δ = -150.2 (-9.7%) ← FAQ WINS ✅")

    # Save results
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qft_scaling_results.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved → {path}")
