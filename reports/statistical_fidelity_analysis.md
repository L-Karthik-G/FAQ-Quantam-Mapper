# Statistical & Fidelity Analysis (review points #2 and #5)

Adds two analysis-level results the earlier round lacked, both reproducible from committed /
regenerated data — no new experiment design, no new backends:

1. **#2 — Paired significance testing.** Every "FAQ-lower / baseline-lower / tie" SWAP-count
   claim in the README tables is now backed by a paired **Wilcoxon signed-rank test** over the
   K=20 per-seed differences, with a **Benjamini–Hochberg FDR correction** across all tested
   comparisons (m = 36 on the regenerated dataset). A signed-rank test is used because the design
   is paired-by-seed and SWAP counts are small, skewed, often zero-inflated integers where a
   paired t-test's normality assumption is fragile; FDR correction guards against declaring
   winners from any single comparison among the many tested.
2. **#5 — Fidelity-loss proxy metric.** Alongside SWAP counts, we now estimate the
   fidelity loss of the *routed* circuit by walking the final transpiled circuit and
   multiplying the actual per-edge CNOT error rates from the same calibration snapshot used to
   build the QAP matrix **B** (`FakeBrisbane` for IBM; the recorded synthetic profile for the
   synthetic grid). This is the metric the method actually optimises for, so it can disagree with
   the raw SWAP count — and in several rows it does.

## Data produced

All fidelity numbers below were **regenerated under the shipped random multi-start FAQ default**
(the regenerated canonical dataset that Tables 1–2 now describe) and include the
FAQ-as-soft-candidate SABRE arm.

| File | Contents |
|:---|:---|
| `benchmarks/results/significance_results.json` | Per-row paired-Wilcoxon results (raw p + BH q) for the SABRE and TKET pairs (`benchmarks/analyze_significance.py`) |
| `benchmarks/results/benchmark_fidelity_raw.json` | Per-(seed, method) SWAP count + fidelity proxy for the re-routed circuits — arms `sabre_def`, `faq_sabre`, `tket_def`, `faq_tket`, `faq_soft_sabre` (`benchmarks/benchmark_fidelity.py`, strided) |
| `benchmarks/results/benchmark_fidelity_results.json` | Mean SWAP + mean fidelity proxy per method/task |
| `benchmarks/results/benchmark_fidelity_comparison.json` | Per-pair SWAP delta vs fidelity-proxy delta for the hard-SABRE, soft-SABRE and TKET pairs (`benchmarks/report_fidelity.py`) |
| `benchmarks/results/benchmark_fidelity_crosscheck.json` | Validation that the re-run reproduced the committed datasets: **0/1600 canonical-arm and 0/400 soft-arm per-seed SWAP divergences** |

The fidelity re-run re-routes every circuit deterministically and keeps the routed circuit
(which `benchmark_eval.py` discarded). Because routing is seed-deterministic, it reproduced the
regenerated canonical SWAP counts exactly (cross-check: 0/1600 divergences for
`benchmark_eval_raw_seeds.json`, 0/400 for the soft-candidate log `benchmark_soft_sabre_raw.json`),
so the fidelity numbers below describe the *same* routed circuits whose SWAP counts are in the
current README tables and in the soft-candidate experiment report.

## #2 — Significance results (paired Wilcoxon, K=20)

**Regenerated dataset.** The canonical Tables 1–2 were regenerated under the shipped **random
multi-start** FAQ default (the earlier committed tables used the deprecated Gaussian mode;
default-router arms are bit-identical, FAQ arms changed). This analysis was re-run on the
regenerated per-seed log — numbers below supersede the previous Gaussian-era panel.

Method: paired **Wilcoxon signed-rank** on the 20 per-seed SWAP differences per row, then a
**Benjamini–Hochberg FDR correction** is applied across all tested comparisons (m = 36) to
control the false-discovery rate from testing many rows at once. A row is significant only if
its **BH-adjusted q-value < 0.05**. Meanings: "base" = default router lower mean; "FAQ" =
FAQ-seeded lower mean; rows marked **det** are deterministic (one/both arms have zero
within-seed variance) so no rank test is defined. "Arch" labels Brisbane (IBM FakeBrisbane) and
Synthetic grid (the internally-named `Rigetti_Grid_80` topology, which is *not* a real Rigetti
device).

