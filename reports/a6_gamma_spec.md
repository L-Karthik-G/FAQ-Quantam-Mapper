# A6 — Gamma decay sensitivity (spec / preregistration)

**Status: SPEC — preregistration recorded before any execution.**

## Question

The FAQ mapper builds the circuit interaction matrix `A` in Module A with a temporal
interaction decay `weight = gamma ** layer`. The shipped default `gamma = 0.9` is a heuristic
that has never been validated against downstream routing performance.

> Does the interaction-decay parameter `gamma` materially affect downstream routing
> performance (post-routing SWAP count) when using the current **random multi-start** FAQ mapper?

A6 is about `gamma` only. The Gaussian-vs-random initialization question (A5) is **not**
re-opened: `start_mode="random"` (K=5 starts, 2-opt enabled) is fixed throughout.

## Hypotheses (preregistered)

* **H1 (primary):** for at least one circuit/router cell, the nine tested `gamma` values do
  not all produce the same SWAP-count distribution (Friedman omnibus rejects).
* **H0:** within a cell, the nine gamma conditions are exchangeable per seed (Friedman
  accepts) → **no post-hoc gamma-vs-0.9 significance claims for that cell**.

A null result is a valid outcome. No gamma is declared "best" from observed means alone.

## Reference condition

`gamma = 0.90` is the **reference/default level**, not an assumed optimum. All post-hoc
comparisons are against 0.90; the experiment does not assume 0.90 is optimal.

## Authorized cell list (recorded before execution; reuses the A5 cells)

These are the five A5 cells (same circuits + the same `FakeBrisbane` / synthetic-80
topology snapshots as Tables 1–2):

