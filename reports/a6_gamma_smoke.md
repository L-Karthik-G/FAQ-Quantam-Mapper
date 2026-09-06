# A6 — Gamma decay sensitivity: Phase-0 smoke report

**Status: SMOKE COMPLETE — full sweep NOT run (execution gate).** This report is the
feasibility/correctness gate described in [`a6_gamma_spec.md`](a6_gamma_spec.md). It is
**not inferential**: no gamma "winner" is selected or implied here.

## Setup (exact cell)

| Element | Value |
|:--|:--|
| Cell | `vqe50-grid` — VQE (RealAmplitudes) N=50, synthetic 8×10 grid (80q) — the designated variational/repeated-layer cell |
| Gamma values | {0.7, 0.9, 1.0} |
| Seeds | K = 20 (`0..19`), **identical seed IDs reused across gamma values** (matched blocks) |
| Routers | Qiskit SABRE downstream (`optimization_level=1`, `seed_transpiler=s`); PyTKET `RoutingPass` |
| Mapper (fixed) | `AdaptiveFAQSolver(num_starts=5, start_mode="random", enable_2opt=True)` |
| Runs | 3 gamma × 20 seeds × 2 routers = **120 runs, 120/120 succeeded** |

Runner: `benchmarks/benchmark_gamma.py`; raw per-seed data:
`benchmarks/results/a6_gamma_smoke_raw.json` (not just means).

## Checks performed (spec Phase-0 purposes)

1. **Gamma reaches Matrix A** — Matrix-A sanity diagnostics are deterministic per gamma
   (single value across all 40 rows of a gamma) and move monotonically with gamma:

   | gamma | n_layers | total weight | min nonzero | max nonzero |
   |:--:|:--:|:--:|:--:|:--:|
   | 0.7 | 75 | 1.220 | 0.000 | 0.183 |
   | 0.9 | 75 | 20.045 | 0.006 | 1.008 |
   | 1.0 | 75 | 294.0 | **3.0** | **3.0** (uniform: min == max) |

   `gamma=1.0` gives uniform interaction weights (every pair weighted by its raw count, 3.0
   here) as expected; the decayed gammas shrink total weight strongly (gamma=0.5 → weight
   0.125^… earlier VQE-N10 check: total 0.13). No plateau effect applies: both smoke cells
   have ≤ 100 DAG layers (the plateau only starts above the 100-layer threshold).
2. **Identical seeds across gammas** — every gamma used the same 20 seed IDs; per-seed parity
   with the committed random-init canonical dataset at `gamma=0.9` is exact
   (`faq_sabre` mean 49.50 = canonical 49.5; `faq_tket` 0.90 = canonical 0.9; seed-level
   spot checks matched 1:1), confirming both the gamma-threading plumbing and seed reuse.
3. **Artifacts recorded** — per row: gamma, cell, router, seed, mapper config, SWAP count,
   routed depth, total 2q count, prep seconds, QAP cost, layer count, Matrix-A diagnostics.
4. **Wall-clock** — 120 runs in 241 s ≈ **2.0 s/run average** on this machine (FAQ prep
   ~1.9 s, M=80). Brisbane cells (M=127) run slower (~3–5 s/run including routing), so the
   full-sweep estimate below uses ~3.5 s/run.
5. **SWAP-count variation** (descriptive only — **no inferential claim**):

   | Router | gamma=0.7 | gamma=0.9 (ref) | gamma=1.0 |
   |:--|:--:|:--:|:--:|
   | SABRE | 70.30 ± 8.39 | 49.50 ± 11.07 | 27.70 ± 4.54 |
   | PyTKET | 1.00 ± 0.48 | 0.90 ± 0.48 | 0.80 ± 0.47 |

   The SABRE arm shows substantial between-gamma spread on this cell (observed means from
   ~28 to ~70) with wide per-seed variation (seed-level SABRE values 5–101 at gamma=0.9), so
   the planned repeated-measures analysis should have material to test on the SABRE arm. The
   PyTKET arm sits at the routing floor (0–2 SWAPs on nearly every seed) on this cell — it
   has no headroom here, so PyTKET-arm sensitivity will have to come from cells with room
   (e.g. Grover rows); this is a per-cell property to report, not an implementation problem.
6. **Implementation/reproducibility** — deterministic A per gamma; exact parity with the
   committed dataset at the reference gamma; 0 failures; mapper config recorded in the JSON.

## Feasibility recommendation

**Full sweep is feasible as planned.** At ~3.5 s/run average over the mixed cells, the
authorized grid (9 gamma × 5 cells × 20 seeds × 2 routers = 1,800 runs) is ≈ 105 minutes
single-process. Slicing the run across 6 worker processes with `--slice K/6` (each process
writes its own partial file) brings wall time to ≈ 20 minutes, well within the budget used by
previous A-series sweeps. No reduction or modification of the authorized grid is recommended.

## Proposed next step (subject to review)

Proceed to Phase 1 with the **preregistered** configuration from
[`a6_gamma_spec.md`](a6_gamma_spec.md) — unchanged: gamma grid
{0.50, 0.60, 0.70, 0.80, 0.85, 0.90(ref), 0.95, 0.98, 1.00}, the five A5 cells, K=20 matched
seeds, both routers, Friedman → (gated) Wilcoxon-vs-0.90 → BH analysis on SWAP count. Raw data
to `benchmarks/results/a6_gamma_results.json`, then the results report
`reports/a6_gamma_results.md`.

**Execution gate: this smoke report must be reviewed before any Phase-1 run starts.**