| Task | Arch | N | SABRE lower? | p | q(BH) | Sig@FDR | TKET lower? | p | q(BH) | Sig@FDR |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| GHZ State | Brisbane | 50 | base | 8.75e-05 | 0.0002 | yes | det | — | — | — |
| Grover's Search | Brisbane | 8 | base | 8.84e-05 | 0.0002 | yes | base | 3.56e-05 | 0.0002 | yes |
| Grover's Search | Synthetic grid | 8 | base | 0.0004 | 0.0006 | yes | FAQ | 2.30e-05 | 0.0002 | yes |
| Grover's Search | Brisbane | 10 | base | 0.2455 | 0.2525 | no | FAQ | 4.67e-05 | 0.0002 | yes |
| Grover's Search | Synthetic grid | 10 | base | 0.0013 | 0.0018 | yes | FAQ | 5.06e-05 | 0.0002 | yes |
| Grover's Search | Brisbane | 12 | base | 0.1474 | 0.1561 | no | base | 4.67e-05 | 0.0002 | yes |
| Grover's Search | Synthetic grid | 12 | base | 0.0826 | 0.0929 | no | FAQ | 2.30e-05 | 0.0002 | yes |
| QAOA | Brisbane | 10 | base | 0.0002 | 0.0003 | yes | FAQ | 2.95e-05 | 0.0002 | yes |
| QAOA | Brisbane | 20 | base | 0.0003 | 0.0006 | yes | FAQ | 0.0001 | 0.0003 | yes |
| QFT | Brisbane | 20 | base | 8.84e-05 | 0.0002 | yes | det | — | — | — |
| QFT | Synthetic grid | 20 | base | 8.76e-05 | 0.0002 | yes | FAQ | 0.1333 | 0.1454 | no |
| QRAM Decoder (Holdout) | Brisbane | 20 | FAQ | 0.0002 | 0.0003 | yes | base | 5.06e-05 | 0.0002 | yes |
| QRAM Decoder (Holdout) | Synthetic grid | 20 | FAQ | 7.59e-05 | 0.0002 | yes | base | 3.56e-05 | 0.0002 | yes |
| Random 3-Regular (Holdout) | Brisbane | 20 | base | 0.0104 | 0.0139 | yes | FAQ | 0.0004 | 0.0006 | yes |
| Ripple-Carry Adder (Holdout) | Brisbane | 20 | base | 0.0202 | 0.0243 | yes | base | 0.0253 | 0.0294 | yes |
| Ripple-Carry Adder (Holdout) | Synthetic grid | 20 | FAQ | 0.0001 | 0.0002 | yes | tie/det | — | — | — |
| VQE (RealAmplitudes) | Brisbane | 10 | base | 0.0176 | 0.0218 | yes | tie/det | — | — | — |
| VQE (RealAmplitudes) | Brisbane | 20 | base | 0.0001 | 0.0003 | yes | base | 0.0143 | 0.0184 | yes |
| VQE (RealAmplitudes) | Brisbane | 50 | base | 8.83e-05 | 0.0002 | yes | FAQ | 0.0010 | 0.0015 | yes |
| VQE (RealAmplitudes) | Synthetic grid | 50 | base | 0.4779 | 0.4779 | no | FAQ | 5.31e-05 | 0.0002 | yes |

**What this adds over the "Lower-SWAP method" column.** Several lower-mean claims are **not**
significant even under FDR: FAQ+SABRE *worsening* SABRE on Grover N=10/N=12 (Brisbane) and
Grover N=12 / VQE-N50 (synthetic grid), and FAQ+PyTKET "improving" over PyTKET on QFT-N20
(synthetic grid, q = 0.145). These five rows carry a **†** in README Tables 1–2. Notably the
BH correction removes **no** row on the regenerated dataset (m = 36): the VQE-N20 (Brisbane)
"default PyTKET lower" claim that BH previously downgraded (raw p = 0.046, q = 0.053) is now
itself significant (q = 0.018), and VQE-N50 (Brisbane) PyTKET flipped from a non-significant
FAQ loss to a *significant FAQ win* (q = 0.0015). All significant FAQ-lower wins survive at
q ≤ 0.0015 (PyTKET pair: Grover-N8/N10/N12 synthetic grid, Grover-N10 Brisbane, QAOA-N10/N20
Brisbane, VQE-N50 both grids, Random 3-regular Brisbane) and q ≤ 0.0003 (SABRE pair: QRAM
Brisbane + Ripple/QRAM synthetic grid). Where one arm is deterministic the row is labelled, not
compared as though sampled.
## #5 — SWAP delta vs. fidelity-proxy delta (regenerated, random-init dataset)

