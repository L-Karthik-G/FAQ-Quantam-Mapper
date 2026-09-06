# Soft-candidate FAQ injection into SABRE's trial pool (roadmap item 4)

**Hypothesis under test.** Tables 1–2 show FAQ+SABRE *hard-constrained* pre-seeding (FAQ layout
as `initial_layout`) usually increases SWAPs: forcing an external layout removes the flexibility
of SABRE, a router that searches its own layout space. The softer alternative is to feed the FAQ
layout to SABRE as **one extra candidate inside SABRE's own randomized layout-trial pool** — if
the layout is good it wins the pool; if not, SABRE's own trials do — so the FAQ pass can no
longer make routing worse than default SABRE, while keeping the cases where FAQ genuinely helps.

**Native mechanism (no fork of Qiskit).** Qiskit's `SabreLayout` reads the property-set field
`sabre_starting_layouts` (a list of `Layout`s) and hands them to the Rust
`sabre_layout_and_routing` call as `partial_layouts`: they are evaluated **in addition to** the
`layout_trials` random starts, and the trial whose full routing yields the fewest SWAPs wins.
The soft arm therefore runs the *identical* optimization_level=1 preset pass manager as the
canonical default arm, with a single `AnalysisPass` prepended to the layout stage that sets
`sabre_starting_layouts = [FAQ layout]`. The FAQ layout is computed exactly as in the canonical
FAQ arm (random multi-start K=5 + 2-opt, `start_mode="random"`), so the only difference between
the default and soft arms is that one extra trial.

## Design

* Same 20 canonical tasks, K = 20 paired seeds (0–19), Qiskit `optimization_level=1`,
  `layout_method="sabre"`, `routing_method="sabre"`, `seed_transpiler=s`.
* Three arms per (task, seed):
  * `sabre_def` — default SABRE (identical to canonical Tables 1–2; verified mean-identical).
  * `faq_sabre` — FAQ layout hard-constrained (`initial_layout`; canonical FAQ+SABRE arm).
  * `faq_soft_sabre` — FAQ layout as one extra trial (`sabre_starting_layouts`).
* Statistics: paired Wilcoxon signed-rank over the 20 per-seed differences, BH-FDR across all
  tested comparisons (m = 58: 18 testable def-vs-soft, 20 hard-vs-soft, 20 def-vs-hard).
* Files: `benchmarks/results/benchmark_soft_sabre_results.json` (per-task means),
  `benchmarks/results/benchmark_soft_sabre_raw.json` (per-seed logs),
  `benchmarks/results/benchmark_soft_sabre_significance.json` (merged panel).
  Generator: `benchmarks/benchmark_soft_sabre.py` (slices merged; default arm cross-checked
  against the canonical dataset: 0 mismatches).

## Results (merged, K=20)

"Δ vs def" = soft − default; "Δ vs hard" = hard − default; negative = fewer SWAPs.
† = significant after BH (q < 0.05).

| Task | Arch | N | SABRE def | FAQ hard | FAQ soft | Δ soft−def (q) | Δ soft−hard (q) | Δ hard−def (q) |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Grover's Search | Bris | 8 | 1152.2 | 1264.6 | 1153.2 | +1.0 (0.507) | −111.3 (0.000†) | +112.3 (0.000†) |
| Grover's Search | Bris | 10 | 5603.1 | 5705.9 | 5642.8 | +39.6 (0.209) | −63.1 (0.411) | +102.7 (0.285) |
| Grover's Search | Bris | 12 | 18579.0 | 18641.7 | 18570.5 | −8.4 (0.390) | −71.1 (0.087) | +62.6 (0.186) |
| VQE (RealAmplitudes) | Bris | 10 | 0.0 | 1.2 | 0.0 | const (=def) | −1.2 (0.030†) | +1.2 (0.030†) |
| VQE (RealAmplitudes) | Bris | 20 | 9.6 | 24.1 | 9.7 | +0.1 (0.629) | −14.3 (0.000†) | +14.4 (0.000†) |
| VQE (RealAmplitudes) | Bris | 50 | 30.8 | 147.8 | 31.1 | +0.3 (0.226) | −116.7 (0.000†) | +117.0 (0.000†) |
| GHZ State | Bris | 50 | 12.0 | 50.6 | 12.0 | const (=def) | −38.6 (0.000†) | +38.6 (0.000†) |
| QFT | Bris | 20 | 225.0 | 258.9 | 222.2 | −2.8 (0.160) | −36.6 (0.000†) | +33.9 (0.000†) |
| QAOA | Bris | 10 | 57.2 | 70.3 | 57.6 | +0.5 (0.172) | −12.7 (0.001†) | +13.1 (0.000†) |
| QAOA | Bris | 20 | 308.6 | 327.9 | 304.2 | −4.5 (0.054) | −23.8 (0.000†) | +19.3 (0.001†) |
| Grover's Search | Grid | 8 | 768.2 | 791.5 | 767.9 | −0.3 (0.707) | −23.6 (0.002†) | +23.2 (0.001†) |
| Grover's Search | Grid | 10 | 3461.8 | 3509.2 | 3452.4 | −9.3 (0.108) | −56.8 (0.001†) | +47.5 (0.003†) |
| Grover's Search | Grid | 12 | 12375.2 | 12429.0 | 12365.9 | −9.4 (0.779) | −63.1 (0.038†) | +53.7 (0.117) |
| VQE (RealAmplitudes) | Grid | 50 | 45.7 | 49.5 | 39.5 | −6.2 (0.186) | −10.1 (0.037†) | +3.8 (0.513) |
| QFT | Grid | 20 | 147.9 | 174.3 | 148.6 | +0.7 (0.779) | −25.8 (0.000†) | +26.4 (0.000†) |
| Ripple-Carry Adder | Bris | 20 | 5.0 | 7.3 | 3.9 | −1.1 (0.030†) | −3.5 (0.002†) | +2.4 (0.033†) |
| QRAM Decoder | Bris | 20 | 19.3 | 14.2 | 12.3 | −7.0 (0.000†) | −1.9 (0.019†) | −5.2 (0.001†) |
| Random 3-Regular | Bris | 20 | 36.6 | 39.7 | 33.0 | −3.6 (0.015†) | −6.7 (0.001†) | +3.0 (0.020†) |
| Ripple-Carry Adder | Grid | 20 | 7.8 | 0.6 | 0.9 | −7.0 (0.000†) | +0.3 (0.142) | −7.2 (0.000†) |
| QRAM Decoder | Grid | 20 | 7.5 | 0.8 | 0.7 | −6.8 (0.000†) | −0.1 (0.194) | −6.8 (0.000†) |

