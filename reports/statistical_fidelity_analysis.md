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

| File | Contents |
|:---|:---|
| `benchmarks/results/significance_results.json` | Per-row paired-Wilcoxon results (raw p + BH q) for the SABRE and TKET pairs (`benchmarks/analyze_significance.py`) |
| `benchmarks/results/benchmark_fidelity_raw.json` | Per-(seed, method) SWAP count + fidelity proxy for the re-routed circuits (`benchmarks/benchmark_fidelity.py`, strided) |
| `benchmarks/results/benchmark_fidelity_results.json` | Mean SWAP + mean fidelity proxy per method/task |
| `benchmarks/results/benchmark_fidelity_comparison.json` | Per-pair SWAP delta vs fidelity-proxy delta (`benchmarks/report_fidelity.py`) |
| `benchmarks/results/benchmark_fidelity_crosscheck.json` | Validation that the re-run reproduced the canonical dataset: **0/1600 per-seed SWAP divergences** |

The fidelity re-run re-routes every circuit deterministically and keeps the routed circuit
(which `benchmark_eval.py` discarded). Because routing is seed-deterministic, it reproduced the
then-canonical SWAP counts exactly — the cross-check confirmed 0/1600 divergences — so the fidelity
numbers below describe the *same* routed circuits whose SWAP counts were in the previous README
tables (Gaussian-era FAQ arms). The canonical dataset has since been regenerated under the random
multi-start FAQ default; see the stale-data banner in section #5.

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
## #5 — SWAP delta vs. fidelity-proxy delta


> **⚠ Stale w.r.t. regenerated Tables 1–2.** The fidelity-proxy re-run below was executed
> against the **previous canonical dataset** (Gaussian-era FAQ arms). FAQ arms changed under the
> regenerated random-init dataset (default arms are identical), so this section's FAQ-arm
> fidelity numbers and sign-flip rows describe the superseded circuits until the fidelity re-run
> is repeated under the new canonical data (roadmap item: fidelity-proxy re-derivation).
>
Δ = (FAQ mean) − (default mean). A negative SWAP delta and a negative infidelity delta are both
*improvements*. Across the 37 comparisons with a non-zero SWAP delta (three rows are exact
ties), the two metrics **disagree in sign on 5** — the headline a fidelity-weighted method must
be judged on.

Rows where the two metrics disagree (the method is a "win" on one metric and a "loss" on the
other):

| Task | Arch | N | Pair | ΔSWAP | Δ infidelity proxy | Reading |
|:---|:---|:---:|:---|:---:|:---:|:---|
| Grover N=8 | Synthetic grid | 8 | SABRE | +14 | **−0.08** | FAQ adds SWAPs yet lands on lower-error edges → fidelity slightly better |
| Grover N=10 | Synthetic grid | 10 | SABRE | +52 | **−8.1** | FAQ adds many SWAPs but routes onto far lower-error edges → big fidelity win masked by SWAP count |
| Grover N=12 | Synthetic grid | 12 | SABRE | +16 | **−15.8** | same pattern, largest fidelity gain despite +SWAPs |
| Grover N=10 | Synthetic grid | 10 | TKET | **−102** | +8.2 | FAQ cuts SWAPs but routes onto higher-error edges → fidelity *worse* |
| Grover N=12 | Synthetic grid | 12 | TKET | **−126** | +38.5 | FAQ's SWAP win is a fidelity *loss* on this row |

**Interpretation (tentative, needs the multi-instance re-run of review point #3 to confirm):**

* On **IBM (real FakeBrisbane errors)** the two metrics almost always agree in sign — FAQ
  makes both metrics worse on SABRE and mostly both better on the TKET wins. No IBM row shows a
  significant sign flip. So on real calibration data the SWAP-count story is a good proxy.
* The sign flips are concentrated on the **synthetic grid**, whose error profile is *synthetic*
  (uniform 1–3%). FAQ's QAP objective drives it to minimise the log-infidelity-weighted path
  length **B**, so on the sparse grid it can trade a *larger number* of SWAPs for *lower-error*
  routing — exactly the behaviour that a SWAP-only metric cannot see. Conversely the Grover
  N10/N12 TKET rows show the SWAP-optimal answer is not fidelity-optimal.
* Because the synthetic grid's profile is randomly generated, these particular flips are illustrative of the
  metric, not a claim about real hardware. On the real IBM snapshot no headline claim
  flips sign. A faithful follow-up must replace the synthetic grid with an archived real
  non-IBM backend (review point #7).

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
