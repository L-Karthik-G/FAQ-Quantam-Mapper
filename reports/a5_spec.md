# A5 — Multi-cell, multi-seed component ablation (rows 1–3)

**Status: DONE — executed at K=20 over the 5 authorized cells. See
[`a5_results.md`](a5_results.md) for the completed analysis and
`../benchmarks/results/ablation_multicell_results.json` for the raw per-seed data.**

## Question

The single-cell, single-seed ablation in `README.md` (§ Component Ablations) shows rows
2 (random multi-start) vs 3 (structured Gaussian multi-start) both ≈ equal *after* 2-opt
polish (86.99 vs 88.31 on that one Grover-N10 example) — i.e. the "structured Gaussian beats
random restarts" claim has **no statistical power** behind it. A5 re-runs exactly rows 1–3 of
that table across a handful of the same cells already in Tables 1–2, with many seeds and
mean±95% CI, to answer: **does Gaussian multi-start ever actually beat random multi-start once
powered, or should the method ship as random-multi-start + 2-opt?**

## Scope (bounded, no new benchmark sweep)

* **Rows (configurations)** — mirror the existing ablation exactly:
  1. `AdaptiveFAQSolver(num_starts=1, start_mode="barycenter", enable_2opt=True)`  — deterministic single start
  2. `AdaptiveFAQSolver(num_starts=5, start_mode="random",   enable_2opt=True)`    — random multi-start (K=5)
  3. `AdaptiveFAQSolver(num_starts=5, start_mode="gaussian", enable_2opt=True)`    — structured Gaussian (ours, K=5)
* **Cells** — reuse existing benchmark cells (same circuits + `FakeBrisbane`/synthetic-80
  snapshots already in Tables 1–2), **not** new circuits. Suggested, on IBM FakeBrisbane where
  the real error profile makes the QAP objective meaningful:
  Grover N=8 / N=10 / N=12, QAOA N=10 / N=20, QFT N=20, Random 3-regular N=20.
* **Seeds** — a CLI-selected K (default 20, matching the main tables). Rows 2 & 3 vary with seed;
  row 1 (single barycenter) is deterministic and reported as a point value.
* **Metric** — the post-2-opt **QAP polished cost** (the objective the pipeline minimizes and
  hands to routing), per seed. Report mean ± 95% CI per (cell, row), plus a **paired Wilcoxon**
  (row 3 vs row 2) on the per-seed differences per cell (and an across-cells FDR if run over
  multiple cells).

## Cost estimate

Each multi-start (K=5, 2-opt over the M-padded permutation) solve ≈ **5 s** for Grover-N10
Brisbane (M=127). Rows 2+3 over K=20 seeds ≈ 200 s per cell; rows 1 adds one ~5 s solve. A
7-cell Brisbane run ≈ 1,400 s ≈ 23 min single-core. `--parallel` splits cells across a strided
multiprocess like `benchmark_fidelity.py`, cutting wall time to a few minutes on ≥4 cores.

## Deliverable

`benchmarks/results/ablation_multicell_results.json` (per cell/row: mean, ci95, per-seed
costs) plus a printed table. Interpretation: if row 3 is **not** significantly better than row
2 (paired, powered) on the cells tested, the honest recommendation is to ship **random
multi-start + 2-opt** (row 2) and drop the Gaussian machinery — or, if the effect needs the
Gaussian but power is marginal, to report that clearly.

## Run (after approval)

```bash
uv run python benchmarks/ablation_multicell.py --seeds 20
uv run python benchmarks/ablation_multicell.py --seeds 20 --parallel 4   # optional
```
