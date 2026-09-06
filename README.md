# FAQ-Layout: Quadratic Assignment Pre-Placement for Quantum Routing

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Central Contribution**: An empirical evaluation of an approximate Quadratic Assignment
Problem (QAP) pre-placement pass that pre-seeds the initial layout of downstream quantum
circuit routers (Qiskit SABRE and PyTKET LexiRoute) and measures whether it reduces the number
of SWAP gates they emit.

FAQ-Layout is a pre-placement heuristic that wraps SciPy's
`quadratic_assignment(method="faq")` with **random multi-start** over the Birkhoff polytope
and a discrete 2-opt refinement. (It previously used structured Gaussian Sinkhorn-perturbed
starts; the multi-cell ablation in `reports/a5_results.md` showed random multi-start is
equal-or-better once 2-opt is applied, so random is now the default and recommended mode.) It
is an *empirical compilation heuristic*,
not a new continuous-optimization theory result. The benchmark evaluates routers on a fixed,
recorded hardware calibration snapshot; it does **not** run on live quantum hardware.

> **Scope note.** This repository contains several experiment rounds. The **canonical,
> reproducible paired-seed dataset is `benchmarks/results/benchmark_eval_results.json`** (with its raw per-seed
> log `benchmarks/results/benchmark_eval_raw_seeds.json`), produced by `benchmarks/benchmark_eval.py` over the 20 tasks in
> Tables 1–2 below (K=20 seeds, Qiskit `optimization_level=1`). Older `*_results.json` files
> (archived under `historical/`) come from earlier rounds that used different seeds, topologies,
> or `optimization_level` settings; they are kept for history and are **not** the numbers cited in
> this README. See [Data provenance & reproduction](#-data-provenance--reproduction).

---

## 📌 Problem Formulation & Heuristic Pipeline

### QAP Objective Function

Initial logical-to-physical placement is modeled as an approximate QAP:

$$\min_{P \in \Pi_M} \sum_{i,j} A_{ij} B_{P(i), P(j)} = \min_{P \in \Pi_M} \text{Tr}(A^T P B P^T)$$

* **$A \in \mathbb{R}^{M \times M}$**: Time-decayed circuit interaction DAG matrix
  (zero-padded for $N < M$), where a two-qubit interaction at DAG layer $l$ contributes
  $g^l$ with decay `gamma = 0.9`. The decay rate is heuristic; A6 tested it against
  downstream SWAP count and found a **workload-dependent effect** — weak/no decay helps
  repeated-layer variational circuits (SABRE) but hurts Grover-style search circuits, so the
  default `0.9` is kept and treated as a per-family dial (see
  [`reports/a6_gamma_results.md`](reports/a6_gamma_results.md)).
* **$B \in \mathbb{R}^{M \times M}$**: Directed shortest-path distance matrix of the hardware
  graph weighted by log-infidelities from a Qiskit **`FakeBrisbane`** fake backend object
  (IBM's archived Brisbane calibration properties; **not** live QPU execution), plus an
  estimated CNOT direction-reversal overhead ($4 \times \text{cost}_{\text{1Q-Hadamard}}$).
* **$\mathcal{D}_M$ (Birkhoff polytope)**: the doubly-stochastic relaxation used internally by
  SciPy's FAQ method. FAQ returns a discrete permutation; its reported cost is the discrete QAP
  cost of that permutation (the relaxation value is not exposed by SciPy and is **not** claimed
  here as a "continuous cost").

Heuristic pipeline: build $A$ and $B$ → solve the QAP by FAQ from K=5 random doubly-stochastic
starts (Birkhoff-polytope restarts) → keep the lowest-cost permutation → apply a discrete 2-opt
local search → hand the resulting layout to the router. (Earlier revisions used structured
Gaussian Sinkhorn-perturbed starts; random multi-start is now the default — see
`reports/a5_results.md`.)

---

## 📊 Paired-Seed Benchmark (MQT-Bench + Hand-Crafted Holdout Suite, $K=20$ Seeds)

*All methods share identical hardware profiles, matching seeds ($s \in \{0..19\}$), basis gates
(`cx`, `h`, `rz`, `x`, `sx`), and router options: Qiskit `transpile(..., optimization_level=1)`
with `seed_transpiler=s`, and PyTKET `PlacementPass(GraphPlacement)` + `RoutingPass` (default)
vs. FAQ-embedding + `RoutingPass`. Values are **mean ± 95% CI over the 20 paired seeds**; all
rows achieved 20/20 successful compilations. "Lower-SWAP method" reports the strictly-lower
mean for each router pair.*

> **Determinism note (PyTKET default).** In the installed pytket (2.18.x), neither
> `GraphPlacement` (constructor args: `maximum_matches`, `timeout`, `maximum_pattern_gates`,
> `maximum_pattern_depth` — no seed/RNG) nor `RoutingPass` (documented as deterministic
> `LexiLabellingMethod` + `LexiRouteRoutingMethod`) exposes any seed or random seed; there is no
> global random-seed knob in `pytket.placement`/`pytket.passes`. So the default PyTKET arm is
> deterministic by construction, and indeed it yields the identical swap count on every seed.
> Its `± 0.0` CI therefore reflects a single deterministic value, *not* 20 independent samples,
> and it is reported as a point value. Rows whose only varying arm is FAQ's are still valid
> paired comparisons; rows where both arms are deterministic (marked **det**) are not treated as
> sampled.
>
> **How to read the "Lower-SWAP method" column.** It states the lower **mean**, which is *not*
> the same as a statistically significant difference. Every claim here is (a) tested with a
> paired **Wilcoxon signed-rank** over the 20 per-seed differences with a **Benjamini–Hochberg
> FDR correction** across all comparisons (full per-row results in
> [`reports/statistical_fidelity_analysis.md`](reports/statistical_fidelity_analysis.md) and
> `benchmarks/results/significance_results.json`) and (b) re-checked against an estimated
> **fidelity-loss proxy** of the routed circuit. A **†** next to a winner in the tables below
> marks a lower mean that the BH-corrected test does **not** support at q < 0.05 (the marker is
> the table-level version of the significance caveat). The fidelity-loss proxy has been
> regenerated under these tables, including the FAQ-as-soft-candidate SABRE arm (see the
> report's §#5); it agrees in sign with the SWAP deltas on IBM and disagrees only on a few
> synthetic-grid rows.

### Table 1: IBM FakeBrisbane (127-qubit Heavy-Hex), K=20 paired seeds

*FAQ-arm numbers below were produced with the **shipped default** solver configuration:
random multi-start (K=5, `start_mode="random"`) + discrete 2-opt polish. This is the mode
`AdaptiveFAQSolver` uses out of the box; the structured-Gaussian multi-start of earlier commits
is deprecated (see the [multi-cell ablation](reports/a5_results.md)). Regenerate the data with
`benchmarks/benchmark_eval.py` (or `benchmark_eval_parallel.py`), re-run
`benchmarks/analyze_significance.py`, and re-render these tables with `benchmarks/render_tables.py`.*

| Benchmark Circuit | Suite | Scale $N$ | **SABRE Default** | **FAQ+SABRE** | **Δ (SABRE)** | **PyTKET Default** | **FAQ+PyTKET** | **Δ (PyTKET)** | **FAQ Preproc. (s)** | **Lower-SWAP method** |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| **Grover's Search** | MQT-Bench | 8 | 1152.2 ± 30.4 | 1264.6 ± 36.6 | +112.3 (+9.8%) | 851.0 ± 0.0 | 1037.0 ± 8.3 | +186.0 (+21.9%) | 17.168 | SABRE Def / PyTKET Def |
| **Grover's Search** | MQT-Bench | 10 | 5603.1 ± 141.8 | 5705.9 ± 109.9 | +102.7 (+1.8%) | 5035.0 ± 0.0 | 4501.1 ± 259.0 | -533.9 (-10.6%) | 14.680 | SABRE Def† / FAQ+PyTKET |
| **Grover's Search** | MQT-Bench | 12 | 18579.0 ± 27.3 | 18641.7 ± 68.1 | +62.7 (+0.3%) | 12610.0 ± 0.0 | 15650.5 ± 21.3 | +3040.5 (+24.1%) | 10.554 | SABRE Def† / PyTKET Def |
| **VQE (RealAmplitudes)** | MQT-Bench | 10 | 0.0 ± 0.0 | 1.2 ± 0.9 | +1.2 (n/a) | 0.0 ± 0.0 | 0.0 ± 0.0 | +0.0 (n/a) | 21.575 | SABRE Def / Tie |
| **VQE (RealAmplitudes)** | MQT-Bench | 20 | 9.6 ± 0.4 | 24.1 ± 4.3 | +14.5 (+150.5%) | 0.0 ± 0.0 | 0.9 ± 0.7 | +0.9 (n/a) | 18.909 | SABRE Def / PyTKET Def |
| **VQE (RealAmplitudes)** | MQT-Bench | 50 | 30.8 ± 0.3 | 147.8 ± 12.2 | +117.0 (+380.5%) | 12.0 ± 0.0 | 7.9 ± 2.9 | -4.1 (-34.2%) | 29.081 | SABRE Def / FAQ+PyTKET |
| **GHZ State** | MQT-Bench | 50 | 12.0 ± 0.0 | 50.6 ± 3.4 | +38.6 (+322.1%) | 0.0 ± 0.0 | 6.0 ± 0.0 | +6.0 (n/a) | 27.517 | SABRE Def / PyTKET Def |
| **QFT** | MQT-Bench | 20 | 225.0 ± 3.4 | 258.9 ± 9.6 | +33.9 (+15.1%) | 284.0 ± 0.0 | 212.0 ± 0.0 | -72.0 (-25.4%) | 16.414 | SABRE Def / FAQ+PyTKET |
| **QAOA** | MQT-Bench | 10 | 57.2 ± 1.8 | 70.3 ± 3.3 | +13.1 (+22.9%) | 79.0 ± 0.0 | 73.9 ± 1.3 | -5.1 (-6.5%) | 19.405 | SABRE Def / FAQ+PyTKET |
| **QAOA** | MQT-Bench | 20 | 308.6 ± 4.2 | 327.9 ± 6.9 | +19.3 (+6.3%) | 398.0 ± 0.0 | 387.1 ± 4.5 | -10.9 (-2.7%) | 16.030 | SABRE Def / FAQ+PyTKET |
| **Ripple-Carry Adder** | Hand-Crafted | 20 | 5.0 ± 0.0 | 7.3 ± 2.2 | +2.3 (+47.0%) | 0.0 ± 0.0 | 3.2 ± 2.7 | +3.2 (n/a) | 7.380 | SABRE Def / PyTKET Def |
| **QRAM Decoder** | Hand-Crafted | 20 | 19.3 ± 1.0 | 14.2 ± 1.2 | -5.2 (-26.7%) | 3.0 ± 0.0 | 22.2 ± 0.5 | +19.2 (+640.0%) | 7.931 | FAQ+SABRE / PyTKET Def |
| **Random 3-Regular** | Hand-Crafted | 20 | 36.6 ± 1.1 | 39.7 ± 1.8 | +3.1 (+8.3%) | 55.0 ± 0.0 | 49.8 ± 1.9 | -5.2 (-9.5%) | 6.539 | SABRE Def / FAQ+PyTKET |

**† Lower mean on that router pair is *not* significant after the Benjamini–Hochberg FDR correction (q ≥ 0.05); see [`benchmarks/results/significance_results.json`](benchmarks/results/significance_results.json) and [`reports/statistical_fidelity_analysis.md`](reports/statistical_fidelity_analysis.md).**

### Table 2: Synthetic Grid Topology (80-qubit), K=20 paired seeds

*Same configuration note as Table 1: FAQ-arm numbers reflect the shipped random multi-start
default (not the deprecated Gaussian scheme). "Rigetti_Grid_80" is a SYNTHETIC 8x10 grid with a
randomly-generated uniform error profile, not a real Rigetti device; it is kept only as a
non-heavy-hex topology stress test.*

| Benchmark Circuit | Suite | Scale $N$ | **SABRE Default** | **FAQ+SABRE** | **Δ (SABRE)** | **PyTKET Default** | **FAQ+PyTKET** | **Δ (PyTKET)** | **FAQ Preproc. (s)** | **Lower-SWAP method** |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| **Grover's Search** | MQT-Bench | 8 | 768.2 ± 4.3 | 791.5 ± 8.1 | +23.2 (+3.0%) | 639.0 ± 0.0 | 606.5 ± 1.7 | -32.5 (-5.1%) | 2.777 | SABRE Def / FAQ+PyTKET |
| **Grover's Search** | MQT-Bench | 10 | 3461.8 ± 13.2 | 3509.2 ± 17.8 | +47.4 (+1.4%) | 2669.0 ± 0.0 | 2540.6 ± 15.5 | -128.4 (-4.8%) | 2.732 | SABRE Def / FAQ+PyTKET |
| **Grover's Search** | MQT-Bench | 12 | 12375.2 ± 27.0 | 12429.0 ± 44.4 | +53.7 (+0.4%) | 8828.0 ± 0.0 | 8704.1 ± 1.0 | -123.9 (-1.4%) | 2.896 | SABRE Def† / FAQ+PyTKET |
| **VQE (RealAmplitudes)** | MQT-Bench | 50 | 45.7 ± 5.0 | 49.5 ± 11.1 | +3.8 (+8.3%) | 13.0 ± 0.0 | 0.9 ± 0.5 | -12.1 (-93.1%) | 2.473 | SABRE Def† / FAQ+PyTKET |
| **QFT** | MQT-Bench | 20 | 147.9 ± 2.3 | 174.3 ± 3.6 | +26.4 (+17.9%) | 148.0 ± 0.0 | 144.5 ± 2.4 | -3.5 (-2.4%) | 2.402 | SABRE Def / FAQ+PyTKET† |
| **Ripple-Carry Adder** | Hand-Crafted | 20 | 7.8 ± 0.8 | 0.6 ± 0.4 | -7.2 (-92.4%) | 0.0 ± 0.0 | 0.0 ± 0.0 | +0.0 (n/a) | 2.125 | FAQ+SABRE / Tie |
| **QRAM Decoder** | Hand-Crafted | 20 | 7.5 ± 0.7 | 0.8 ± 0.5 | -6.8 (-89.4%) | 0.0 ± 0.0 | 14.0 ± 0.8 | +14.0 (n/a) | 1.988 | FAQ+SABRE / PyTKET Def |

**† Lower mean on that router pair is *not* significant after the Benjamini–Hochberg FDR correction (q ≥ 0.05); see [`benchmarks/results/significance_results.json`](benchmarks/results/significance_results.json) and [`reports/statistical_fidelity_analysis.md`](reports/statistical_fidelity_analysis.md).**

### What these data actually show

* **FAQ + PyTKET** reduces SWAPs versus PyTKET's own `GraphPlacement` on every synthetic-grid
  MQT task (Grover N8/N10/N12, VQE-N50; QFT-N20's −3.5 mean is the one not significant, q = 0.145)
  and on several IBM tasks: Grover-N10 (−533.9, −10.6%), QAOA-N10/N20 (−5.1/−10.9), Random
  3-regular (−5.2), QFT-N20 (−72.0, a deterministic constant here) and VQE-N50 (−4.1, −34.2%).
  The largest consistent win is VQE-N50 on the synthetic grid (−12.1 SWAPs, −93.1%).
* **FAQ + SABRE rarely helps.** It adds SWAPs on every MQT-Bench task and on the Ripple-Carry /
  Random 3-regular IBM holdouts; it beats default SABRE on only three hand-crafted holdout rows —
  QRAM on IBM (19.3→14.2, −26.7%) and Ripple-Carry Adder / QRAM on the synthetic grid
  (7.8→0.6, 7.5→0.8) — all three significant. Pre-seeding a layout can *over-constrain* SABRE's
  own search, so a worse FAQ layout than SABRE would find on its own cannot always be recovered
  by routing.
* FAQ + PyTKET is **not** uniformly better even on IBM: on Grover-N8 (+21.9%) and Grover-N12
  (+24.1%) it is substantially *worse* than PyTKET default, and it also loses the QRAM/Ripple
  holdouts on IBM (+19.2/+3.2). Gains are workload- and size-specific, not a blanket improvement.
* Default routers are already optimal (0–3 SWAPs) on the easiest circuits (VQE-N10, Ripple and
  QRAM holdouts on the synthetic grid); there is no room for FAQ to help there, and on VQE-N10
  Brisbane random-init FAQ+SABRE even adds +1.2 SWAPs on average where default SABRE needs 0.

All raw per-seed values (each of the 20 seeds, per method, with explicit success/failure) are
in `benchmarks/results/benchmark_eval_raw_seeds.json`.

> **Significance & fidelity caveat on the bullets above.** These are statements about *mean*
> differences. With a Benjamini–Hochberg FDR correction over m = 36 comparisons (q < 0.05), five
> rows have a lower mean that is **not** significant: FAQ+SABRE vs default SABRE on Grover-N10 /
> N12 (Brisbane) and Grover-N12 / VQE-N50 (synthetic grid), and FAQ+PyTKET vs PyTKET on QFT-N20
> (synthetic grid, q = 0.145). The BH correction removes no row this round — the VQE-N20 Brisbane
> "default PyTKET lower" claim that BH previously downgraded is now significant (q = 0.018) — but
> the non-significant rows are marked **†** in the tables. The significant FAQ-lower wins survive
> at q ≤ 0.0015 (PyTKET pair) and q ≤ 0.0003 (SABRE pair). The fidelity-loss proxy has been
> regenerated under these tables (incl. the soft-candidate SABRE arm; cross-checks 0/1600 and
> 0/400) and can disagree with raw SWAP deltas — sign flips are confined to the synthetic grid.
> Read the bullets as directional means, not tested claims, and consult
> [`reports/statistical_fidelity_analysis.md`](reports/statistical_fidelity_analysis.md) before
> drawing conclusions.
>
> **Change note (random-init regeneration).** Tables 1–2 were regenerated from the shipped
> **random** multi-start default; the previously committed tables reflected the deprecated
> **Gaussian** mode. Default-router arms are bit-identical to the old dataset (verified), so all
> deltas come from the FAQ arms. The broad conclusions are unchanged (FAQ+SABRE still usually
> hurts, FAQ+PyTKET still wins on the same classes of tasks), but several FAQ-arm means moved —
> e.g. FAQ+PyTKET on Grover-N10 Brisbane improved to 4501 (−10.6% vs PyTKET) and on VQE-N50
> Brisbane flipped from a (non-significant) loss to a significant −34.2% win, while its QFT-N20
> synthetic-grid win is no longer significant (q = 0.145 vs 0.0014 before). These tables are the
> new canonical dataset.

## 🔬 Component Ablations (QAP-cost level, IBM FakeBrisbane, Grover N=10)

`benchmarks/benchmark_ablations.py` measures each solver configuration's **QAP objective value only**
(FAQ permutation cost before 2-opt and final cost after 2-opt) on one circuit. It does **not**
route; downstream routing outcomes are measured per-router in Tables 1–2 and are not a property
of a single QAP-init configuration, so no "downstream SWAPs" column is reported here.

| Ablation configuration | FAQ perm. cost (pre-2-opt) | After 2-opt polish | Isolated effect |
|:---|:---:|:---:|:---|
| 1. Single barycenter start | 166.51 | 91.86 | Baseline single start (best-of-1). |
| 2. Random multi-start (K=5) | 156.41 | 86.99 | Multi-start min over random starts. |
| 3. Structured Gaussian multi-start (K=5, ours) | 122.12 | 88.31 | Multi-start min over Gaussian-perturbed starts. |
| 4. FAQ, no 2-opt polish (barycenter, K=5) | 166.51 | 166.51 | Same init as row 1 with polish disabled. |
| 5. FAQ with undirected hardware matrix (Gaussian K=5) | 53.17 | 35.72 | Ignoring CNOT direction lowers the cost scale; **not** directly comparable. |

Interpretation below is **superseded for the Gaussian-vs-random question** by the multi-cell,
K=20 follow-up in `reports/a5_results.md` (see the verdict block after it). The single-cell
numbers are kept only to show the historical basis and the 2-opt/undirected isolation effects,
which the multi-cell study did not re-derive:

* **2-opt polish (isolated, rows 1 vs 4):** with a fixed barycenter start, 2-opt lowers the QAP
  cost from 166.51 to 91.86 (−44.8%). This is the clean measure of the 2-opt contribution (the
  multi-cell study kept 2-opt on throughout, so it does not re-isolate this).
* **Multi-start vs single barycenter (rows 2/3 vs 1):** best-of-K multi-start beats best-of-1
  (random 86.99, Gaussian 88.31, vs barycenter 91.86). Part of the gain is simply the
  min-over-K effect, so these figures are **not** a pure "Gaussian-noise" effect.
* **Random vs. Gaussian (superseded):** on this one Grover-N10 example the two were within ~1
  point after 2-opt (86.99 vs 88.31). With only a single seed this could not distinguish them.
* These are QAP-cost proxies on one circuit; they are consistent with — but do not alone
  establish — the routing results in Tables 1–2.

> **CURRENT POSITION — multi-cell follow-up (rows 1–3, K=20 seeds, 5 regimes).** The
> Gaussian-vs-random question above was re-run across five cells from Tables 1–2 (Grover-N10,
> VQE-N50 synthetic-grid, QRAM-N20, Grover-N12, VQE-N10) at K=20 seeds with mean ± 95% CI and a
> paired Wilcoxon (BH-corrected). **Verdict: Gaussian multi-start does not beat random
> multi-start once 2-opt is applied.** It ties (non-significant) in 3 cells and is *significantly
> worse* in VQE-N50 (q=0.032; a real but small ~+3.9% penalty — Gaussian worse on 16/20 seeds,
> not a tie artifact). The one cell where Gaussian looks significantly better (VQE-N10, q=0.042)
> is a tie artifact: Gaussian collapses to the deterministic single-barycenter value on every
> seed. See [`reports/a5_results.md`](reports/a5_results.md). Recommendation: **ship random
> multi-start + 2-opt** (simpler, equal-or-better) rather than the structured-Gaussian scheme.

---

## 🧪 Follow-up experiment: FAQ as a soft candidate in SABRE's own trial pool

Tables 1–2 show FAQ+SABRE *hard-constrained* pre-seeding (FAQ layout forced as
`initial_layout`) usually increases SWAPs. Qiskit's `SabreLayout` natively supports the softer
alternative: a `sabre_starting_layouts` property-set list is evaluated as **additional layout
trials inside SABRE's own randomized trial pool** (min-SWAP selection across all trials). The
follow-up benchmark (K=20, same 20 tasks, identical `optimization_level=1` preset pipeline and
seeds) compares default SABRE, hard FAQ+SABRE, and **FAQ-as-one-trial** SABRE; full table in
[`reports/soft_candidate_sabre.md`](reports/soft_candidate_sabre.md).

**Result (paired Wilcoxon + BH, m = 58):** injecting the FAQ layout as one trial in the pool is
**never significantly worse than default SABRE** (0/18 tested rows; largest deltas +39.6 SWAPs,
q = 0.209, and +1.0, q = 0.507), and it keeps the FAQ wins — **5 significant improvements**
(QRAM Brisbane −7.0, QRAM synthetic grid −6.8, Ripple synthetic grid −7.0, and — where *hard*
FAQ+SABRE had been a significant loss — Ripple Brisbane −1.1 and Random 3-regular −3.6). Every
row where hard-constraint FAQ made SABRE significantly worse (VQE-N50 Brisbane +117.0, GHZ
+38.6, QFT Brisbane +33.9, QAOA +13.1/+19.3, VQE-N20 +14.4, Grover-N8 Brisbane +112.3, synthetic
grid +23.2/+47.5) falls back to ≈ default SABRE under the soft injection (all non-significant).
This confirms the over-constraint diagnosis: FAQ pre-seeding is only harmful to SABRE because it
*forces* the layout; offered as one candidate among SABRE's own trials it is harmless at worst
and a real win on the structural holdout circuits.

---

## 🧪 Objective-function test: transitive-dependence-weighted interaction matrix A (item 5) — negative

The theoretical review questioned whether the raw time-decayed interaction-frequency matrix A
has any link to the router's SWAP count. A candidate fix was implemented and A/B tested:
`DAGInteractionMatrixBuilder.build_matrix_dependence_weighted` (variant **A2**) scales each
two-qubit gate by `(1 + d(g))`, where `d(g)` is its transitive dependence depth (longest chain
of earlier two-qubit gates sharing a qubit), i.e. weighting interactions by dependence distance
instead of raw frequency (no new hyperparameters; `A2 == A0` for dependence-free circuits —
unit-tested). Holding everything else fixed (same seeds, solver, routers), the FAQ+PyTKET and
FAQ-soft-SABRE arms were re-run under A2 and compared per-seed against the committed A0 logs
(paired Wilcoxon, BH over m = 33 cells).

**Result: no improvement.** 32/33 cells are non-significant after FDR; the only significant
effect is a *regression* (soft SABRE, QRAM synthetic grid, +1.85 SWAPs, q = 0.0036), and the
directional trend on the FAQ+PyTKET rows where A0 wins most clearly (Grover-N10 Brisbane,
VQE-N50 Brisbane) is negative. The dependence-depth weighting is **not adopted**; A0 remains the
shipped objective. Full table:
[`reports/dependence_objective.md`](reports/dependence_objective.md).

---

## 🧪 Stronger off-the-shelf baselines (item 7): optimization_level 2/3 (+ VF2PostLayout)

FAQ has only ever been compared against `optimization_level=1` routers. A new baseline run
(K=20, same tasks/seeds; `benchmarks/benchmark_baselines.py`) adds Qiskit's default
`optimization_level=2` and `3` arms — the o3 preset also refines the layout with **VF2PostLayout**
(the VF2-family pass available in this Qiskit; there is no `layout_method='vf2'` plugin). Full
table: [`reports/stronger_baselines.md`](reports/stronger_baselines.md).

**Result: for the SABRE router family, FAQ pre-placement is not the answer — o3 is.** o3 beats
the o1 default SABRE used in Tables 1–2 on 16/20 tasks and beats the FAQ-as-trial SABRE arm on
13 tasks, tying 2 and losing only on **three small structural holdouts** (Ripple Brisbane 3.9 vs
5.0, Ripple synthetic grid 0.9 vs 3.3, QRAM synthetic grid 0.7 vs 4.3). **FAQ+PyTKET still beats
every SABRE baseline** on the large rows (e.g. Grover-N12 Brisbane 15650 vs 18469, VQE-N50
synthetic grid 0.9 vs 20.8): FAQ's remaining measurable value is as an embedding for PyTKET's
LexiRoute on large structured circuits — not as a seed for SABRE.

**Exact ceiling (item 8).** For tiny circuits (N ≤ 6, line and 2×3 grid) an exact
joint layout+routing solver (`benchmarks/exact_ceiling.py`, 0-1 BFS over mapping×gate
states) gives a ground-truth floor to report "% of theoretical optimum". On those cells the
optima are 0–3 SWAPs; the only row with headroom (random 3-regular on the 2×3 grid, exact =
2) is met at 105% by o3, 125% by o1/FAQ-soft and 150% by hard FAQ+SABRE — and line-N5 ripple
shows hard FAQ+SABRE above the exact 0 floor (+0.6) with FAQ-soft back at 0. See
[`reports/exact_ceiling.md`](reports/exact_ceiling.md).

---

## Limitations & When to Use It

* **Real overhead is seconds, not sub-second.** FAQ pre-placement measured ~2–29 s per
  circuit here (Tables 1–2: ~2–3 s on the 80-qubit synthetic grid, ~6.5–29 s on the 127-qubit
  FakeBrisbane rows — dominated by the random multi-start + 2-opt solve, which is
  single-threaded Python over an M×M permutation). That is far from negligible, so it is only
  justified when the routed circuit is itself large/multi-iteration (e.g. repeated VQE/QAOA
  layers) and the SWAP savings outweigh the one-time cost.
* **FAQ+SABRE (hard-constrained) usually makes routing worse** on these benchmarks; prefer
  default SABRE — and the item-7 baselines show default `optimization_level=3` (+VF2PostLayout)
  beats even the FAQ-as-trial arm on most tasks, so for SABRE the recommendation is simply
  o3. This is specific to *forcing* the FAQ layout as `initial_layout` — offering the
  FAQ layout as one candidate inside SABRE's own trial pool removes the downside entirely (see
  the [follow-up experiment](#-follow-up-experiment-faq-as-a-soft-candidate-in-sabres-own-trial-pool)).
  The FAQ-seeded gains for PyTKET are specific to the synthetic-grid MQT rows plus a
  workload-specific IBM subset (QAOA, QFT-N20, VQE-N50, Random 3-regular), and persist against
  the o3 baseline on the large Grover/VQE rows.
* **Not a blanket improvement.** On IBM, FAQ+PyTKET *hurts* Grover at N=8 and N=12 and the
  QRAM/Ripple holdouts, and helps only a workload-specific subset (QAOA-N10/20, QFT-N20,
  VQE-N50, Random 3-regular). The README's earlier recommendation "use it for large
  Grover/search circuits" is **not** supported by the data and has been removed.
* **Over-constraining:** pre-seeding an initial layout can restrict a router's search space.
* **Hardware snapshot scope:** results use an IBM `FakeBrisbane` snapshot (archived calibration
  data) and a synthetic-grid profile (labeled "Rigetti_Grid_80" internally), **not** live physical hardware; live results vary with
  calibration drift.
* **Heuristic, non-convex:** FAQ seeks local solutions of an indefinite QAP over the Birkhoff
  polytope; no global-optimality guarantee.
* The ablation table is a single-circuit, single-seed cost study; see the caveats in its section.

---

## 📌 Data provenance & reproduction

Canonical paired-seed dataset (this README's Tables 1–2):

| File | Contents | Produced by |
|:---|:---|:---|
| `benchmarks/results/benchmark_eval_results.json` | Summary (mean, 95% CI, success) per task/method | `benchmarks/benchmark_eval.py` |
| `benchmarks/results/benchmark_eval_raw_seeds.json` | Raw per-seed SWAP/time/prep logs (all 20 seeds) | `benchmarks/benchmark_eval.py` |
| `benchmarks/results/benchmark_ablation_results.json` | QAP-cost ablation table | `benchmarks/benchmark_ablations.py` |
| `benchmarks/results/ablation_multicell_results.json` | A5 multi-cell, K=20 QAP-cost ablation of init rows 1–3 (report: `reports/a5_results.md`) | `benchmarks/ablation_multicell.py` |
| `benchmarks/results/significance_results.json` | Paired Wilcoxon + BH q per row | `benchmarks/analyze_significance.py` |
| `benchmarks/results/benchmark_fidelity_raw.json` / `benchmark_fidelity_results.json` | Per-seed SWAP + fidelity-loss proxy per method (5 arms incl. FAQ-soft-SABRE; regenerated under the random-init dataset) | `benchmarks/benchmark_fidelity.py` |
| `benchmarks/results/benchmark_fidelity_crosscheck.json` | Validates fidelity re-run reproduces the committed data (0/1600 canonical-arm + 0/400 soft-arm SWAP divergences) | `benchmarks/benchmark_fidelity.py` |
| `benchmarks/results/benchmark_fidelity_comparison.json` | SWAP-delta vs fidelity-delta per pair (hard-SABRE, soft-SABRE, TKET) | `benchmarks/report_fidelity.py` |
| `benchmarks/results/benchmark_soft_sabre_results.json` / `benchmark_soft_sabre_raw.json` / `benchmark_soft_sabre_significance.json` | FAQ-as-soft-candidate SABRE: per-task means, per-seed logs, merged paired-Wilcoxon + BH (report: `reports/soft_candidate_sabre.md`) | `benchmarks/benchmark_soft_sabre.py` (4 balanced slices, merged) |
| `benchmarks/results/benchmark_dependence_a_results.json` / `benchmark_dependence_a_raw.json` / `benchmark_dependence_a_significance.json` | A2 (dependence-weighted A) vs A0 arms for FAQ+PyTKET and FAQ-soft-SABRE: means, per-seed logs, per-seed paired-Wilcoxon + BH (report: `reports/dependence_objective.md`) | `benchmarks/benchmark_dependence_a.py` (6 balanced slices, merged) |
| `benchmarks/results/benchmark_baselines_results.json` / `benchmark_baselines_raw.json` / `benchmark_baselines_significance.json` | optimization_level 2/3 (VF2PostLayout) default SABRE baselines vs committed arms: means, per-seed logs, paired-Wilcoxon + BH (report: `reports/stronger_baselines.md`) | `benchmarks/benchmark_baselines.py` |
| `benchmarks/results/exact_ceiling.json` | Exact joint layout+routing optimum on tiny cells (N≤6) + arm means (report: `reports/exact_ceiling.md`) | `benchmarks/exact_ceiling.py` |
| `benchmarks/results/a6_gamma_results.json` / `a6_gamma_significance.json` / `a6_gamma_smoke_raw.json` | A6 gamma-decay sensitivity: per-seed SWAP rows (Compact A6: 5 gammas × 3 cells × K=10 × 2 routers = 300 runs; plus the 120-run Phase-0 smoke log) + Friedman/Wilcoxon/BH analysis (reports: `reports/a6_gamma_spec.md`, `a6_gamma_smoke.md`, `a6_gamma_results.md`) | `benchmarks/benchmark_gamma.py`, `benchmarks/analyze_gamma.py` |

Running `benchmarks/benchmark_eval.py` (or its CPU-parallel variants),
`benchmarks/analyze_significance.py` and `benchmarks/benchmark_ablations.py` regenerates these
files in `benchmarks/results/`; the README's Tables 1–2 markdown is rendered from
`benchmark_eval_results.json` + `significance_results.json` by `benchmarks/render_tables.py`
(do not hand-edit the numbers). Older, mutually-inconsistent experiment rounds
(e.g. `benchmark_2_results.json`, `benchmark_results.json`, `benchmark_statistical_results.json`,
`benchmark_rigorous_results.json`, `benchmark_new_circuits_results.json`,
`benchmark_tket_all_results.json`, `benchmark_fgea_results.json`, `qft_scaling_results.json`
and their generators) used different seeds, topologies, or `optimization_level` settings and are
**not** the numbers reported here. They have been archived under `historical/` (see
`historical/README.md`) for provenance only. The previously contradictory
`reports/complete_benchmark_table.md` has been rewritten as a data provenance note. Treat the
three canonical benchmark files (`benchmark_eval_results.json`, `benchmark_eval_raw_seeds.json`,
`benchmark_ablation_results.json`) as the authoritative dataset — the significance and fidelity
files in the table are *derived analysis* over that same dataset — and regenerate before drawing
conclusions. The fidelity files have been regenerated under the current (random multi-start)
canonical dataset and cover the soft-candidate SABRE arm as well (cross-checks: 0/1600 + 0/400
SWAP divergences).

---

## 🚀 Quickstart (uv)

This project uses **[uv](https://docs.astral.sh/uv/)** for dependency management and
environment setup. Python dependencies are declared in `pyproject.toml` and pinned in
`uv.lock`; a `.python-version` pins the interpreter to Python 3.12.

```bash
git clone https://github.com/L-Karthik-G/FAQ-Quantam-Mapper.git
cd FAQ-Quantam-Mapper

# Create the environment (downloads Python 3.12 if needed) and install all deps
uv sync

# Run the unit & integration test suite
uv run pytest tests/test_modules.py -v

# Regenerate the QAP-cost ablation table (writes benchmarks/results/benchmark_ablation_results.json in-repo)
uv run python benchmarks/benchmark_ablations.py

# Regenerate the paired-seed benchmark suite (K=20 seeds; writes results in-repo).
# NOTE: this runs full Qiskit/PyTKET/MQT routing and can take a long time.
uv run python benchmarks/benchmark_eval.py

# Faster alternative: run the 20 tasks in parallel across CPU cores
# (multiprocessing Pool; results identical to the serial run):
uv run python benchmarks/benchmark_eval_parallel.py 6
#   ...or, in sandboxed environments that block multiprocessing Pools, launch the
#   strided driver on <workers> shells and merge the partial results:
#   uv run python benchmarks/benchmark_eval_strided.py 6 0   # repeat remainder 0..5

# Paired significance + BH FDR over the raw seed log, then re-render README Tables 1-2
# (with the per-row "not significant after FDR" daggers) from the results:
uv run python benchmarks/analyze_significance.py
uv run python benchmarks/render_tables.py
```

`uv sync` installs the project itself (editable) plus the runtime dependencies and the `dev`
group (pytest). To add/upgrade a dependency: `uv add <pkg>` / `uv add --dev <pkg>`, then
commit the updated `pyproject.toml` and `uv.lock`.

The pure-`numpy`/`scipy` solver (`qap_compiler/module_c_faq.py`) has no Qiskit dependency and
can be tested/used standalone.

---

## 📜 Citation

```bibtex
@misc{faq_layout_2026,
  author = {Karthik, G. and collaborators},
  title = {FAQ-Layout: Quadratic Assignment Pre-Placement for Quantum Routing},
  year = {2026},
  publisher = {GitHub},
  journal = {GitHub repository},
  howpublished = {\url{https://github.com/L-Karthik-G/FAQ-Quantam-Mapper}}
}
```
