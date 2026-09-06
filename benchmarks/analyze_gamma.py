"""A6 - Gamma decay sensitivity: preregistered statistical analysis.

Implements the analysis plan recorded in reports/a6_gamma_spec.md:

  Step 1  Friedman omnibus per (circuit x router) cell across the 9 gamma
          conditions, seed = block. If p >= alpha for a cell, NO post-hoc
          gamma-vs-0.9 significance claims are made for that cell.
  Step 2  Only for cells passing Step 1: paired Wilcoxon signed-rank of each
          non-reference gamma vs gamma=0.90 on per-seed SWAP differences
          (8 comparisons per gated cell; no all-pairs).
  Step 3  Benjamini-Hochberg FDR across the complete family of post-hoc
          comparisons actually performed after the Step-1 gates.

Effect sizes / practical significance: for every significant comparison report the
mean and median per-seed SWAP difference (gamma - 0.90), the counts of seeds that
improved/tied/worsened, and a matched-pairs effect size (rank-biserial r).
Statistical significance is separated from practical meaningfulness.

Primary metric: post-routing SWAP count. All inputs are the per-seed rows from
benchmarks/results/a6_gamma_results.json (gamma=0.90 is the reference).

Usage:
  uv run python benchmarks/analyze_gamma.py --raw benchmarks/results/a6_gamma_results.json \
      --out benchmarks/results/a6_gamma_significance.json
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from typing import Dict, List, Tuple

import numpy as np
from scipy import stats

GAMMAS = [0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.95, 0.98, 1.00]
REF = 0.90
ALPHA = 0.05
BENCH_DIR = os.path.dirname(os.path.abspath(__file__))

ARCH_SHORT = {"IBM_Eagle_127_Brisbane": "Bris", "Rigetti_Grid_80": "Grid"}


def load_blocks(raw_path: str) -> Dict:
    with open(raw_path) as f:
        data = json.load(f)
    rows = data["rows"]
    blocks: "Dict[Tuple[str, str], Dict[str, Dict[int, int]]]" = defaultdict(
        lambda: defaultdict(dict)
    )
    for r in rows:
        if r.get("status") == "failed":
            continue
        blocks[(r["cell"], r["router"])][str(r["gamma"])][int(r["seed"])] = int(r["swaps"])
    return blocks


def benjamini_hochberg(pvals: List[float]) -> List[float]:
    n = len(pvals)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: pvals[i])
    q = [0.0] * n
    prev = float("inf")
    for pos in range(n - 1, -1, -1):
        i = order[pos]
        qv = n * pvals[i] / (pos + 1)
        q[i] = min(qv, prev)
        prev = q[i]
    return q


def effect_stats(diff: np.ndarray) -> Dict:
    """diff = per-seed (gamma - 0.90) SWAP differences. Negative = fewer SWAPs at gamma."""
    n = len(diff)
    improved = int(np.sum(diff < 0))
    tied = int(np.sum(diff == 0))
    worsened = int(np.sum(diff > 0))
    # matched-pairs rank-biserial r (a common paired effect size for Wilcoxon)
    d = diff[diff != 0]
    if len(d) == 0:
        r = 0.0
    else:
        ranks = stats.rankdata(np.abs(d))
        neg = np.sum(ranks[d < 0])
        tot = ranks.sum()
        r = (neg - (tot - neg)) / tot
    return {
        "n_seeds": int(n),
        "n_improved": improved,
        "n_tied": tied,
        "n_worsened": worsened,
        "mean_diff_gamma_minus_ref": float(np.mean(diff)),
        "median_diff_gamma_minus_ref": float(np.median(diff)),
        "rank_biserial_r": float(r),
    }


def analyze(raw_path: str) -> Dict:
    blocks = load_blocks(raw_path)
    cells_out = []
    post_hoc_rows = []  # (cell, router, gamma, dict) for comparisons actually performed
    n_friedman = 0
    n_gated = 0

    for (cell, router), gammas in sorted(blocks.items()):
        seeds = sorted({s for g in gammas.values() for s in g})
        # Friedman needs complete blocks: require all 9 gammas x all seeds present
        g_keys = [str(g) for g in GAMMAS]
        if not all(gk in gammas and len(gammas[gk]) == len(seeds) for gk in g_keys):
            continue
        mat = np.array([[gammas[gk][s] for s in seeds] for gk in g_keys], dtype=float)
        fr = stats.friedmanchisquare(*mat)
        n_friedman += 1
        cell_rec = {
            "cell": cell, "router": router,
            "n_seeds": len(seeds),
            "friedman_statistic": float(fr.statistic),
            "friedman_p": float(fr.pvalue),
            "friedman_significant": bool(fr.pvalue < ALPHA),
            "gammas": {
                gk: {"mean_swaps": float(np.mean([gammas[gk][s] for s in seeds])),
                     "sd_swaps": float(np.std([gammas[gk][s] for s in seeds])),
                     "ci95": float(stats.t.ppf(0.975, len(seeds) - 1) * stats.sem([gammas[gk][s] for s in seeds]))}
                for gk in g_keys
            },
        }
        cells_out.append(cell_rec)
        if not cell_rec["friedman_significant"]:
            continue
        n_gated += 1
        ref = np.array([gammas[str(REF)][s] for s in seeds], float)
        for g in GAMMAS:
            if g == REF:
                continue
            gv = np.array([gammas[str(g)][s] for s in seeds], float)
            diff = gv - ref
            entry = effect_stats(diff)
            if float(np.ptp(diff)) == 0:
                entry.update({"test": "constant_difference", "p_value": None,
                              "statistic": None, "note": "all seeds identical"})
            else:
                res = stats.wilcoxon(diff, zero_method="wilcox", alternative="two-sided")
                entry.update({"test": "wilcoxon_signed_rank",
                              "statistic": float(res.statistic),
                              "p_value": float(res.pvalue)})
            post_hoc_rows.append({"cell": cell, "router": router, "gamma": g, **entry})

    # Step 3: BH across the complete family actually performed
    performed = [r for r in post_hoc_rows if r.get("p_value") is not None]
    pvals = [r["p_value"] for r in performed]
    qs = benjamini_hochberg(pvals)
    for r, q in zip(performed, qs):
        r["q_value_bh"] = q
        r["significant_bh"] = bool(q < ALPHA)

    summary = {
        "n_cells_analyzed": n_friedman,
        "n_cells_gated_significant": n_gated,
        "n_posthoc_performed": len(performed),
        "n_posthoc_significant_bh": sum(1 for r in performed if r["significant_bh"]),
        "posthoc_positive_bh": sum(1 for r in performed
                                   if r["significant_bh"] and r["mean_diff_gamma_minus_ref"] < 0),
        "posthoc_negative_bh": sum(1 for r in performed
                                   if r["significant_bh"] and r["mean_diff_gamma_minus_ref"] > 0),
    }
    return {"alpha": ALPHA, "reference_gamma": REF, "gamma_grid": GAMMAS,
            "summary": summary, "cells": cells_out, "posthoc": post_hoc_rows}


def render_md(result: Dict) -> str:
    lines = []
    lines.append("| Cell | Router | Friedman p | gate | mean@0.9 | best gamma (lowest mean) | lowest mean | highest mean |")
    lines.append("|:--|:--|:--:|:--:|:--:|:--:|:--:|:--:|")
    for c in result["cells"]:
        gm = c["gammas"]
        means = {float(k): v["mean_swaps"] for k, v in gm.items()}
        bg = min(means, key=lambda g: means[g])
        lines.append(
            f"| {c['cell']} | {c['router']} | {c['friedman_p']:.4g} | "
            f"{'PASS' if c['friedman_significant'] else 'fail'} | {means[REF]:.2f} | "
            f"{bg:.2f} ({means[bg]:.2f}) | {min(means.values()):.2f} | {max(means.values()):.2f} |"
        )
    lines.append("")
    lines.append("### Post-hoc (gated cells only): gamma vs 0.90 (mean diff; q after BH across performed family)")
    lines.append("| Cell | Router | gamma | mean diff | median diff | r | seeds +/- | p | q(BH) | sig |")
    lines.append("|:--|:--|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|")
    for r in sorted(result["posthoc"], key=lambda x: (x["cell"], x["router"], x["gamma"])):
        p = r.get("p_value")
        q = r.get("q_value_bh")
        lines.append(
            f"| {r['cell']} | {r['router']} | {r['gamma']:.2f} | {r['mean_diff_gamma_minus_ref']:+.2f} | "
            f"{r['median_diff_gamma_minus_ref']:+.1f} | {r['rank_biserial_r']:+.2f} | "
            f"{r['n_improved']}/{r['n_tied']}/{r['n_worsened']} | "
            f"{'—' if p is None else f'{p:.4g}'} | {'—' if q is None else f'{q:.4g}'} | "
            f"{'yes' if r.get('significant_bh') else 'no'} |"
        )
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=os.path.join(BENCH_DIR, "results", "a6_gamma_results.json"))
    ap.add_argument("--out", default=os.path.join(BENCH_DIR, "results", "a6_gamma_significance.json"))
    args = ap.parse_args()
    result = analyze(args.raw)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2)
    print(render_md(result))
    print("\n" + json.dumps(result["summary"], indent=1))
    print(f"\nSaved -> {args.out}")


if __name__ == "__main__":
    main()
