# A6 — Gamma decay sensitivity: results (Compact A6 run)

**Status: DONE.** Executes the human-authorized **Compact A6** design recorded in the
[`a6_gamma_spec.md`](a6_gamma_spec.md) addendum: 5 gamma levels × 3 cells × K=10 matched seeds
× 2 routers = 300 routing runs (0 failures). Raw per-seed data:
`benchmarks/results/a6_gamma_results.json`; significance output:
`benchmarks/results/a6_gamma_significance.json`. Analysis = preregistered plan: per-cell
Friedman gate → paired Wilcoxon vs `gamma=0.90` **only** on gated cells → BH across the 12
post-hoc comparisons actually performed. Primary metric: post-routing **SWAP count** (sole
significance metric).

## Per-cell gamma summaries (mean SWAPs over K=10 seeds)

| Cell | Router | g=0.5 | g=0.7 | g=0.9 (ref) | g=0.95 | g=1.0 | Friedman p | gate |
|:--|:--|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| vqe50-grid | SABRE | 117.6 | 68.1 | 46.1 | 29.1 | 22.6 | 4.5e-07 | **PASS** |
| vqe50-grid | PyTKET | 1.2 | 1.2 | 0.8 | 1.0 | 1.2 | 0.856 | fail |
| qram20-bris | SABRE | 14.7 | 13.2 | 13.9 | 13.9 | 17.0 | 0.087 | fail |
| qram20-bris | PyTKET | 22.2 | 22.0 | 21.8 | 21.4 | 22.4 | 0.259 | fail |
| grover10-bris | SABRE | 5613.3 | 5740.2 | 5663.7 | 5860.1 | 5950.6 | 0.0011 | **PASS** |
| grover10-bris | PyTKET | 4444.6 | 4670.8 | 4557.7 | 4331.5 | 3766.0 | 0.0037 | **PASS** |

Distribution note: SWAP counts are per-seed varied and often zero-inflated/skewed (small
counts on qram/vqe50-PyTKET; hundreds-to-thousands on grover), which is why the paired
Friedman/Wilcoxon design is used rather than mean comparisons.

## Post-hoc: gamma vs 0.90 on the three gated cells (12 comparisons, BH across all)

Mean per-seed difference = (gamma − 0.90); negative = gamma routes fewer SWAPs.
r = matched-pairs rank-biserial effect size; seeds +/- = improved / tied / worsened.

| Cell | Router | gamma | mean diff | median diff | r | seeds +/- | p | q (BH) | sig |
|:--|:--|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| vqe50-grid | SABRE | 0.50 | +71.5 | +64.5 | −1.00 | 0/0/10 | 0.002 | 0.012 | **yes** (worse) |
| vqe50-grid | SABRE | 0.70 | +22.0 | +19.5 | −0.82 | 1/1/8 | 0.027 | 0.047 | **yes** (worse) |
| vqe50-grid | SABRE | 0.95 | −17.0 | −19.0 | +0.80 | 8/0/2 | 0.023 | 0.047 | **yes** (better) |
| vqe50-grid | SABRE | 1.00 | −23.5 | −23.0 | +0.93 | 9/0/1 | 0.006 | 0.023 | **yes** (better) |
| grover10-bris | SABRE | 0.50 | −50.4 | −10.0 | +0.20 | 5/1/4 | 0.652 | 0.917 | no |
| grover10-bris | SABRE | 0.70 | +76.5 | −27.0 | −0.07 | 6/1/3 | 0.910 | 1.000 | no |
| grover10-bris | SABRE | 0.95 | +196.4 | +215.5 | −0.78 | 2/0/8 | 0.027 | 0.047 | **yes** (worse) |
| grover10-bris | SABRE | 1.00 | +286.9 | +270.5 | −1.00 | 0/0/10 | 0.002 | 0.012 | **yes** (worse) |
| grover10-bris | PyTKET | 0.50 | −113.1 | 0 | +0.20 | 3/5/2 | 1.000 | 1.000 | no |
| grover10-bris | PyTKET | 0.70 | +113.1 | 0 | −0.20 | 2/5/3 | 1.000 | 1.000 | no |
| grover10-bris | PyTKET | 0.95 | −226.2 | 0 | +0.33 | 4/4/2 | 0.688 | 0.917 | no |
| grover10-bris | PyTKET | 1.00 | −791.7 | −1131.0 | +1.00 | 7/3/0 | 0.016 | 0.047 | **yes** (better) |