| # | Label | Arch | Circuit (bench key) | N | Suite |
|:--|:--|:--|:--|:--:|:--|
| 1 | grover10-bris | `IBM_Eagle_127_Brisbane` | `grover` (Grover's Search) | 10 | mqt |
| 2 | vqe50-grid | `Rigetti_Grid_80` (synthetic 8×10; NOT a real Rigetti device) | `vqe_real_amp` (VQE RealAmplitudes) | 50 | mqt |
| 3 | qram20-bris | `IBM_Eagle_127_Brisbane` | `qram_bucket_brigade` (QRAM Decoder holdout) | 20 | holdout |
| 4 | grover12-bris | `IBM_Eagle_127_Brisbane` | `grover` (Grover's Search) | 12 | mqt |
| 5 | vqe10-bris | `IBM_Eagle_127_Brisbane` | `vqe_real_amp` (VQE RealAmplitudes) | 10 | mqt |

Rationale: reuses the A5 cells (circuit diversity: two search workloads, two
variational/repeated-layer workloads — the family where temporal decay has a mechanism — and a
structural holdout; VQE-N50 synthetic grid is the designated variational cell for the smoke
test). Circuit-family-specific interpretation is reported where the data supports it.

## Gamma grid (full sweep, Phase 1)

```
gamma ∈ {0.50, 0.60, 0.70, 0.80, 0.85, 0.90(ref), 0.95, 0.98, 1.00}
```

Spans aggressive decay (0.50) → moderate (0.70–0.80) → current default (0.90) → weak decay
(0.95–0.98) → no decay (1.00).

## Seeds and pairing

* K = 20 seeds, `seed ∈ {0, …, 19}` (subject to feasibility confirmation in the smoke report).
* **Matched blocks:** the same seed IDs are reused for every gamma value within a cell
  (cell X, seed s: one run per gamma). Gamma/seed combinations are **not** treated as
  independent samples; the seed is the repeated-measures unit.

## Router conditions (held fixed)

1. FAQ layout → Qiskit SABRE downstream routing (`optimization_level=1`, `seed_transpiler=s`,
   FAQ layout hard-constrained as `initial_layout` — the canonical FAQ+SABRE arm).
2. FAQ layout → PyTKET `RoutingPass` downstream routing (the canonical FAQ+PyTKET arm).

Random multi-start (K=5, 2-opt) is the mapper configuration in both arms. Gaussian-based
historical harnesses (`start_mode="gaussian"`) are **not** modified.

## Experimental scale (planned, subject to smoke-test feasibility review)

```
9 gamma × 5 cells × 20 seeds × 2 routers = 1,800 routing runs
```

Any reduction/modification to this grid must be documented **before** the full run and must not
be selected from observed full-run outcomes.

## Statistical analysis plan (preregistered)

1. **Step 1 — Friedman omnibus** per (circuit × router) cell over the 9 gamma conditions, seed
   = block. If not significant for a cell → no post-hoc claims for that cell.
2. **Step 2 — paired Wilcoxon** only for cells that pass Step 1, comparing each non-reference
   gamma vs `0.90` on per-seed SWAP differences:
   `{0.50, 0.60, 0.70, 0.80, 0.85, 0.95, 0.98, 1.00} vs 0.90` (8 comparisons; no all-pairs).
3. **Step 3 — Benjamini–Hochberg FDR** across the *complete* family of post-hoc comparisons
   actually performed after the Step-1 gates (all gated cells × routers × up-to-8
   comparisons; nothing selectively excluded).
4. **Effect size & practical significance:** report per comparison raw p, BH q, effect size
   appropriate to the paired analysis, direction and practical magnitude. Distinguish
   *statistically significant* from *practically meaningful*; large-but-non-significant effects
   are reported as uncertain, not as wins.

Primary metric: post-routing **SWAP count** (only metric receiving significance claims).
Secondary metrics collected descriptively only: routed circuit depth, total two-qubit gate
count, FAQ prep seconds, Matrix-A diagnostics.

## Matrix-A sanity diagnostics (recorded per condition)

gamma, circuit layer count, total matrix weight (Σ A), nonzero interaction count, min and max
nonzero interaction weight. Expected pattern e.g. `gamma=1.00` → all-ones weights (subject to
the deep-circuit plateau rule: for circuits with > 100 DAG layers the first `plateau_length=20`
layers are un-decayed at weight 1.0), `gamma=0.50` → 1, 0.5, 0.25, …; `gamma=0.90` → 1, 0.9,
0.81, …. These are sanity diagnostics, not outcomes.

## Implementation & reproduction record

Per (cell, gamma, router, seed) the raw log stores: gamma, cell identifier (arch/bench/N),
router, seed, mapper config (`num_starts=5`, `start_mode="random"`, `enable_2opt=True`), SWAP
count, routed depth, total 2q count, prep seconds, Matrix-A diagnostics, and the harness
versions (as committed in `uv.lock`). Raw per-seed data is retained (not only means) in
`benchmarks/results/a6_gamma_results.json` (Phase 1) / `a6_gamma_smoke_raw.json` (smoke).

## Historical-data isolation

* A6 data lives in its own files under `benchmarks/results/` (`a6_*`) and is analysed in
  `reports/a6_*`.
* Tables 1–2 (random-init canonical, regenerated in the roadmap phase) are **not** rewritten by
  A6; reproduction harnesses that pass `start_mode="gaussian"` are untouched.
* A6 does not claim that historical Gaussian-era tables represent the shipped mapper.

## Decision rules (do not change the default automatically)

* **Keep gamma = 0.9** if no alternative shows a practically meaningful improvement, or
  significant differences are absent, or alternatives differ statistically but not meaningfully.
* **Candidate for changing the default** only if: reproducible SWAP improvement, the
  Friedman→Wilcoxon→BH procedure supports it, the effect is practically meaningful, and the
  result is not confined to one anomalous cell/artifact.
* **No-change conclusion** if the Friedman tests generally accept: no evidence from the tested
  workloads that gamma materially affects routing performance (absence of detected effect under
  the tested conditions — not proof of universal equivalence).

## Deliverables / gates

1. This spec (preregistration): `reports/a6_gamma_spec.md` — cell list recorded before
   execution. **DONE (this file).**
2. **Phase 0 smoke** (gamma ∈ {0.7, 0.9, 1.0}, one cell — VQE-N50 synthetic grid, both
   routers, K=20 matched seeds): `reports/a6_gamma_smoke.md` — feasibility/correctness gate,
   NOT inferential. Includes wall-clock cost estimate and a recommendation for the full run.
3. **Phase 1 full sweep** (authorized grid above): `benchmarks/results/a6_gamma_results.json`
   + `reports/a6_gamma_results.md` (per-cell summaries, distributions, Friedman stats, gated
   Wilcoxons, BH q, effect sizes, router- and circuit-family interpretation, limitations).

**Execution gate:** no full sweep until the smoke report has been completed and **reviewed** by
the human and Phase 1 is explicitly authorized with the final preregistered grid.

## Non-goals

Re-evaluating Gaussian vs random multi-start; tuning FAQ start count; testing new routers;
learned routing; fidelity as a primary endpoint; scaling beyond the authorized cells; changing
the mapper default before analysis; tuning gamma against the QAP objective alone; claiming a
universally optimal gamma.