**Regenerated.** This panel was re-run under the shipped random multi-start FAQ default (the
regenerated canonical dataset), and now also reports the **FAQ-as-soft-candidate SABRE** pair
(`faq_soft_sabre`, FAQ layout as one extra trial in SABRE's pool — see
`reports/soft_candidate_sabre.md`). It supersedes the earlier Gaussian-era numbers.

Δ = (FAQ mean) − (default mean). A negative SWAP delta and a negative infidelity delta are both
*improvements*. Rows where the two metrics disagree in sign (a "win" on one metric and a "loss"
on the other), per pair and across all non-zero comparisons:

| Task | Arch | N | Pair | ΔSWAP | Δ infidelity proxy | Reading |
|:---|:---|:---:|:---|:---:|:---:|:---|
| Grover N=8 | Synthetic grid | 8 | SABRE soft | −0.4 | **+1.77** | FAQ-as-trial trims SWAPs marginally but the winning trial lands on higher-error edges → fidelity slightly worse |
| Grover N=10 | Synthetic grid | 10 | SABRE hard | +47.4 | **−11.42** | hard FAQ adds many SWAPs but routes onto far lower-error edges → fidelity win masked by SWAP count |
| Grover N=12 | Synthetic grid | 12 | TKET | **−123.9** | +46.54 | FAQ+PyTKET cuts SWAPs but routes onto higher-error edges → SWAP win is a fidelity *loss* (persists from the previous dataset) |
| QFT N=20 | Synthetic grid | 20 | SABRE soft | +0.7 | **−0.13** | tiny opposite-sign effect on an already-near-zero row |

**Interpretation (tentative, needs the multi-instance re-run of review point #3 to confirm):**

* On **IBM (real FakeBrisbane errors)** the two metrics again agree in sign on every row — FAQ
  makes both metrics worse on the hard-constrained SABRE losses and both better on its TKET and
  soft-SABRE wins. No IBM row shows a sign flip.
* The sign flips remain concentrated on the **synthetic grid**, whose error profile is *synthetic*
  (uniform 1–3%). FAQ's QAP objective drives it to minimise the log-infidelity-weighted path
  length **B**, so on the sparse grid it can trade a *larger number* of SWAPs for *lower-error*
  routing (Grover-N10 hard-SABRE), and the converse appears for FAQ+PyTKET on Grover-N12 (its
  SWAP win routes onto higher-error edges). The new **soft-candidate** pair shows two small
  opposite-sign rows (Grover-N8, QFT-N20) where the pool-selected FAQ trial shifts fidelity by
  more than it shifts SWAPs.
* Because the synthetic grid's profile is randomly generated, these particular flips are
  illustrative of the metric, not a claim about real hardware. On the real IBM snapshot no
  headline claim flips sign. A faithful follow-up must replace the synthetic grid with an
  archived real non-IBM backend (review point #7).
* **Headline for the fidelity-weighted objective.** The FAQ layout that wins SABRE's own trial
  pool is almost always also the fidelity-better one on IBM; only the synthetic grid exposes
  SWAP-vs-fidelity disagreement, and only there do FAQ's SWAP deltas understate (or overstate)
  its fidelity effect. SWAP count remains a good proxy on the IBM snapshot.

## Caveats

* **Fidelity proxy, not executed fidelity.** It multiplies the snapshot's reported per-edge
  CNOT error rates along the routed circuit (each SWAP counted as 3 CNOTs); it does not account
  for single-qubit errors, measurement error, crosstalk, or calibration drift during a run, and
  it is a *re-transpile* of the same deterministic routing, not a hardware execution.
* For very large circuits the per-circuit failure proxy `1−∏(1−eᵢ)` saturates toward 1 on both
  arms (too many gates), so the additive infidelity proxy (sum of −ln(1−eᵢ)) is the more
  informative column there; both are stored.
* Significance is per-row across the *router's* seed variation on a single circuit instance.
  It does **not** generalise across circuit instances — that requires review point #3.

## Reproduce

```bash
# 1. Paired significance + BH FDR (pure analysis of the committed canonical per-seed log)
uv run python benchmarks/analyze_significance.py

# 2. Fidelity re-run (heavy; re-routes all circuits). Launch 6 strided slices, then merge:
uv run python benchmarks/benchmark_fidelity.py 6 0   # ... remainder 0..5 in parallel
uv run python benchmarks/benchmark_fidelity.py --merge 6
# then render the delta table:
uv run python benchmarks/report_fidelity.py
```
