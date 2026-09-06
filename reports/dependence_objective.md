# Objective-function test: transitive-dependence-weighted matrix A (roadmap item 5)

**Question.** The QAP objective currently uses `A` = raw time-decayed two-qubit interaction
frequency (each CX weighted by `γ^layer`), which is order-agnostic w.r.t. circuit dependency
structure — the theoretical review found no established link from that static aggregate to the
router's SWAP count. Would weighting interactions by *transitive dependence distance* (analogous
to the dependence-aware reasoning used in the mapping literature) instead of raw frequency
produce FAQ layouts that route with fewer SWAPs?

**Variant under test (A2).** `DAGInteractionMatrixBuilder.build_matrix_dependence_weighted`
scales each two-qubit gate's contribution by `(1 + d(g))` on top of the usual `γ^layer` decay,
where `d(g)` is the transitive dependence depth of the gate: the length of the longest chain of
earlier two-qubit gates sharing a qubit with it (computed in one pass over `dag.layers()`; gates
in the same layer never share qubits). Gates deep on dependent chains cannot be deferred or
commuted, so their adjacency demand is weighted harder than equally-timed gates on independent
parallel tracks. No new hyperparameters; `A2 == A0` for any circuit with no
shared-qubit-dependent two-qubit gates (unit-tested).

