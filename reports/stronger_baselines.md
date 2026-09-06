# Stronger off-the-shelf router baselines (roadmap item 7)

**Question.** FAQ pre-placement has only ever been compared against *optimization_level=1*
default routers. Before claiming pre-placement is worth pursuing, it must be compared against
what an off-the-shelf user would actually run: higher Qiskit optimization levels (whose level-3
preset additionally refines the layout with **VF2PostLayout**, the VF2-family pass available in
this Qiskit version — a bare `layout_method='vf2'` plugin does not exist here). This benchmark
adds, per canonical task and seed (K=20, identical `seed_transpiler`):

* `sabre_o2` — `transpile(..., optimization_level=2)` default preset
* `sabre_o3` — `transpile(..., optimization_level=3)` default preset (adds Commutative
  Cancellation etc. and VF2PostLayout)

and compares them against the committed arms: `sabre_def` (o1 default), `faq_sabre` (hard
FAQ+SABRE), `faq_soft_sabre` (FAQ as one extra trial in SABRE's pool) and `faq_tket`
(FAQ→PyTKET). Paired Wilcoxon per row, BH over m = 88 cells.
Files: `benchmarks/results/benchmark_baselines_{results,raw,significance}.json`; generator
`benchmarks/benchmark_baselines.py`.

## Per-row means (SWAPs over 20 seeds)

| Task | Arch | N | def o1 | o2 | o3 | FAQ soft | FAQ+PyTKET | o3−def | o3−soft | o3−FAQ+TKET |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Grover's Search | Bris | 8 | 1152.2 | 1062.7 | 1059.7 | 1153.2 | 1037.0 | −93† | −94† | +23† |
| Grover's Search | Bris | 10 | 5603.1 | 5256.3 | 5348.1 | 5642.8 | 4501.1 | −255† | −295† | +847† |
| Grover's Search | Bris | 12 | 18579.0 | 18484.9 | 18468.6 | 18570.5 | 15650.5 | −110† | −102† | +2818† |
| VQE (RealAmplitudes) | Bris | 10 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | +0 | +0 | +0 |
| VQE (RealAmplitudes) | Bris | 20 | 9.6 | 9.2 | 7.7 | 9.7 | 0.9 | −2† | −2† | +7† |
| VQE (RealAmplitudes) | Bris | 50 | 30.8 | 30.8 | 30.8 | 31.1 | 7.9 | +0 | −0 | +23† |
| GHZ State | Bris | 50 | 12.0 | 12.0 | 12.0 | 12.0 | 6.0 | +0 | +0 | +6 |
| QFT | Bris | 20 | 225.0 | 210.3 | 206.5 | 222.2 | 212.0 | −18† | −16† | −6† |
| QAOA | Bris | 10 | 57.2 | 52.0 | 52.2 | 57.6 | 73.9 | −5† | −5† | −22† |
| QAOA | Bris | 20 | 308.6 | 291.3 | 295.4 | 304.2 | 387.1 | −13† | −9† | −92† |
| Grover's Search | Grid | 8 | 768.2 | 749.9 | 750.0 | 767.9 | 606.5 | −18† | −18† | +143† |
| Grover's Search | Grid | 10 | 3461.8 | 3388.6 | 3391.2 | 3452.4 | 2540.6 | −71† | −61† | +851† |
| Grover's Search | Grid | 12 | 12375.2 | 12235.1 | 12208.8 | 12365.9 | 8704.1 | −166† | −157† | +3505† |
| VQE (RealAmplitudes) | Grid | 50 | 45.7 | 35.8 | 20.8 | 39.5 | 0.9 | −25† | −19† | +20† |
| QFT | Grid | 20 | 147.9 | 140.1 | 138.9 | 148.6 | 144.5 | −9† | −10† | −6† |
| Ripple-Carry Adder | Bris | 20 | 5.0 | 5.0 | 5.0 | 3.9 | 3.2 | +0 | +1† | +2 |
| QRAM Decoder | Bris | 20 | 19.3 | 17.3 | 12.7 | 12.3 | 22.2 | −7† | +0 | −10† |
| Random 3-Regular | Bris | 20 | 36.6 | 33.0 | 30.9 | 33.0 | 49.8 | −6† | −2† | −19† |
| Ripple-Carry Adder | Grid | 20 | 7.8 | 5.8 | 3.3 | 0.9 | 0.0 | −5† | +2† | +3† |
| QRAM Decoder | Grid | 20 | 7.5 | 6.3 | 4.3 | 0.7 | 14.0 | −3† | +4† | −10† |

Δ columns = new arm − compared arm (negative = new arm better). † = significant after BH.
Bris = IBM FakeBrisbane (127q); Grid = synthetic 8×10 (80q).

## What this shows

* **Higher optimization levels dominate o1-default SABRE.** o2 beats o1 on 15/20 tasks (2 ns),
  o3 on 16/20 (1 ns); every significant delta is negative. Turning up the level is an easy,
  large win over the o1 configuration the FAQ tables used as their "default SABRE" baseline.
* **FAQ-as-trial SABRE is not worth it for SABRE users.** o3 beats the soft-candidate arm on
  13 tasks; they tie on QRAM-Brisbane and VQE-N50-Brisbane; FAQ-soft keeps a significant edge
  on exactly **3 small structural holdouts** — Ripple-Carry Brisbane (3.9 vs 5.0), Ripple-Carry
  synthetic grid (0.9 vs 3.3) and QRAM synthetic grid (0.7 vs 4.3) — i.e. VF2PostLayout-refined
  o3 still cannot find what the FAQ-trial layout finds there. If the goal is "route better than
  default SABRE", the answer is `optimization_level=3`, not FAQ pre-placement.
* **FAQ+PyTKET still wins on the big rows, against every SABRE baseline tested here.** o3 cannot
  touch FAQ+PyTKET on Grover-N10/N12 (both grids and Brisbane: e.g. 15650 vs 18469 Brisbane-N12,
  4501 vs 5348 Brisbane-N10) or VQE-N50 synthetic grid (0.9 vs 20.8). FAQ pre-placement's value
  is as an *embedding for PyTKET's LexiRoute*, not as a seed for SABRE; no SABRE-level
  configuration in this study closes that gap.
* Caveat: these are single-topology snapshots with the same synthetic-grid error caveats as
  before, and o3 adds meaningful compile time on the largest circuits (still ≤ ~1.3 s/seed here).

## Verdict for the roadmap

Item 7 answers the "is FAQ worth it vs a better router" question: **for the SABRE router
family the correct baseline is o3 (+VF2PostLayout) and FAQ pre-placement adds nothing there
(13/18 rows o3 wins); FAQ's measurable remaining value is (a) as the PyTKET/LexiRoute embedding
on large structured circuits (10 rows) and (b) on three tiny structural circuits where its
trial layout beats even o3.** This is what any future "FAQ helps" claim must be measured
against.

## Reproduce

```bash
uv run python benchmarks/benchmark_baselines.py --out benchmarks/results/baseline_full
# ~3 minutes on this machine; results + significance written as baseline_full_*.json, then
# consolidated into benchmark_baselines_{results,raw,significance}.json (see commit message).
```
