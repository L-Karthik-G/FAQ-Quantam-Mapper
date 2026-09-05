# Complete Benchmark Results — Data Provenance & Reproduction

> ⚠️ **Superseded-in-content notice.** Earlier revisions of this document carried a 36-case,
> K=5, `optimization_level=3` table with a 115-qubit Heavy-Hex topology that **contradicted**
> the current README (K=20, `optimization_level=1`, 127-qubit FakeBrisbane / 80-qubit synthetic grid).
> That table was removed so the repository reports a single, internally-consistent dataset.

The **authoritative, reproducible paired-seed dataset** for this project is produced by
`benchmarks/benchmark_eval.py` and written into the repository root as:

| File | Contents |
|:---|:---|
| `benchmarks/results/benchmark_eval_results.json` | Per-task/method mean SWAPs, 95% CI, and success counts (K=20 paired seeds) |
| `benchmarks/results/benchmark_eval_raw_seeds.json` | Raw per-seed logs (all 20 seeds × all methods) |
| `benchmarks/results/benchmark_ablation_results.json` | QAP-cost ablation table (`benchmarks/benchmark_ablations.py`) |
| `benchmarks/results/significance_results.json` | Paired Wilcoxon per row (`benchmarks/analyze_significance.py`) |
| `benchmarks/results/benchmark_fidelity_results.json` | SWAP + fidelity-loss proxy per method (`benchmarks/benchmark_fidelity.py`) |
| `benchmarks/results/benchmark_fidelity_comparison.json` | SWAP-delta vs fidelity-delta (`benchmarks/report_fidelity.py`) |
| `benchmarks/results/ablation_multicell_results.json` | Multi-cell, K=20 ablation of rows 1–3 (`benchmarks/ablation_multicell.py`) |

The full results tables derived from these files are published in the README:

- **Table 1 — IBM FakeBrisbane (127q Heavy-Hex)**: 13 tasks (Grover N=8/10/12, VQE N=10/20/50,
  GHZ N=50, QFT N=20, QAOA N=10/20, and 3 hand-crafted holdouts).
- **Table 2 — Synthetic Grid Topology (80q)**: 7 tasks (Grover N=8/10/12, VQE N=50, QFT N=20, and 2
  hand-crafted holdouts).
- **Ablation table**: QAP-cost level component ablations on Grover N=10 (IBM FakeBrisbane).

Metrics are **mean ± 95% CI** over the 20 paired seeds; every row compiled 20/20 successfully.

### Reproduction

```bash
# Python dependencies are managed with uv (see pyproject.toml + uv.lock)
uv sync

# Regenerate the QAP-cost ablation table (in-repo output)
uv run python benchmarks/benchmark_ablations.py

# Regenerate the paired-seed benchmark suite (in-repo output; slow — full routing)
uv run python benchmarks/benchmark_eval.py

# Paired significance (analysis-only) + fidelity proxy (heavy re-route):
uv run python benchmarks/analyze_significance.py
uv run python benchmarks/benchmark_fidelity.py 6 0   # ...remainder 0..5, then:
uv run python benchmarks/benchmark_fidelity.py --merge 6
uv run python benchmarks/report_fidelity.py
```

Significance and fidelity results (review points #2 and #5) are summarised in
[`reports/statistical_fidelity_analysis.md`](statistical_fidelity_analysis.md).

### Other result files

Root `*_results.json` files other than the three canonical files above reflect earlier,
mutually-inconsistent experiment rounds (different seeds, topologies, or
`optimization_level`). They are retained for history but are **not** the numbers reported in
the README. Do not mix them with the canonical dataset when reporting results.