**Design.** Everything else held fixed vs. the committed datasets: same 20 canonical tasks,
K=20 paired seeds, same random multi-start FAQ solver (`start_mode="random"`, K=5, 2-opt), same
routers. Two A2 arms were compiled from scratch:
`faq_tket_a2` (FAQ layout → PyTKET `RoutingPass`) and `faq_soft_a2` (FAQ layout as one extra
trial in SABRE's pool). Their A0 counterparts are the already-committed `faq_tket` /
`faq_soft_sabre` per-seed logs (identical seeds and settings), so the comparison is an exact
per-seed paired test (Wilcoxon signed-rank, BH over m = 33 testable cells). Files:
`benchmarks/results/benchmark_dependence_a_{results,raw,significance}.json`; generator
`benchmarks/benchmark_dependence_a.py`.

## Result: no improvement — A2 is statistically indistinguishable from A0, with one significant regression

Per-seed Δ = A2 − A0 (negative = A2 better). † = q < 0.05 after BH.

| Cell | N | Arch | Router | Δ mean (q) |
|:---|:---:|:---:|:---|:---:|
| Grover's Search | 8 | Bris | SABRE-soft | 0.0 (const) |
| Grover's Search | 8 | Grid | SABRE-soft | −0.65 (0.688) |
| Grover's Search | 10 | Bris | SABRE-soft | −2.10 (0.519) |
| Grover's Search | 10 | Grid | SABRE-soft | +2.35 (0.737) |
| Grover's Search | 12 | Bris | SABRE-soft | −0.80 (0.519) |
| Grover's Search | 12 | Grid | SABRE-soft | −1.90 (0.737) |
| QAOA | 10 | Bris | SABRE-soft | 0.0 (const) |
| QAOA | 20 | Bris | SABRE-soft | −2.60 (0.519) |
| QFT | 20 | Bris | SABRE-soft | −0.65 (0.737) |
| QFT | 20 | Grid | SABRE-soft | −0.60 (0.519) |
| QRAM Decoder (Holdout) | 20 | Bris | SABRE-soft | −1.00 (0.519) |
| **QRAM Decoder (Holdout)** | **20** | **Grid** | **SABRE-soft** | **+1.85 (0.004†)** |
| Random 3-Regular (Holdout) | 20 | Bris | SABRE-soft | +1.25 (0.519) |
| Ripple-Carry Adder (Holdout) | 20 | Bris | SABRE-soft | −0.15 (0.737) |
| Ripple-Carry Adder (Holdout) | 20 | Grid | SABRE-soft | −0.25 (0.737) |
| VQE (RealAmplitudes) | 20 | Bris | SABRE-soft | +0.45 (0.519) |
| VQE (RealAmplitudes) | 10 | Bris | SABRE-soft | 0.0 (const) |
| VQE (RealAmplitudes) | 50 | Bris | SABRE-soft | −0.25 (0.519) |
| VQE (RealAmplitudes) | 50 | Grid | SABRE-soft | −3.50 (0.615) |
| GHZ State | 50 | Bris | PyTKET | 0.0 (const) |
| Grover's Search | 8 | Bris | PyTKET | −2.00 (0.739) |
| Grover's Search | 8 | Grid | PyTKET | +1.00 (0.688) |
| Grover's Search | 10 | Bris | PyTKET | +339.3 (0.216) |
| Grover's Search | 10 | Grid | PyTKET | +3.30 (0.737) |
| Grover's Search | 12 | Bris | PyTKET | −18.6 (0.519) |
| Grover's Search | 12 | Grid | PyTKET | −1.20 (0.300) |
| QAOA | 10 | Bris | PyTKET | −0.90 (0.519) |
| QAOA | 20 | Bris | PyTKET | −5.50 (0.481) |
| QFT | 20 | Bris | PyTKET | +1.60 (0.519) |
| QFT | 20 | Grid | PyTKET | −1.50 (0.519) |
| QRAM Decoder (Holdout) | 20 | Bris | PyTKET | −0.30 (0.519) |
| QRAM Decoder (Holdout) | 20 | Grid | PyTKET | −0.60 (0.519) |
| Random 3-Regular (Holdout) | 20 | Bris | PyTKET | +0.45 (0.737) |
| Ripple-Carry Adder (Holdout) | 20 | Bris | PyTKET | +2.60 (0.519) |
| Ripple-Carry Adder (Holdout) | 20 | Grid | PyTKET | 0.0 (const) |
| VQE (RealAmplitudes) | 20 | Bris | PyTKET | +1.05 (0.287) |
| VQE (RealAmplitudes) | 50 | Bris | PyTKET | +4.55 (0.216) |
| VQE (RealAmplitudes) | 50 | Grid | PyTKET | +0.20 (0.737) |

Arch: Bris = IBM FakeBrisbane (127q), Grid = synthetic 8×10 grid (80q). "const" = A2 identical
to A0 on every seed (no test possible).

**Reading.**

* **32 of 33 testable cells are not significant after BH (q < 0.05).** The dependence-weighted
  objective neither reliably improves nor harms downstream SWAP counts.
* The **only significant effect is a regression**: SABRE-soft on QRAM synthetic grid
  (+1.85 SWAPs mean, q = 0.0036). Nothing significantly *improves*.
* The directional (non-significant) trend on the FAQ+PyTKET rows where A0 had its clearest wins
  is *negative*: Grover-N10 Brisbane (Δ +339.3, raw p = 0.014 — A2 moves most seeds into the
  worse of the two layout basins the solver sees: 4897 vs the 3766-basin A0 reaches on 8/20
  seeds; verified by re-compiling both variants for seed 0) and VQE-N50 Brisbane (+4.55, raw
  p = 0.020). After BH correction neither survives.
* Verdict: **the transitive-dependence-depth weighting tested here does not close the
  QAP-cost-to-SWAP gap and is not adopted**; the shipped raw-frequency objective A0 remains the
  default. Any future objective change should first reproduce a *proven* dependence/lower-bound
  construction from the literature rather than this exploratory weighting, and ideally be
  evaluated jointly with the fidelity proxy (still unmeasured) and stronger baselines.

## Reproduce

```bash
# Six balanced slices (each writes dep_a_part<r>_*.json), then merge into
# benchmark_dependence_a_{results,raw,significance}.json (merge = concatenate results/raw and
# call analyze_a2_vs_a0 on the merged raw log).
uv run python benchmarks/benchmark_dependence_a.py --tasks 0,10,19  --out benchmarks/results/dep_a_part0
uv run python benchmarks/benchmark_dependence_a.py --tasks 1,11,18  --out benchmarks/results/dep_a_part1
uv run python benchmarks/benchmark_dependence_a.py --tasks 2,12,17  --out benchmarks/results/dep_a_part2
uv run python benchmarks/benchmark_dependence_a.py --tasks 3,13,16  --out benchmarks/results/dep_a_part3
uv run python benchmarks/benchmark_dependence_a.py --tasks 4,14,15  --out benchmarks/results/dep_a_part4
uv run python benchmarks/benchmark_dependence_a.py --tasks 5,6,7,8,9 --out benchmarks/results/dep_a_part5
```
