"""A5 — Multi-cell, multi-seed component ablation (rows 1-3).

Re-runs the single-cell ablation of `benchmark_ablations.py` (rows 1-3) across five cells
spanning the regimes in Tables 1-2, with multiple seeds and mean +/- 95% CI, to give the
Gaussian-vs-random-restarts question real statistical power.

Cells (authorized set for A5):
  1. Grover N=10, IBM Brisbane      (continuity with the original single-seed ablation)
  2. VQE N=50,  synthetic grid      (largest FAQ+PyTKET paired-seed win, -91.5%)
  3. QRAM N=20, IBM Brisbane        (the FAQ+SABRE-vs-SABRE win)
  4. Grover N=12, IBM Brisbane      (one of FAQ+PyTKET's worst regressions)
  5. VQE N=10,  IBM Brisbane        (zero-SWAP baseline: no room to improve)

Configurations (mirror `benchmark_ablations.py` rows 1-3):
  1. single barycenter start (num_starts=1)        -- deterministic
  2. random multi-start (K=5)
  3. structured Gaussian multi-start (K=5)         -- "ours"

Metric: the post-2-opt **polished QAP cost** of the best candidate (the objective the pipeline
minimizes before routing). Rows 2 & 3 vary with seed; row 1 is deterministic and reported as a
point value. A paired Wilcoxon (row 3 vs row 2) is run on the per-seed polished costs, then
Benjamini-Hochberg-corrected across the cells.

Outputs: benchmarks/results/ablation_multicell_results.json plus a printed table.

Usage:
  uv run python benchmarks/ablation_multicell.py --seeds 20
  uv run python benchmarks/ablation_multicell.py --seeds 20 --cells grover vqe_real_amp
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List

import numpy as np
from scipy import stats

# Ensure repo root importable.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from benchmarks.benchmark_eval import (
    get_hardware_topology,
    load_benchmark_circuit,
    load_holdout_circuit,
)
from qap_compiler.module_a_dag import DAGInteractionMatrixBuilder
from qap_compiler.module_b_hardware import HardwareMatrixBuilder
from qap_compiler.module_c_faq import AdaptiveFAQSolver

ARCH_BRISBANE = "IBM_Eagle_127_Brisbane"
ARCH_RIGETTI = "Rigetti_Grid_80"

# (arch, bench_key, suite_type, label, n_qubits) -- the 5 A5 cells spanning the regimes in
# Tables 1-2. Grover-N10 Brisbane is kept for continuity with the original single-seed ablation.
CELLS = [
    (ARCH_BRISBANE, "grover", "mqt", "Grover's Search", 10),
    (ARCH_RIGETTI, "vqe_real_amp", "mqt", "VQE (RealAmplitudes)", 50),
    (ARCH_BRISBANE, "qram_bucket_brigade", "holdout", "QRAM Decoder (Holdout)", 20),
    (ARCH_BRISBANE, "grover", "mqt", "Grover's Search", 12),
    (ARCH_BRISBANE, "vqe_real_amp", "mqt", "VQE (RealAmplitudes)", 10),
]

CONFIGS = {
    "row1_barycenter_single": dict(num_starts=1, start_mode="barycenter"),
    "row2_random_multistart": dict(num_starts=5, start_mode="random"),
    "row3_gaussian_multistart": dict(num_starts=5, start_mode="gaussian"),
}

# Rows expected to vary with seed (paired Wilcoxon compares these two).
ROW3_KEY = "row3_gaussian_multistart"
ROW2_KEY = "row2_random_multistart"

# Rigetti synthetic-grid error profile is the only one available for that cell; the QAP
# objective there is still the same quantity FAQ minimizes before routing.
_RIGETTI_NOTE = (
    "synthetic-grid topology (Rigetti_Grid_80 identifier); NOT a real Rigetti device"
)


def load_circuit(bench_key: str, suite_type: str, n_qubits: int):
    if suite_type == "mqt":
        return load_benchmark_circuit(bench_key, n_qubits)
    return load_holdout_circuit(bench_key, n_qubits)


def _polished_cost(solver: AdaptiveFAQSolver) -> float:
    return float(solver.last_run_stats["best_polished_cost"])


def run_cell(arch: str, bench_key: str, suite_type: str, label: str, n_qubits: int,
             seeds: List[int]) -> Dict:
    M, edges, errs = get_hardware_topology(arch)
    qc = load_circuit(bench_key, suite_type, n_qubits)
    A = DAGInteractionMatrixBuilder(gamma=0.9).build_matrix(qc)
    B = HardwareMatrixBuilder(alpha=1.0).build_matrix(M, edges, errs, is_directed=True)

    rec = {"benchmark": bench_key, "label": label, "qubits": n_qubits,
           "architecture": arch, "num_physical_qubits": M, "seeds": seeds,
           "configs": {}}

    for cfg_key, cfg in CONFIGS.items():
        per_seed = []
        run_seeds = [seeds[0]] if cfg["num_starts"] == 1 else seeds
        for s in run_seeds:
            solver = AdaptiveFAQSolver(enable_2opt=True, seed=s, **cfg)
            solver.solve(A, B)
            per_seed.append(_polished_cost(solver))
        arr = np.array(per_seed, dtype=float)
        entry = {"config": cfg_key, "num_starts": cfg["num_starts"],
                 "start_mode": cfg["start_mode"], "per_seed_polished_cost": per_seed}
        if len(arr) > 1:
            ci = float(stats.t.ppf(0.975, df=len(arr) - 1) * stats.sem(arr))
            entry.update({"mean": float(np.mean(arr)), "ci95": ci,
                          "deterministic": bool(float(np.ptp(arr)) == 0.0)})
        else:
            entry.update({"mean": float(arr[0]), "ci95": 0.0, "deterministic": True})
        rec["configs"][cfg_key] = entry

    # Paired Wilcoxon row3 vs row2 over shared seeds (always; both are seed-varying K=5).
    a = rec["configs"][ROW3_KEY]["per_seed_polished_cost"]
    b = rec["configs"][ROW2_KEY]["per_seed_polished_cost"]
    if len(a) == len(b) and len(a) > 1:
        d = np.asarray(a, float) - np.asarray(b, float)
        if float(np.ptp(d)) == 0.0:
            rec["gaussian_vs_random"] = {"test": "constant_difference",
                                         "note": "per-seed diff constant across all seeds",
                                         "mean_diff_gaussian_minus_random": float(np.mean(d))}
        else:
            res = stats.wilcoxon(d, zero_method="wilcox", alternative="two-sided")
            rec["gaussian_vs_random"] = {
                "test": "wilcoxon_signed_rank",
                "mean_diff_gaussian_minus_random": float(np.mean(d)),
                "statistic": float(res.statistic),
                "p_value": float(res.pvalue),
                "n_zero_diffs": int(np.sum(d == 0.0)),
                "n_pairs": int(len(d)),
            }
    return rec


def fmt_entry(e: Dict) -> str:
    if e.get("deterministic"):
        return f"{e['mean']:.2f} (det)"
    return f"{e['mean']:.2f} ± {e['ci95']:.2f}"


def _benjamini_hochberg(pvals: List[float]) -> List[float]:
    """BH step-up q-values (mirrors analyze_significance; standalone here)."""
    n = len(pvals)
    q = [0.0] * n
    if n == 0:
        return q
    order = sorted(range(n), key=lambda i: pvals[i])
    prev = float("inf")
    for pos in range(n - 1, -1, -1):
        i = order[pos]
        rank = pos + 1
        qv = n * pvals[i] / rank
        q[i] = min(qv, prev)
        prev = q[i]
    return q


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--start-seed", type=int, default=0)
    parser.add_argument("--cells", nargs="*", default=None,
                        help="subset of benchmark keys (e.g. grover vqe_real_amp); default=all")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    seeds = list(range(args.start_seed, args.start_seed + args.seeds))
    selected = CELLS if not args.cells else [c for c in CELLS if c[1] in args.cells]

    print(f"=== A5 ablation (rows 1-3): {len(selected)} cells, K={len(seeds)} seeds ===")
    results = []
    for arch, bench_key, suite_type, label, n in selected:
        rec = run_cell(arch, bench_key, suite_type, label, n, seeds)
        results.append(rec)
        arch_disp = "Brisbane" if "Brisbane" in arch else "Synthetic grid (not real Rigetti)"
        print(f"\n{label} N={n} [{arch_disp}]:")
        for cfg_key, e in rec["configs"].items():
            print(f"  {cfg_key:<26} polished cost: {fmt_entry(e)}")
        gv = rec.get("gaussian_vs_random")
        if gv and gv.get("p_value") is not None:
            print(f"  gaussian vs random (paired): p={gv['p_value']:.4g} "
                  f"(mean gauss-rand={gv['mean_diff_gaussian_minus_random']:+.2f}, "
                  f"{gv['n_pairs']} pairs, {gv['n_zero_diffs']} zero-diff)")
        elif gv:
            print(f"  gaussian vs random: {gv.get('note','')}")

    # BH-correct the gaussian-vs-random p-values across the cells (mirror of A2).
    gv_ps = [(i, r.get("gaussian_vs_random", {}).get("p_value"))
             for i, r in enumerate(results)]
    tested = [(i, p) for (i, p) in gv_ps if p is not None]
    if tested:
        bh = _benjamini_hochberg([p for _, p in tested])
        for (i, _), q in zip(tested, bh):
            results[i]["gaussian_vs_random"]["q_value_bh"] = q
            results[i]["gaussian_vs_random"]["significant_bh"] = bool(q < 0.05)

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out_dir, exist_ok=True)
    out_path = args.out or os.path.join(out_dir, "ablation_multicell_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    # Final table incl. BH.
    print("\n=== Summary (gaussian row3 vs random row2, BH-corrected across cells) ===")
    for r in results:
        gv = r.get("gaussian_vs_random", {})
        arch_disp = "Brisbane" if "Brisbane" in r["architecture"] else "SyntheticGrid"
        if gv.get("p_value") is None:
            print(f"  {r['label']:<24} N{r['qubits']:<3} {arch_disp:<13} {gv.get('note','n/a')}")
            continue
        sig = gv.get("significant_bh")
        tag = ("SIG" if sig else ("ns" if sig is False else "n/a"))
        print(f"  {r['label']:<24} N{r['qubits']:<3} {arch_disp:<13} "
              f"gauss-rand={gv['mean_diff_gaussian_minus_random']:+8.2f}  "
              f"p={gv['p_value']:.4g}  q_bh={gv.get('q_value_bh'):.4g}  {tag}")
    print(f"\nSaved -> {out_path}")


if __name__ == "__main__":
    main()
