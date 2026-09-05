# A5 — Multi-cell ablation: does Gaussian multi-start beat random restarts?

**Status: run complete (K=20 seeds, 5 cells).** Reproduces `benchmarks/ablation_multicell.py` →
`benchmarks/results/ablation_multicell_results.json`. This is the statistical-power follow-up to
the single-cell ablation in the README (§ Component Ablations), which showed Gaussian ≈ random
on one Grover-N10 example.

## Question

Rows 1–3 of the QAP-cost ablation, run across five cells that span the regimes in Tables 1–2,
with K=20 seeds and mean ± 95% CI. The open question from review point #4: **does structured
Gaussian multi-start (row 3) beat plain random multi-start (row 2) once 2-opt is applied, with
real power — or should the method just ship as random-multi-start + 2-opt?**

Cells: Grover-N10 (Brisbane, continuity), VQE-N50 (synthetic grid — the largest FAQ+PyTKET
paired-seed win, −91.5%), QRAM-N20 (Brisbane — the FAQ+SABRE win), Grover-N12 (Brisbane — a
FAQ+PyTKET regression), VQE-N10 (Brisbane — the zero-SWAP baseline).

Metric: post-2-opt **polished QAP cost** (the objective the pipeline minimizes before routing).
Paired Wilcoxon (row 3 vs row 2) per cell, Benjamini–Hochberg-corrected across the 5 cells.

## Results (mean ± 95% CI of polished QAP cost; K=20)

| Cell | Arch | row1 barycenter | row2 random (K5) | row3 Gaussian (K5) | gauss−rand | p | q(BH) | sig |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Grover N10 | Brisbane | 91.86 (det) | 88.12 ± 0.61 | 88.54 ± 0.28 | +0.42 | 0.184 | 0.31 | no |
| VQE N50 | synthetic | 24.34 (det) | **22.35 ± 0.41** | 23.21 ± 0.32 | **+0.86** | 0.0064 | **0.032** | **yes (random better)** |
| QRAM N20 | Brisbane | 105.44 (det) | 101.54 ± 1.41 | 101.48 ± 1.39 | −0.06 | 0.812 | 0.81 | no |
| Grover N12 | Brisbane | 91.40 (det) | 87.70 ± 0.44 | 87.79 ± 0.46 | +0.08 | 0.717 | 0.81 | no |
| VQE N10 | Brisbane | 37.21 (det) | 37.66 ± 0.33 | 37.21 (det) | −0.45 | 0.017 | **0.042** | yes (Gaussian better) |

*Positive `gauss−rand` = Gaussian is **worse** (higher polished cost) than random. row 1 is a
single deterministic solve, reported as a point value.*

## Reading the result

**1. Gaussian does NOT beat random multi-start once 2-opt is applied — this holds in 3 of 5
cells and is actively contradicted in the most important one.**

* In **3 cells** (Grover N10, QRAM N20, Grover N12) Gaussian ≈ random: small, non-significant
  differences (q > 0.3). The original Grover-N10 finding generalizes.
* In **VQE-N50 (synthetic grid)** — the cell where FAQ+PyTKET recorded its largest paired-seed
  SWAP win (−91.5%) — Gaussian is **significantly worse** than random (q = 0.032), adding
  ~0.86 to the polished cost. Random multi-start is the better init here.
* In **VQE-N10 (Brisbane)** Gaussian is flagged *significantly better* (q = 0.042) — but this is
  a **degeneracy artifact, not a real win**: see point 2.

**2. The VQE-N10 "Gaussian win" is a tie artifact — flagging explicitly.** row 3 (Gaussian) is
`det` and equals row 1 (single barycenter) exactly: 37.2104 on all 20 seeds. The Gaussian
perturbations produce no diversity — every seed collapses to the same single-barycenter optimum
(37.21), which random restarts sometimes overshoot (37.66 ± 0.33). So on VQE-N10 Gaussian is not
beating random via better perturbation search; it is simply returning the deterministic
barycenter answer, and 13 of 20 per-seed differences are exact zeros (only n=7 informative
pairs). The "significance" therefore does **not** demonstrate Gaussian multi-start value.

**2b. VQE-N50 scrutiny — real but *small*, not large.** Applying the same degeneracy check to
the VQE-N50 "random better" cell (now the central negative claim): all **20/20 per-seed
differences are non-zero** (no tie artifact; Gaussian is worse on 16 of 20 seeds). So the
significance there is genuine, not a pairwise-collapse artifact. But **"significant" ≠ "large"**:
the mean effect is +0.86 on a ~22–23 polished-cost scale, i.e. **~+3.9%** of the random-mean
magnitude. Contextualizing against the multi-start benefit over the single barycenter baseline
(random multi-start improves by −1.99 over barycenter; Gaussian by only −1.13), Gaussian captures
only ~57% of the multi-start improvement that random does. So the correct reading is: at VQE-N50
the K=20 sample size was enough to detect a **small, real-but-modest** penalty from using
Gaussian instead of random restarts — it is a *consistent* disadvantage, not a catastrophic one,
and it does **not** by itself argue that FAQ placement is useless, only that random init is the
better (and simpler) of the two schemes. A reader must not conflate the q=0.032 significance
with a large effect.

**3. Net verdict.** The negative result is not confined to the original Grover-N10 case — it is
the general picture. Across the five regimes Gaussian multi-start provides **no reliable
advantage** over random multi-start after 2-opt, and it is significantly *worse* in the one cell
(VQE-N50) where the underlying placement most clearly matters. This matches review point #4's
conclusion: the honest recommendation is to **ship random multi-start + 2-opt** (row 2) and drop
the Gaussian machinery, since it is more complex, roughly equally good, and occasionally worse.

## Caveats

* **QAP-cost level only.** This ablation measures the objective the layout pass minimizes; it
  does not route, so a "better QAP cost" is not guaranteed to equal better SWAPs/fidelity
  downstream (that is exactly the Grover-N12 concern in the cell selection). It is the right
  level to isolate *which init scheme to keep*, which is the question A5 asks.
* **Synthetic grid for VQE-N50.** Its error profile is randomly generated, not real Rigetti
  hardware (see the A4 rename); the finding is about the method's init scheme, not that device.
* QAP costs are continuous, so Wilcoxon tie-handling is not a general concern, but VQE-N10
  produced many exact-zero differences (a real degeneracy) and is flagged rather than hidden.

## Reproduce

```bash
uv run python benchmarks/ablation_multicell.py --seeds 20
```
