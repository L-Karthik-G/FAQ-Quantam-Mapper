"""Paired significance testing for the FAQ-Layout benchmark.

Reads the canonical per-seed log (`benchmarks/results/benchmark_eval_raw_seeds.json`),
reconstructs the per-seed SWAP counts for the four router methods per task, and runs a
**paired Wilcoxon signed-rank test** on the K per-seed differences for each router pair:

    (SABRE default,  FAQ + SABRE)   -> pair "sabre"
    (PyTKET default, FAQ + PyTKET)  -> pair "tket"

A paired signed-rank test is used (rather than comparing summary means / CIs) because the
design is paired-by-seed and SWAP counts are small, skewed, often zero-inflated integers for
which a paired t-test is inappropriate. A p-value and a significance flag at alpha=0.05 are
reported next to every "which method has the lower mean SWAP" decision, replacing the previous
"Lower-SWAP method" claims that were made without a test.

Determinism handling: a method arm whose 20 seeds produce an identical value is *deterministic*
(no within-arm sampling variance). The difference between two such arms is then constant, so a
rank test is undefined for that row; this is reported explicitly instead of fabricating a p-value.
Rows whose difference vector is constant (deterministic-vs-deterministic, equal) are reported as
EXACT ties.

Usage:
    uv run python benchmarks/analyze_significance.py [--raw benchmarks/results/benchmark_eval_raw_seeds.json] [--alpha 0.05]
Output: benchmarks/results/significance_results.json and a printed markdown table.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import OrderedDict, defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import stats

ROUTER_PAIRS = [("sabre", "sabre_def", "faq_sabre"), ("tket", "tket_def", "faq_tket")]


def _row_key(task: str, qubits: int, arch: str) -> Tuple[str, int, str]:
    return (task, qubits, arch)


def load_paired_swaps(raw_logs: List[Dict]) -> "OrderedDict[Tuple, Dict[str, List[int]]]":
    """Group raw seed rows by task and method, preserving seed order.

    Returns { (task,qubits,arch): {"sabre_def": [swaps...], ...} } aligned by the SEEDS
    iteration order recorded in the log (rows appear in seed 0..19 order per method).
    """
    cells: "OrderedDict[Tuple, Dict[str, List[int]]]" = OrderedDict()
    by_key: Dict[Tuple, Dict[str, Dict[int, int]]] = defaultdict(lambda: defaultdict(dict))
    for row in raw_logs:
        if row.get("status") != "success":
            continue
        key = _row_key(row["task"], row["qubits"], row["arch"])
        by_key[key][row["method"]][int(row["seed"])] = int(row["swaps"])

    for key in sorted(by_key.keys()):
        methods = OrderedDict()
        for seed in sorted({s for m in by_key[key].values() for s in m}):
            for meth, seed_map in by_key[key].items():
                methods.setdefault(meth, []).append(seed_map.get(seed, np.nan))
        cells[key] = methods
    return cells


def test_pair(base: List[float], faq: List[float], alpha: float) -> Dict:
    """Wilcoxon signed-rank test on K per-seed differences (faq - base).

    Returns a record with test stat, p-value, significance flag, and determinism diagnosis.
    """
    base_a = np.asarray(base, dtype=float)
    faq_a = np.asarray(faq, dtype=float)
    diff = faq_a - base_a

    n = int(len(diff))
    base_det = float(np.ptp(base_a)) == 0.0 and n > 0
    faq_det = float(np.ptp(faq_a)) == 0.0 and n > 0
    diff_const = float(np.ptp(diff)) == 0.0 and n > 0

    rec = {
        "n_paired": n,
        "mean_diff_faq_minus_base": float(np.mean(diff)),
        "median_diff_faq_minus_base": float(np.median(diff)),
        "base_deterministic": base_det,
        "faq_deterministic": faq_det,
    }

    # Exact constant difference (both arms deterministic, or identical samples): no rank test.
    if n == 0 or diff_const:
        rec.update(
            {
                "test": "exact_constant_difference",
                "statistic": None,
                "p_value": None,
                "significant": None,
                "note": (
                    "constant per-seed difference (deterministic arm(s)) "
                    "- rank test undefined"
                ),
            }
        )
        return rec

    # Default zero handling drops zero-difference pairs; that is appropriate here because a
    # zero difference carries no rank information. We surface how many were dropped.
    n_zero = int(np.sum(diff == 0.0))
    res = stats.wilcoxon(diff, zero_method="wilcox", alternative="two-sided")
    p = float(res.pvalue)
    rec.update(
        {
            "test": "wilcoxon_signed_rank",
            "statistic": float(res.statistic),
            "p_value": p,
            "significant": bool(p < alpha),
            "alpha": alpha,
            "n_zero_diffs_dropped": n_zero,
            "note": (
                "deterministic base arm" if base_det
                else ("deterministic faq arm" if faq_det else "both arms vary across seeds")
            ),
        }
    )
    return rec


def analyze(raw_path: str, alpha: float) -> Tuple[List[Dict], List[Dict]]:
    """Returns (row_records, summary) lists."""
    with open(raw_path) as f:
        raw_logs = json.load(f)
    cells = load_paired_swaps(raw_logs)

    rows: List[Dict] = []
    for key, methods in cells.items():
        task, qubits, arch = key
        rec = {
            "task": task,
            "qubits": qubits,
            "architecture": arch,
        }
        for pair_name, base_m, faq_m in ROUTER_PAIRS:
            base = methods.get(base_m, [])
            faq = methods.get(faq_m, [])
            if not base or not faq:
                rec[pair_name] = {"test": "missing_data", "note": "arm absent from raw log"}
                continue
            pair_rec = test_pair(base, faq, alpha)
            # Add per-method mean for readability.
            pair_rec["base_mean_swaps"] = float(np.mean(base)) if base else None
            pair_rec["faq_mean_swaps"] = float(np.mean(faq)) if faq else None
            rec[pair_name] = pair_rec
        rows.append(rec)

    # Benjamini-Hochberg FDR across all tested comparisons (both pairs, all tasks).
    # Only rows with an actual p-value are in the multiple-testing family.
    pvals = [rr[pn]["p_value"] for rr in rows for pn, _, _ in ROUTER_PAIRS
             if rr[pn].get("p_value") is not None]
    bh = benjamini_hochberg(pvals)
    idx = 0
    for rr in rows:
        for pn, _, _ in ROUTER_PAIRS:
            if rr[pn].get("p_value") is None:
                continue
            q = bh[idx]
            idx += 1
            rr[pn]["q_value_bh"] = q
            rr[pn]["significant_bh"] = bool(q < alpha)
            # Also record whether the BH decision changes the raw-alpha decision.
            if rr[pn]["significant"] is not None:
                rr[pn]["changed_by_bh"] = bool(rr[pn]["significant"] != rr[pn]["significant_bh"])

    # Count significant improvements per router pair across tasks.
    summary = []
    for pair_name, _, _ in ROUTER_PAIRS:
        sig_faq_raw = sum(1 for r in rows if r[pair_name].get("significant") is True
                          and r[pair_name].get("mean_diff_faq_minus_base", 0) < 0)
        sig_base_raw = sum(1 for r in rows if r[pair_name].get("significant") is True
                           and r[pair_name].get("mean_diff_faq_minus_base", 0) > 0)
        sig_faq_bh = sum(1 for r in rows if r[pair_name].get("significant_bh") is True
                         and r[pair_name].get("mean_diff_faq_minus_base", 0) < 0)
        sig_base_bh = sum(1 for r in rows if r[pair_name].get("significant_bh") is True
                          and r[pair_name].get("mean_diff_faq_minus_base", 0) > 0)
        untested = sum(1 for r in rows if r[pair_name].get("p_value") is None)
        summary.append(
            {
                "pair": pair_name,
                "tasks_tested": sum(1 for r in rows if r[pair_name].get("p_value") is not None),
                "significant_faq_lower_raw": sig_faq_raw,
                "significant_base_lower_raw": sig_base_raw,
                "significant_faq_lower_bh": sig_faq_bh,
                "significant_base_lower_bh": sig_base_bh,
                "not_significant_raw": sum(1 for r in rows if r[pair_name].get("significant") is False),
                "not_significant_bh": sum(1 for r in rows if r[pair_name].get("significant_bh") is False),
                "n_multiple_testing": len(pvals),
                "untested_constant": untested,
            }
        )
    return rows, summary


def benjamini_hochberg(pvals: List[float], alpha: float = 0.05) -> List[float]:
    """Returns BH-adjusted q-values (step-up) for a list of p-values.

    For ascending-ordered p-values p_(1) <= ... <= p_(m), the BH procedure sets
        q_(m) = p_(m)
        q_(i) = min( q_(i+1),  m * p_(i) / i )   for i = m-1 ... 1
    so iteration runs from the largest p downward.
    """
    n = len(pvals)
    if n == 0:
        return []
    # ascending order of original indices by their p-value
    order = sorted(range(n), key=lambda i: pvals[i])
    q = [0.0] * n
    prev = float("inf")
    # iterate from the largest p-value (rank n) down to the smallest (rank 1)
    for pos in range(n - 1, -1, -1):
        i = order[pos]          # original index
        rank = pos + 1          # 1-based ascending rank
        qv = n * pvals[i] / rank
        q[i] = min(qv, prev)
        prev = q[i]
    return q


def fmt_p(p: Optional[float]) -> str:
    if p is None:
        return "—"
    return f"{p:.4f}" if p >= 1e-4 else f"{p:.2e}"


def render_markdown(rows: List[Dict]) -> str:
    lines = []
    lines.append("| Task | Arch | N | SABRE lower? | p | q(BH) | Sig@FDR | TKET lower? | p | q(BH) | Sig@FDR |")
    lines.append("|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|")
    for r in rows:
        sabre, tket = r["sabre"], r["tket"]
        arch = "Brisbane" if "Brisbane" in r["architecture"] else (
            "Synthetic grid" if "Rigetti" in r["architecture"] else r["architecture"]
        )
        def cell(pair: Dict) -> Tuple[str, str, str, str]:
            if pair.get("p_value") is None:
                winner = "tie/det" if pair.get("mean_diff_faq_minus_base") == 0 else "det"
                return winner, "—", "—", "—"
            md = pair["mean_diff_faq_minus_base"]
            lower = "FAQ" if md < 0 else ("base" if md > 0 else "tie")
            sig = "yes" if pair["significant_bh"] else "no"
            q = pair.get("q_value_bh")
            qs = "—" if q is None else (f"{q:.4f}" if q >= 1e-4 else f"{q:.2e}")
            return lower, fmt_p(pair["p_value"]), qs, sig
        sl, sp, sq, ss = cell(sabre)
        tl, tp, tq, ts = cell(tket)
        lines.append(
            f"| {r['task']} | {arch} | {r['qubits']} | {sl} | {sp} | {sq} | {ss} "
            f"| {tl} | {tp} | {tq} | {ts} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    here = os.path.dirname(os.path.abspath(__file__))
    default_raw = os.path.join(here, "results", "benchmark_eval_raw_seeds.json")
    parser.add_argument("--raw", default=default_raw)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--out", default=os.path.join(here, "results", "significance_results.json"))
    args = parser.parse_args()

    if os.path.dirname(args.raw) not in sys.path and os.path.dirname(args.raw):
        sys.path.insert(0, os.path.dirname(args.raw))

    rows, summary = analyze(args.raw, args.alpha)

    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    payload = {"alpha": args.alpha, "rows": rows, "summary": summary}
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2)

    print(render_markdown(rows))
    print("\n=== Summary (FDR-adjusted at alpha=%.2g over %d tests) ===" % (
        args.alpha, summary[0]["n_multiple_testing"] if summary else 0))
    for s in summary:
        print(
            f"{s['pair']}: {s['tasks_tested']} tested, "
            f"raw-alpha sig: {s['significant_faq_lower_raw']} FAQ-lower / "
            f"{s['significant_base_lower_raw']} base-lower; "
            f"BH-FDR sig: {s['significant_faq_lower_bh']} FAQ-lower / "
            f"{s['significant_base_lower_bh']} base-lower; "
            f"{s['not_significant_bh']} not sig (BH), "
            f"{s['untested_constant']} untested (constant/det)"
        )
    print(f"\nSaved -> {args.out}")


if __name__ == "__main__":
    main()