Cells that failed the Friedman gate (qram20-bris both routers; vqe50-grid PyTKET) get **no**
gamma-vs-0.9 significance claims, per the preregistration.

## Interpretation

**Router-specific.** All gamma signal lives in the **SABRE** arm except one (grover10 PyTKET).
The PyTKET cells that did not gate sit at or near the routing floor with little room
(vqe50-grid PyTKET: 0–2 SWAPs per seed) or show no significant between-gamma variation
(qram20). Where PyTKET had room (grover10),
`gamma=1.0` is significantly better than 0.9 (−792 SWAPs mean, q = 0.047) — on this search
workload the FAQ embedding's best layout is identical across gammas (3766 on 7/10 seeds at 1.0),
i.e. weaker decay let FAQ find the good layout on more seeds.

**Circuit-family specific (opposite directions — important).**
* **Variational (VQE-N50 synthetic grid, SABRE):** weak/no decay wins — `1.0` −23.5 SWAPs
  (q=0.023, −51% relative to the 0.9 mean 46.1), `0.95` −17.0 (q=0.047); aggressive decay
  (0.5, 0.7) significantly *worse* (+71.5/+22.0). Mechanism-consistent: for repeated layers of
  the *same* interaction structure, temporal decay down-weights exactly the interactions that
  dominate total routing cost, so removing decay (or weakening it) aligns A with cumulative
  routing burden.
* **Search (Grover-N10 Brisbane, SABRE):** the default is already right-side — `0.95` and
  `1.0` are significantly *worse* than 0.9 (+196/+287), while 0.5/0.7 are indistinguishable.
  Here interactions are spread across the circuit rather than repeated, so over-weighting later
  shallow-structure layers hurts.
* **Structural holdout (QRAM-N20 Brisbane):** no gamma effect detected (both routers).

**Practical-significance reading (per decision rules).** Statistically *and* practically
meaningful effects exist, but they are **not monotone and not universal**: no tested gamma
beats 0.9 on every cell — 1.0 is best on variational-SABRE and grover-PyTKET yet worst on
grover-SABRE; 0.9 remains best-in-set on grover-SABRE and is never significantly worse than
1.0/0.95 there. The cells where 0.9 is *not* competitive (vqe50-grid SABRE) were exactly the
kind of repeated-layer variational workload the mapper is aimed at. Under the decision rules,
this is **not** a clear "change the default" result (the improvement is not reproducible across
circuit families — it flips sign between variational and search), so the recommendation is:

> **Keep `gamma = 0.9` as the shipped default, and treat gamma as a per-family dial**: for
> repeated-layer variational workloads, `gamma >= 0.95` (up to no decay, 1.0) is measurably
> better for SABRE routing and not worse for PyTKET; for search-structured workloads 0.9 (or
> weaker decay) stays best. A confirmatory run on the two cells dropped for cost
> (vqe10-bris zero-floor, grover12-bris) and/or K=20 would be needed before changing the
> shipped default.

**"No-effect" reading for the cells that failed the gate.** qram20-bris (both routers) and
vqe50-grid PyTKET show no evidence of a gamma effect — i.e., for structural holdouts and for
PyTKET routing at/near the SWAP floor, gamma did not materially change routing performance
under the tested conditions. This does not prove universal gamma equivalence; it is limited to
those tested cells.

## Limitations

* **Small matched seed count** (K=10) per the feasibility-driven Compact A6 revision: Friedman
  and Wilcoxon are valid but lower-powered; the two largest reported effects (r = ±1.00) are on
  10-seed comparisons.
* **Reduced cell scope**: vqe10-bris (zero-SWAP floor) and grover12-bris (150 s/run PyTKET arm)
  were dropped for cost (recorded pre-run in the spec addendum, not from outcomes). Conclusions
  must not be blanket-generalized to the zero-SWAP-floor or 127q deep-search regimes.
* **Two topologies / snapshots only** (IBM FakeBrisbane 127q; synthetic 8×10 grid with a
  synthetic 1–3% error profile), as throughout the project.
* SWAP count is the only metric with significance claims; secondary metrics (depth, 2q count,
  prep) are stored in the raw JSON but not tested.
* gamma=0.90 is the reference, not an assumed optimum; the analysis only supports the
  comparisons it ran (no all-pairs).

## Reproduce

```bash
# 300 runs across 6 slices (~25 min on this machine), then:
uv run python benchmarks/benchmark_gamma.py --merge 6 --out benchmarks/results/a6_gamma_results.json
uv run python benchmarks/analyze_gamma.py --raw benchmarks/results/a6_gamma_results.json
```
