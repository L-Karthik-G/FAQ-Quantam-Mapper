"""Render the fidelity-aware comparison for the FAQ-Layout benchmark.

Reads `benchmark_fidelity_raw.json` (per-seed SWAP + fidelity proxies per method) produced by
`benchmark_fidelity.py --merge`, pairs default-vs-FAQ per seed, and reports for every task/row
both the SWAP-count delta and the fidelity-proxy delta. This makes explicit when a method wins
on SWAP count but ties/loses on the fidelity proxy (the real headline a fidelity-weighted method
should care about).

Outputs a markdown table and writes `benchmark_fidelity_comparison.json`.

Usage: uv run python benchmarks/report_fidelity.py
"""
from __future__ import annotations

import json
import os
from collections import OrderedDict
from typing import Dict, List

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")

PAIRS = [("sabre", "sabre_def", "faq_sabre"), ("tket", "tket_def", "faq_tket")]
METRICS = [("swaps", "mean SWAPs"), ("infidelity_sum", "mean infidelity proxy"),
           ("failure_prob", "mean failure prob.")]


def _row_key(r: Dict) -> tuple:
    return (r["task"], r["qubits"], r["arch"])


def build() -> List[Dict]:
    with open(os.path.join(RES, "benchmark_fidelity_raw.json")) as f:
        per_seed = json.load(f)
    # Group per-seed rows by (task, qubits, arch), preserving seed iteration order.
    cells: "OrderedDict[tuple, List[Dict]]" = OrderedDict()
    for r in per_seed:
        cells.setdefault(_row_key(r), []).append(r)

    rows = []
    for key, seed_rows in cells.items():
        first = seed_rows[0]
        rec = {"task": first["task"], "qubits": first["qubits"],
               "architecture": first["arch"]}
        for pair_name, base_m, faq_m in PAIRS:
            pair = {}
            for metric, _label in METRICS:
                try:
                    b = np.array([sr[base_m][metric] for sr in seed_rows])
                    a = np.array([sr[faq_m][metric] for sr in seed_rows])
                except KeyError:
                    pair[metric] = None
                    continue
                bmean = float(np.mean(b))
                pct = None if bmean == 0 else (float(np.mean(a)) - bmean) / abs(bmean) * 100.0
                pair[metric] = {
                    "base_mean": bmean,
                    "faq_mean": float(np.mean(a)),
                    "faq_minus_base": float(np.mean(a)) - bmean,
                    "pct_change": pct,
                }
            rec[pair_name] = pair
        rows.append(rec)
    return rows


def render_md(rows: List[Dict]) -> str:
    lines = []
    head = "| Task | Arch | N | SABRE ΔSWAP | SABRE Δinfid | SABRE Δfailprob | TKET ΔSWAP | TKET Δinfid | TKET Δfailprob |"
    lines.append(head)
    lines.append("|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|")
    for rec in rows:
        arch = "Brisbane" if "Brisbane" in rec["architecture"] else (
            "Synthetic grid" if "Rigetti" in rec["architecture"] else rec["architecture"])
        def cell(p):
            if p is None or p["swaps"] is None:
                return "—", "—", "—"
            ds = p["swaps"]["faq_minus_base"]
            s = (f"{ds:+.0f}" + (f" ({p['swaps']['pct_change']:+.0f}%)" if p['swaps']['pct_change'] is not None else ""))
            di = p["infidelity_sum"]["faq_minus_base"]
            i = f"{di:+.2f}" if abs(di) < 1000 else f"{di:+.1e}"
            df = p["failure_prob"]["faq_minus_base"]
            return s, i, f"{df:+.2e}"
        sc, si, sp = cell(rec["sabre"])
        tc, ti, tp = cell(rec["tket"])
        lines.append(f"| {rec['task']} | {arch} | {rec['qubits']} | {sc} | {si} | {sp} | {tc} | {ti} | {tp} |")
    return "\n".join(lines)


def main() -> None:
    rows = build()
    out = os.path.join(RES, "benchmark_fidelity_comparison.json")
    with open(out, "w") as f:
        json.dump(rows, f, indent=2)
    print(render_md(rows))
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
