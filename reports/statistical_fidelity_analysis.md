# Statistical & Fidelity Analysis (review points #2 and #5)

Adds two analysis-level results the earlier round lacked, both reproducible from committed /
regenerated data — no new experiment design, no new backends:

1. **#2 — Paired significance testing.** Every "FAQ-lower / baseline-lower / tie" SWAP-count
   claim in the README tables is now backed by a paired **Wilcoxon signed-rank test** over the
   K=20 per-seed differences, with a **Benjamini–Hochberg FDR correction** across all tested
   comparisons (m = 34). A signed-rank test is used because the design is paired-by-seed and SWAP
   counts are small, skewed, often zero-inflated integers where a paired t-test's normality
   assumption is fragile; FDR correction guards against declaring winners from any single
   comparison among the many tested.
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
(which `benchmark_eval.py` discarded). Because routing is seed-deterministic, it reproduces the
canonical SWAP counts exactly — the cross-check confirmed 0/1600 divergences — so the fidelity
numbers below describe the *same* routed circuits whose SWAP counts are in the README tables.

## #2 — Significance results (paired Wilcoxon, K=20)

Method: paired **Wilcoxon signed-rank** on the 20 per-seed SWAP differences per row, then a
**Benjamini–Hochberg FDR correction** is applied across all tested comparisons (m = 34) to
control the false-discovery rate from testing many rows at once. A row is significant only if
its **BH-adjusted q-value < 0.05**. Meanings: "base" = default router lower mean; "FAQ" =
FAQ-seeded lower mean; rows marked **det** are deterministic (one/both arms have zero
within-seed variance) so no rank test is defined. "Arch" labels Brisbane (IBM FakeBrisbane) and
Synthetic grid (the internally-named `Rigetti_Grid_80` topology, which is *not* a real Rigetti
device).

| Task | Arch | N | SABRE lower? | p | q(BH) | Sig@FDR | TKET lower? | p | q(BH) | Sig@FDR |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| GHZ State | Brisbane | 50 | base | 8.8e-05 | 0.0002 | yes | det | — | — | — |
| Grover's Search | Brisbane | 8 | base | 8.8e-05 | 0.0002 | yes | base | 4.2e-05 | 0.0002 | yes |
| Grover's Search | Synthetic grid | 8 | base | 0.012 | 0.015 | yes | FAQ | 1.2e-05 | 0.0002 | yes |
| Grover's Search | Brisbane | 10 | base | 0.33 | 0.37 | **no** | FAQ | 1.2e-05 | 0.0002 | yes |
| Grover's Search | Synthetic grid | 10 | base | 4.5e-04 | 0.0007 | yes | det | — | — | — |
| Grover's Search | Brisbane | 12 | base | 0.25 | 0.28 | **no** | base | 5.3e-05 | 0.0002 | yes |
| Grover's Search | Synthetic grid | 12 | base | 0.61 | 0.63 | **no** | FAQ | 5.3e-05 | 0.0002 | yes |
| QAOA | Brisbane | 10 | base | 8.8e-05 | 0.0002 | yes | det | — | — | — |
| QAOA | Brisbane | 20 | base | 7.2e-04 | 0.0010 | yes | FAQ | 6.9e-05 | 0.0002 | yes |
| QFT | Brisbane | 20 | base | 8.8e-05 | 0.0002 | yes | FAQ | 1.7e-05 | 0.0002 | yes |
| QFT | Synthetic grid | 20 | base | 8.8e-05 | 0.0002 | yes | FAQ | 1.0e-03 | 0.0014 | yes |
| QRAM Decoder (Holdout) | Brisbane | 20 | FAQ | 1.0e-04 | 0.0002 | yes | base | 5.1e-05 | 0.0002 | yes |
| QRAM Decoder (Holdout) | Synthetic grid | 20 | FAQ | 7.5e-05 | 0.0002 | yes | base | 5.4e-05 | 0.0002 | yes |
| Random 3-Regular (Holdout) | Brisbane | 20 | base | 0.022 | 0.028 | yes | FAQ | 2.2e-04 | 0.0004 | yes |
| Ripple-Carry Adder (Holdout) | Brisbane | 20 | base | 1.0 | 1.0 | **no** | base | 0.025 | 0.031 | yes |
| Ripple-Carry Adder (Holdout) | Synthetic grid | 20 | FAQ | 8.3e-05 | 0.0002 | yes | det | — | — | — |
| VQE (RealAmplitudes) | Brisbane | 10 | det (tie) | — | — | — | det (tie) | — | — | — |
| VQE (RealAmplitudes) | Brisbane | 20 | base | 1.3e-04 | 0.0002 | yes | base | 0.046 | 0.053 | **no** |
| VQE (RealAmplitudes) | Brisbane | 50 | base | 8.8e-05 | 0.0002 | yes | base | 0.59 | 0.62 | **no** |
| VQE (RealAmplitudes) | Synthetic grid | 50 | base | 7.2e-04 | 0.0010 | yes | FAQ | 5.3e-05 | 0.0002 | yes |

**What this adds over the earlier "Lower-SWAP method" column.** Several previously-reported
differences are **not** significant even under FDR despite a lower mean — notably FAQ+SABRE
*worsening* SABRE on Grover N=10/N=12 (Brisbane) and FAQ+PyTKET "improving" over PyTKET on
VQE-N50 (Brisbane). The BH correction additionally removes **VQE-N20 (Brisbane), TKET pair**:
raw p = 0.046 looked significant but its adjusted q = 0.053 crosses the 0.05 threshold, so the
"default PyTKET is better here" claim is not supported at FDR 0.05. Where one arm is
deterministic the row is labelled, not compared as though sampled. All *significant* FAQ-lower
PyTKET wins (QFT, QAOA, Random 3-regular, Grover N8 synthetic grid, Grover N10 Brisbane, VQE-N50
synthetic grid) survive the FDR correction at q ≤ 0.0014.

## #5 — SWAP delta vs. fidelity-proxy delta

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
