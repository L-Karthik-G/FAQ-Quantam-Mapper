"""Render README Tables 1-2 rows from the canonical benchmark + significance datasets.

Tables 1-2 in README.md were historically hand-maintained, which is how a stale
Gaussian-init dataset ended up documented next to the shipped random-init default. This
renderer is the reproducible source for those tables: it reads

  benchmarks/results/benchmark_eval_results.json      (means / 95% CI per task/method)
  benchmarks/results/benchmark_eval_raw_seeds.json    (per-seed logs; FAQ prep. seconds)
  benchmarks/results/significance_results.json        (paired Wilcoxon + BH q per pair)

and prints the exact markdown rows used in README.md (Table 1 = FakeBrisbane rows,
Table 2 = synthetic-grid rows, in BENCHMARK_TASKS order), plus a per-row marker (dagger)
on every "Lower-SWAP method" winner whose lower-mean claim is **not** significant after
the BH FDR correction (q >= alpha) -- the table-level caveat that used to live only in the
separate significance report.

Usage:
    uv run python benchmarks/render_tables.py
    # prints both tables as markdown; redirect to a file to paste into README.md
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

# Canonical task list (identical to benchmark_eval.BENCHMARK_TASKS); kept local so this
# renderer needs no qiskit/pytket imports and runs in any plain-python env.
BENCHMARK_TASKS = [
    # (arch, bench_key, bench_label, n_qubits, suite_type)
    ("IBM_Eagle_127_Brisbane", "grover", "Grover's Search", 8, "mqt"),
    ("IBM_Eagle_127_Brisbane", "grover", "Grover's Search", 10, "mqt"),
    ("IBM_Eagle_127_Brisbane", "grover", "Grover's Search", 12, "mqt"),
    ("IBM_Eagle_127_Brisbane", "vqe_real_amp", "VQE (RealAmplitudes)", 10, "mqt"),
    ("IBM_Eagle_127_Brisbane", "vqe_real_amp", "VQE (RealAmplitudes)", 20, "mqt"),
    ("IBM_Eagle_127_Brisbane", "vqe_real_amp", "VQE (RealAmplitudes)", 50, "mqt"),
    ("IBM_Eagle_127_Brisbane", "ghz", "GHZ State", 50, "mqt"),
    ("IBM_Eagle_127_Brisbane", "qft", "QFT", 20, "mqt"),
    ("IBM_Eagle_127_Brisbane", "qaoa", "QAOA", 10, "mqt"),
    ("IBM_Eagle_127_Brisbane", "qaoa", "QAOA", 20, "mqt"),
    ("IBM_Eagle_127_Brisbane", "ripple_carry_adder", "Ripple-Carry Adder (Holdout)", 20, "holdout"),
    ("IBM_Eagle_127_Brisbane", "qram_bucket_brigade", "QRAM Decoder (Holdout)", 20, "holdout"),
    ("IBM_Eagle_127_Brisbane", "random_3_regular", "Random 3-Regular (Holdout)", 20, "holdout"),
    ("Rigetti_Grid_80", "grover", "Grover's Search", 8, "mqt"),
    ("Rigetti_Grid_80", "grover", "Grover's Search", 10, "mqt"),
    ("Rigetti_Grid_80", "grover", "Grover's Search", 12, "mqt"),
    ("Rigetti_Grid_80", "vqe_real_amp", "VQE (RealAmplitudes)", 50, "mqt"),
    ("Rigetti_Grid_80", "qft", "QFT", 20, "mqt"),
    ("Rigetti_Grid_80", "ripple_carry_adder", "Ripple-Carry Adder (Holdout)", 20, "holdout"),
    ("Rigetti_Grid_80", "qram_bucket_brigade", "QRAM Decoder (Holdout)", 20, "holdout"),
]

SUITE_LABEL = {"mqt": "MQT-Bench", "holdout": "Hand-Crafted"}
HEADER = "| Benchmark Circuit | Suite | Scale $N$ | **SABRE Default** | **FAQ+SABRE** | **Δ (SABRE)** | **PyTKET Default** | **FAQ+PyTKET** | **Δ (PyTKET)** | **FAQ Preproc. (s)** | **Lower-SWAP method** |"
SEPARATOR = "|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|"
ARCH_LABEL = {
    "IBM_Eagle_127_Brisbane": "FakeBrisbane (IBM, 127q)",
    "Rigetti_Grid_80": "Synthetic grid (80q)",
}


def _fmt_mean_ci(mean: Optional[float], ci: Optional[float]) -> str:
    if mean is None:
        return "—"
    return f"{mean:.1f} ± {(ci if ci is not None else 0.0):.1f}"


def _delta_cell(faq_mean: float, base_mean: float) -> str:
    d = faq_mean - base_mean
    if abs(d) < 0.05:
        return "+0.0 (n/a)"
    pct = f"({100.0 * d / base_mean:+.1f}%)" if base_mean > 0 else "(n/a)"
    return f"{d:+.1f} {pct}"


def _winner(faq_mean: float, base_mean: float, faq_name: str, base_name: str) -> Tuple[str, float]:
    """Returns (winner label, signed diff faq-base). Tie -> ('Tie', 0.0)."""
    d = faq_mean - base_mean
    if abs(d) < 1e-9:
        return "Tie", 0.0
    return (faq_name if d < 0 else base_name), d


def load_data() -> Tuple[Dict, Dict, Dict]:
    here = os.path.dirname(os.path.abspath(__file__))
    res_dir = os.path.join(here, "results")
    with open(os.path.join(res_dir, "benchmark_eval_results.json")) as f:
        results = json.load(f)
    with open(os.path.join(res_dir, "benchmark_eval_raw_seeds.json")) as f:
        raw = json.load(f)
    with open(os.path.join(res_dir, "significance_results.json")) as f:
        sig = json.load(f)

    # prep-time mean per task (identical FAQ solve time for the sabre/tket FAQ arms;
    # average over both, matching how the README column was historically produced)
    prep: Dict[Tuple[str, int, str], float] = {}
    for e in raw:
        if e.get("prep_time_sec") is not None:
            key = (e["task"], int(e["qubits"]), e["arch"])
            prep.setdefault(key, []).append(float(e["prep_time_sec"]))  # type: ignore[arg-type]
    prep = {k: sum(v) / len(v) for k, v in prep.items()}

    rec_by_key: Dict[Tuple[str, int, str], Dict] = {
        (r["benchmark_label"], int(r["qubits"]), r["architecture"]): r for r in results
    }
    # significance rows indexed the same way
    sig_by_key: Dict[Tuple[str, int, str], Dict] = {
        (r["task"], int(r["qubits"]), r["architecture"]): r for r in sig["rows"]
    }
    return rec_by_key, prep, sig_by_key


def render_table_rows(rec_by_key, rows, prep, sig, alpha: float) -> Tuple[List[str], List[str]]:
    """Returns (markdown rows, footnote lines).

    Args:
        rec_by_key: task-key -> per-method summary record (from benchmark_eval_results.json)
        rows: list of (arch, bench_key, bench_label, n_qubits, suite_type) in display order.
        prep: task-key -> mean FAQ prep seconds.
        sig: task-key -> significance record with per-pair BH decisions.
    """
    out, footnotes = [], []
    marked = 0
    for (arch, _bk, label, n, suite) in rows:
        key = (label, n, arch)
        rec = rec_by_key.get(key)
        if rec is None:
            out.append(f"| **{label.replace(' (Holdout)', '')}** | {SUITE_LABEL[suite]} | {n} | — | — | — | — | — | — | — | — |")
            continue
        sd = rec["sabre_default"]
        fs = rec["faq_sabre"]
        td = rec["tket_default"]
        ft = rec["faq_tket"]
        prep_s = prep.get(key)
        prep_cell = "—" if prep_s is None else f"{prep_s:.3f}"

        cells = []
        for pair_name, faq, base, faq_lbl, base_lbl in (
            ("sabre", fs, sd, "FAQ+SABRE", "SABRE Def"),
            ("tket", ft, td, "FAQ+PyTKET", "PyTKET Def"),
        ):
            win, d = _winner(faq["mean_swaps"], base["mean_swaps"], faq_lbl, base_lbl)
            mark = ""
            if win != "Tie":
                srow = sig.get(key, {}).get(pair_name)
                # marker: a lower-mean claim that a BH-corrected test does not support
                if srow and srow.get("p_value") is not None and srow.get("q_value_bh") is not None:
                    if srow["q_value_bh"] >= alpha and srow["mean_diff_faq_minus_base"] != 0:
                        mark = "†"
                        marked += 1
            cells.append(win + mark)

        display_label = label.replace(" (Holdout)", "")
        sabre_def_c = _fmt_mean_ci(sd["mean_swaps"], sd["ci95_swaps"])
        faq_sabre_c = _fmt_mean_ci(fs["mean_swaps"], fs["ci95_swaps"])
        tket_def_c = _fmt_mean_ci(td["mean_swaps"], td["ci95_swaps"])
        faq_tket_c = _fmt_mean_ci(ft["mean_swaps"], ft["ci95_swaps"])
        ds = _delta_cell(fs["mean_swaps"], sd["mean_swaps"])
        dt = _delta_cell(ft["mean_swaps"], td["mean_swaps"])
        row = (
            f"| **{display_label}** | {SUITE_LABEL[suite]} | {n} | {sabre_def_c} | {faq_sabre_c} | "
            f"{ds} | {tket_def_c} | {faq_tket_c} | {dt} | {prep_cell} | {cells[0]} / {cells[1]} |"
        )
        out.append(row)

    if marked:
        footnotes.append(
            "**† Lower mean on that router pair is *not* significant after the "
            "Benjamini–Hochberg FDR correction (q ≥ 0.05); see "
            "[`benchmarks/results/significance_results.json`](benchmarks/results/significance_results.json) "
            "and [`reports/statistical_fidelity_analysis.md`](reports/statistical_fidelity_analysis.md).**"
        )
    return out, footnotes


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--alpha", type=float, default=0.05)
    args = ap.parse_args()

    rec_by_key, prep, sig = load_data()
    table_rows = {"IBM_Eagle_127_Brisbane": [], "Rigetti_Grid_80": []}
    # collect per-arch rows in BENCHMARK_TASKS order
    ordered = [(a, bk, lbl, n, s) for (a, bk, lbl, n, s) in BENCHMARK_TASKS]
    for arch in ("IBM_Eagle_127_Brisbane", "Rigetti_Grid_80"):
        arch_tasks = [t for t in ordered if t[0] == arch]
        rows_md, notes = render_table_rows(rec_by_key, arch_tasks, prep, sig, args.alpha)
        print(f"### Table ({arch}) -- {len(arch_tasks)} rows, {len(notes)} footnote(s)")
        print(HEADER)
        print(SEPARATOR)
        for r in rows_md:
            print(r)
        for n in notes:
            print()
            print(n)
        print()
