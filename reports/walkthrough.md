# FAQ-Layout: Quadratic Assignment Pre-Placement for Quantum Routing

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Central Contribution**: An empirical evaluation of an approximate Quadratic Assignment
Problem (QAP) pre-placement pass that pre-seeds the initial layout of downstream quantum
circuit routers (Qiskit SABRE and PyTKET LexiRoute) and measures whether it reduces the number
of SWAP gates they emit.

FAQ-Layout is a pre-placement heuristic that wraps SciPy's
`quadratic_assignment(method="faq")` and adds multi-start Gaussian perturbations, Sinkhorn
normalization, and a discrete 2-opt refinement. It is an *empirical compilation heuristic*,
not a new continuous-optimization theory result. The benchmark evaluates routers on a fixed,
recorded hardware calibration snapshot; it does **not** run on live quantum hardware.

> **Scope note.** This repository contains several experiment rounds. The **canonical,
> reproducible paired-seed dataset is `benchmark_eval_results.json`** (with its raw per-seed
> log `benchmark_eval_raw_seeds.json`), produced by `benchmark_eval.py` over the 20 tasks in
> Tables 1–2 below (K=20 seeds, Qiskit `optimization_level=1`). Older `*_results.json` files
> in the repo root come from earlier rounds that used different seeds, topologies, or
> `optimization_level` settings; they are kept for history and are **not** the numbers cited in
> this README. See [Data provenance & reproduction](#-data-provenance--reproduction).

---

## 📌 Problem Formulation & Heuristic Pipeline

### QAP Objective Function

Initial logical-to-physical placement is modeled as an approximate QAP:

$$\min_{P \in \Pi_M} \sum_{i,j} A_{ij} B_{P(i), P(j)} = \min_{P \in \Pi_M} \text{Tr}(A^T P B P^T)$$

* **$A \in \mathbb{R}^{M \times M}$**: Time-decayed circuit interaction DAG matrix
  (zero-padded for $N < M$).
* **$B \in \mathbb{R}^{M \times M}$**: Directed shortest-path distance matrix of the hardware
  graph weighted by log-infidelities from a Qiskit **`FakeBrisbane`** fake backend object
  (IBM's archived Brisbane calibration properties; **not** live QPU execution), plus an
  estimated CNOT direction-reversal overhead ($4 \times \text{cost}_{\text{1Q\_Hadamard}}$).
* **$\mathcal{D}_M$ (Birkhoff polytope)**: the doubly-stochastic relaxation used internally by
  SciPy's FAQ method. FAQ returns a discrete permutation; its reported cost is the discrete QAP
  cost of that permutation (the relaxation value is not exposed by SciPy and is **not** claimed
  here as a "continuous cost").

Heuristic pipeline: build $A$ and $B$ → solve the QAP by FAQ from 5 starts (1 barycenter +
2 small-noise + 2 medium-noise Gaussian Sinkhorn projections) → keep the lowest-cost
permutation → apply a discrete 2-opt local search → hand the resulting layout to the router.

---

## 📊 Paired-Seed Benchmark (MQT-Bench + Hand-Crafted Holdout Suite, $K=20$ Seeds)

*All methods share identical hardware profiles, matching seeds ($s \in \{0..19\}$), basis gates
(`cx`, `h`, `rz`, `x`, `sx`), and router options: Qiskit `transpile(..., optimization_level=1)`
with `seed_transpiler=s`, and PyTKET `PlacementPass(GraphPlacement)` + `RoutingPass` (default)
vs. FAQ-embedding + `RoutingPass`. Values are **mean ± 95% CI over the 20 paired seeds**; all
rows achieved 20/20 successful compilations. "Lower-SWAP method" reports the strictly-lower
mean for each router pair.*

### Table 1: IBM FakeBrisbane (127-qubit Heavy-Hex), K=20 paired seeds

| Benchmark Circuit | Suite | Scale $N$ | **SABRE Default** | **FAQ+SABRE** | **Δ (SABRE)** | **PyTKET Default** | **FAQ+PyTKET** | **Δ (PyTKET)** | **FAQ Preproc. (s)** | **Lower-SWAP method** |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| **Grover's Search** | MQT-Bench | 8 | 1152.2 ± 30.4 | 1263.5 ± 31.7 | +111.3 (+9.7%) | 851.0 ± 0.0 | 1039.0 ± 8.8 | +188.0 (+22.1%) | 3.932 | SABRE Def / PyTKET Def |
| **Grover's Search** | MQT-Bench | 10 | 5603.1 ± 141.8 | 5693.6 ± 92.7 | +90.4 (+1.6%) | 5035.0 ± 0.0 | 4840.4 ± 118.4 | -194.6 (-3.9%) | 4.397 | SABRE Def / FAQ+PyTKET |
| **Grover's Search** | MQT-Bench | 12 | 18579.0 ± 27.3 | 18625.3 ± 69.2 | +46.3 (+0.2%) | 12610.0 ± 0.0 | 15669.1 ± 22.2 | +3059.1 (+24.3%) | 4.794 | SABRE Def / PyTKET Def |
| **VQE (RealAmplitudes)** | MQT-Bench | 10 | 0.0 ± 0.0 | 0.0 ± 0.0 | +0.0 (n/a) | 0.0 ± 0.0 | 0.0 ± 0.0 | +0.0 (n/a) | 3.354 | Tie / Tie |
| **VQE (RealAmplitudes)** | MQT-Bench | 20 | 9.6 ± 0.4 | 23.5 ± 4.3 | +13.9 (+144.8%) | 0.0 ± 0.0 | 0.6 ± 0.6 | +0.6 (n/a) | 4.436 | SABRE Def / PyTKET Def |
| **VQE (RealAmplitudes)** | MQT-Bench | 50 | 30.8 ± 0.3 | 158.8 ± 17.0 | +128.1 (+416.4%) | 12.0 ± 0.0 | 12.4 ± 3.0 | +0.4 (+3.7%) | 4.617 | SABRE Def / PyTKET Def |
| **GHZ State** | MQT-Bench | 50 | 12.0 ± 0.0 | 58.9 ± 8.5 | +46.9 (+390.8%) | 0.0 ± 0.0 | 6.0 ± 0.0 | +6.0 (n/a) | 4.687 | SABRE Def / PyTKET Def |
| **QFT** | MQT-Bench | 20 | 225.0 ± 3.4 | 248.2 ± 6.3 | +23.2 (+10.3%) | 284.0 ± 0.0 | 213.6 ± 2.3 | -70.4 (-24.8%) | 1.977 | SABRE Def / FAQ+PyTKET |
| **QAOA** | MQT-Bench | 10 | 57.2 ± 1.8 | 72.5 ± 2.3 | +15.3 (+26.8%) | 79.0 ± 0.0 | 73.0 ± 0.0 | -6.0 (-7.6%) | 2.954 | SABRE Def / FAQ+PyTKET |
| **QAOA** | MQT-Bench | 20 | 308.6 ± 4.2 | 325.9 ± 6.6 | +17.3 (+5.6%) | 398.0 ± 0.0 | 380.9 ± 4.8 | -17.1 (-4.3%) | 2.686 | SABRE Def / FAQ+PyTKET |
| **Ripple-Carry Adder** | Hand-Crafted | 20 | 5.0 ± 0.0 | 5.1 ± 1.4 | +0.1 (+2.0%) | 0.0 ± 0.0 | 3.2 ± 2.7 | +3.2 (n/a) | 3.334 | SABRE Def / PyTKET Def |
| **QRAM Decoder** | Hand-Crafted | 20 | 19.3 ± 1.0 | 14.0 ± 1.4 | -5.3 (-27.5%) | 3.0 ± 0.0 | 21.8 ± 0.5 | +18.8 (+626.7%) | 3.749 | FAQ+SABRE / PyTKET Def |
| **Random 3-Regular** | Hand-Crafted | 20 | 36.6 ± 1.1 | 40.6 ± 2.3 | +4.0 (+10.9%) | 55.0 ± 0.0 | 50.9 ± 1.4 | -4.1 (-7.5%) | 3.328 | SABRE Def / FAQ+PyTKET |

### Table 2: Rigetti Grid (80-qubit), K=20 paired seeds

| Benchmark Circuit | Suite | Scale $N$ | **SABRE Default** | **FAQ+SABRE** | **Δ (SABRE)** | **PyTKET Default** | **FAQ+PyTKET** | **Δ (PyTKET)** | **FAQ Preproc. (s)** | **Lower-SWAP method** |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| **Grover's Search** | MQT-Bench | 8 | 768.2 ± 4.3 | 781.8 ± 8.1 | +13.5 (+1.8%) | 639.0 ± 0.0 | 605.5 ± 1.0 | -33.5 (-5.2%) | 1.422 | SABRE Def / FAQ+PyTKET |
| **Grover's Search** | MQT-Bench | 10 | 3461.8 ± 13.2 | 3513.4 ± 18.1 | +51.7 (+1.5%) | 2669.0 ± 0.0 | 2567.0 ± 0.0 | -102.0 (-3.8%) | 1.733 | SABRE Def / FAQ+PyTKET |
| **Grover's Search** | MQT-Bench | 12 | 12375.2 ± 27.0 | 12390.8 ± 54.0 | +15.5 (+0.1%) | 8828.0 ± 0.0 | 8702.3 ± 1.4 | -125.7 (-1.4%) | 2.391 | SABRE Def / FAQ+PyTKET |
| **VQE (RealAmplitudes)** | MQT-Bench | 50 | 45.7 ± 5.0 | 64.0 ± 7.8 | +18.3 (+40.0%) | 13.0 ± 0.0 | 1.1 ± 0.5 | -11.9 (-91.5%) | 1.510 | SABRE Def / FAQ+PyTKET |
| **QFT** | MQT-Bench | 20 | 147.9 ± 2.3 | 172.9 ± 3.0 | +25.0 (+16.9%) | 148.0 ± 0.0 | 142.0 ± 2.2 | -6.0 (-4.1%) | 1.496 | SABRE Def / FAQ+PyTKET |
| **Ripple-Carry Adder** | Hand-Crafted | 20 | 7.8 ± 0.8 | 0.8 ± 0.5 | -7.1 (-90.4%) | 0.0 ± 0.0 | 0.0 ± 0.0 | +0.0 (n/a) | 1.434 | FAQ+SABRE / Tie |
| **QRAM Decoder** | Hand-Crafted | 20 | 7.5 ± 0.7 | 0.6 ± 0.4 | -7.0 (-92.1%) | 0.0 ± 0.0 | 13.0 ± 1.0 | +13.0 (n/a) | 1.311 | FAQ+SABRE / PyTKET Def |

### What these data actually show

* **FAQ + PyTKET** reduces SWAPs versus PyTKET's own `GraphPlacement` on every Rigetti-Grid
  task except the (already SWAP-free) holdouts, and on several IBM tasks (Grover-N10, QFT,
  QAOA, Random 3-regular). The largest consistent win is VQE-N50 on Rigetti (−11.9 SWAPs,
  −91.5%).
* **FAQ + SABRE rarely helps.** It is worse than default SABRE on essentially all MQT-Bench
  tasks (VQE/GHZ on IBM by 100–400%, Grover by +0.2% to +9.7%); it only beats default SABRE on
  three rows of the hand-crafted holdouts — QRAM on IBM (19.3→14.0) and Ripple-Carry Adder /
  QRAM on Rigetti (7.8→0.8 and 7.5→0.6). Pre-seeding a layout can *over-constrain* SABRE's own
  search, so a worse FAQ layout than SABRE would find on its own cannot always be recovered by
  routing.
* FAQ + PyTKET is **not** uniformly better even on IBM: on Grover-N8 (+22%) and Grover-N12
  (+24%) it is substantially *worse* than PyTKET default. Gains are workload- and size-specific,
  not a blanket improvement.
* Default routers are already optimal (0–3 SWAPs) on the easiest circuits (VQE-N10, Ripple,
  QRAM holdouts on Rigetti); there is no room for FAQ to help there, and it often adds swaps.

All raw per-seed values (each of the 20 seeds, per method, with explicit success/failure) are
in `benchmark_eval_raw_seeds.json`.

---

## 🔬 Component Ablations (QAP-cost level, IBM FakeBrisbane, Grover N=10)

`benchmark_ablations.py` measures each solver configuration's **QAP objective value only**
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

Interpretation, scoped to this single circuit/seed:

* **2-opt polish (isolated, rows 1 vs 4):** with a fixed barycenter start, 2-opt lowers the QAP
  cost from 166.51 to 91.86 (−44.8%). This is the clean measure of the 2-opt contribution.
* **Multi-start Gaussian (row 3) vs. single barycenter (row 1):** the best-of-5 Gaussian FAQ
  cost is 122.12 vs 166.51 (−26.7%); versus best-of-5 random (156.41) it is −21.9%. Part of the
  gain is simply the min-over-K effect, so these figures are **not** a pure "Gaussian-noise"
  effect.
* **Random vs. Gaussian:** after 2-opt the random multi-start (86.99) is essentially as good as
  the Gaussian multi-start (88.31) on this example — the Gaussian scheme is not decisively
  better than random once 2-opt is applied.
* These are QAP-cost proxies on one circuit. They are consistent with — but do not alone
  establish — the routing results in Tables 1–2.

---

## Limitations & When to Use It

* **Real overhead is seconds, not sub-second.** FAQ pre-placement measured ~1.3–4.8 s per
  circuit here (Tables 1–2). That is far from negligible, so it is only justified when the
  routed circuit is itself large/multi-iteration (e.g. repeated VQE/QAOA layers) and the SWAP
  savings outweigh the one-time cost.
* **FAQ+SABRE usually makes routing worse** on these benchmarks; prefer default SABRE. The
  FAQ-seeded gain is specific to PyTKET routing on the Rigetti grid and on several IBM tasks.
* **Not a blanket improvement.** On IBM, FAQ+PyTKET *hurts* Grover at N=8 and N=12, and gains
  nothing on VQE/GHZ. The README's earlier recommendation "use it for large Grover/search
  circuits" is **not** supported by the data and has been removed.
* **Over-constraining:** pre-seeding an initial layout can restrict a router's search space.
* **Hardware snapshot scope:** results use an IBM `FakeBrisbane` snapshot (archived calibration
  data) and a synthetic Rigetti profile, **not** live physical hardware; live results vary with
  calibration drift.
* **Heuristic, non-convex:** FAQ seeks local solutions of an indefinite QAP over the Birkhoff
  polytope; no global-optimality guarantee.
* The ablation table is a single-circuit, single-seed cost study; see the caveats in its section.

---

## 📌 Data provenance & reproduction

Canonical paired-seed dataset (this README's Tables 1–2):

| File | Contents | Produced by |
|:---|:---|:---|
| `benchmark_eval_results.json` | Summary (mean, 95% CI, success) per task/method | `benchmark_eval.py` |
| `benchmark_eval_raw_seeds.json` | Raw per-seed SWAP/time/prep logs (all 20 seeds) | `benchmark_eval.py` |
| `benchmark_ablation_results.json` | QAP-cost ablation table | `benchmark_ablations.py` |

The benchmark scripts write their outputs **into this repository** (relative to each script),
so re-running them regenerates the files above. Older, mutually-inconsistent experiment rounds
(e.g. `benchmark_2_results.json`, `benchmark_results.json`, `benchmark_statistical_results.json`,
`benchmark_rigorous_results.json`, `benchmark_new_circuits_results.json`,
`benchmark_tket_all_results.json`, `benchmark_fgea_results.json`, `qft_scaling_results.json`
and their generators) used different seeds, topologies, or `optimization_level` settings and are
**not** the numbers reported here. They have been archived under `historical/` (see
`historical/README.md`) for provenance only. The previously contradictory
`reports/complete_benchmark_table.md` has been rewritten as a data provenance note. Treat the
three files in the table above as the authoritative dataset and regenerate before drawing
conclusions.

---

## 🚀 Quickstart

```bash
git clone https://github.com/L-Karthik-G/FAQ-Quantam-Mapper.git
cd FAQ-Quantam-Mapper

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the unit & integration test suite
pytest tests/test_modules.py -v

# Regenerate the QAP-cost ablation table (writes benchmark_ablation_results.json in-repo)
python3 benchmark_ablations.py

# Regenerate the paired-seed benchmark suite (K=20 seeds; writes results in-repo).
# NOTE: this runs full Qiskit/PyTKET routing and can take a long time.
python3 benchmark_eval.py
```

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