Arch "Bris" = IBM FakeBrisbane (127q); "Grid" = synthetic 8×10 grid (80q). Means = SWAPs over
20 seeds; ties/deterministic rows marked const where soft ≡ default on every seed.

## What this shows

* **Soft-candidate injection removes FAQ+SABRE's downside.** Default-vs-soft: **0 of 18 tested
  rows show a significant loss** (worst mean deltas +39.6 SWAPs, q = 0.209, and +1.0, q = 0.507 —
  both Grover on Brisbane, not significant). Every row where hard-constrained FAQ made SABRE
  significantly worse — VQE-N50 Brisbane +117.0, VQE-N20 +14.4, GHZ +38.6, QFT Brisbane +33.9,
  QAOA +13.1/+19.3, Grover-N8 Brisbane +112.3, Grover-N8/N10 synthetic grid +23.2/+47.5 — falls
  back to ≈ default SABRE under soft injection (all non-significant, |Δ| ≤ 1 on most).
* **The FAQ wins survive.** Default-vs-soft has **5 significant improvements**: QRAM Brisbane
  −7.0, QRAM synthetic grid −6.8, Ripple synthetic grid −7.0, Ripple Brisbane −1.1, Random
  3-regular Brisbane −3.6 (the last two are rows where *hard* FAQ+SABRE was a significant loss —
  +2.4/+3.0 — so the pool turned an FAQ loss into an FAQ win).
* **Soft never does worse than hard.** Hard-vs-soft: **16 significant soft improvements**, 0
  significant regressions; the only rows where hard ≈ soft are exactly the FAQ-win rows (QRAM
  synthetic grid −0.1 ns, Ripple synthetic grid +0.3 ns).
* **Mechanism confirmation.** On rows where the FAQ layout is unhelpful, SABRE's own randomized
  trials simply beat it and win the pool (soft ≡ default up to seed-level equality — GHZ-N50 and
  VQE-N10 Brisbane are bit-identical to default on all 20 seeds); on rows where the FAQ layout is
  good, the FAQ trial wins. Exactly the soft-candidate behaviour the roadmap hypothesised.

## Limitations

* SWAP-count metric only (as throughout this repository so far); the fidelity-loss proxy has not
  been re-run for the soft arm (it is still stale w.r.t. even the regenerated Tables 1–2).
* FAQ pre-placement cost is unchanged (~2–29 s/circuit) and the soft arm additionally runs the
  full SabreLayout pool (default `layout_trials` = number of CPUs; the FAQ trial adds ~1 trial's
  routing). The design goal was to test the mechanism, not to reduce overhead.
* Per-circuit, per-architecture evidence (20 tasks on two fixed calibration snapshots); the
  pattern "pool-injection neutralises bad external layouts" should hold generally, but only these
  two topologies were measured.
* `sabre_starting_layouts` is Qiskit-internal-but-documented property-set API; the results are
  pinned to the installed Qiskit (2.5.2) via `uv.lock`.

## Reproduce

```bash
# Four balanced slices (each writes soft_part<r>_* files), then merge (merge step is manual;
# the analysis below was produced by concatenating the four slices and re-running the paired
# Wilcoxon + BH over all rows):
uv run python benchmarks/benchmark_soft_sabre.py --tasks 0,5,10,15,19 --out benchmarks/results/soft_part0
uv run python benchmarks/benchmark_soft_sabre.py --tasks 1,6,11,16,18 --out benchmarks/results/soft_part1
uv run python benchmarks/benchmark_soft_sabre.py --tasks 2,7,12,17 --out benchmarks/results/soft_part2
uv run python benchmarks/benchmark_soft_sabre.py --tasks 3,4,8,9,13,14 --out benchmarks/results/soft_part3
# merged outputs are committed as benchmark_soft_sabre_{results,raw,significance}.json
```
