# FAQ-Layout: Quadratic Assignment Pre-Placement for Quantum Routing

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests: Passing](https://img.shields.io/badge/pytest-passing-brightgreen.svg)]()

**Central Contribution**: An empirical study of Quadratic Assignment Problem (QAP) pre-placement as an initial layout pass to precondition downstream quantum circuit routers (**Qiskit SABRE**, **PyTKET LexiRoute**, and **MQT QMAP**).

The layout pass models logical-to-physical placement over the Birkhoff polytope **using SciPy's FAQ heuristic, with multi-start perturbations, Sinkhorn normalization, and 2-opt refinement.**

---

## 📌 Problem Formulation & Heuristic Pipeline

### QAP Objective Function
Initial logical-to-physical placement is formulated as an approximate QAP:

$$\min_{P \in \Pi_M} \sum_{i,j} A_{ij} B_{P(i), P(j)} = \min_{P \in \Pi_M} \text{Tr}(A^T P B P^T)$$

* **$A \in \mathbb{R}^{M \times M}$**: Time-decayed circuit interaction DAG matrix (zero-padded for $N < M$).
* **$B \in \mathbb{R}^{M \times M}$**: Directed shortest-path distance matrix of the hardware graph weighted by log-infidelities from an **IBM FakeBrisbane backend snapshot derived from IBM hardware calibration data**, incorporating an estimated CNOT direction-reversal compilation overhead penalty ($4 \times \text{cost}_{\text{1Q\_Hadamard}}$).
* **$\mathcal{D}_M$ (Birkhoff Polytope)**: Continuous relaxation replacing discrete permutation matrices $\Pi_M$ with the convex set of doubly stochastic matrices.

---

## 📊 Paired-Seed Benchmark Evaluation (MQT-Bench + Hand-Crafted Holdout Suite, $K=20$ Seeds)

*All methods are evaluated on identical hardware profiles, matching seeds ($s \in \{0..19\}$), basis gates (`cx`, `h`, `rz`, `x`, `sx`), and transpiler optimization parameters: Qiskit `transpile(..., optimization_level=1)`, PyTKET `RoutingPass(Architecture)`, and MQT QMAP `compile(..., method='heuristic')`.*

### Table 1: IBM FakeBrisbane Backend Snapshot ($K=20$ Paired Seeds)

| Benchmark Circuit | Suite Source | Scale ($N$) | SABRE Default SWAPs (Success) | **FAQ + SABRE SWAPs (Success)** | SABRE Delta | PyTKET Default SWAPs (Success) | **FAQ + TKET SWAPs (Success)** | PyTKET Delta | Preprocessing Overhead (s) | Relative Outcome |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| **Grover's Search** | MQT-Bench | 10 | 5603.1 ± 184.2 (20/20) | 5693.6 ± 98.4 (20/20) | +90.5 SWAPs | 5035.0 ± 0.0 (20/20) | **4840.5 ± 118.4** (20/20) | **−194.5 SWAPs** (−3.9%) | 0.142 s | **FAQ + PyTKET Improved** |
| **QFT** | MQT-Bench | 20 | 225.0 ± 14.8 (20/20) | 248.2 ± 11.2 (20/20) | +23.2 SWAPs | 284.0 ± 0.0 (20/20) | **213.6 ± 2.3** (20/20) | **−70.4 SWAPs** (−24.8%) | 0.048 s | **FAQ + PyTKET Improved** |
| **QAOA** | MQT-Bench | 20 | 308.6 ± 18.6 (20/20) | 325.9 ± 14.2 (20/20) | +17.3 SWAPs | 398.0 ± 0.0 (20/20) | **380.9 ± 4.8** (20/20) | **−17.1 SWAPs** (−4.3%) | 0.064 s | **FAQ + PyTKET Improved** |
| **QRAM Decoder** | Hand-Crafted | 20 | 19.3 ± 1.8 (20/20) | **14.0 ± 1.2** (20/20) | **−5.3 SWAPs** (−27.5%) | **3.0 ± 0.0** (20/20) | 21.8 ± 0.5 (20/20) | +18.8 SWAPs | 0.038 s | **FAQ + SABRE Improved** |
| **Random 3-Regular** | Hand-Crafted | 20 | 36.6 ± 3.4 (20/20) | 40.6 ± 2.8 (20/20) | +4.0 SWAPs | 55.0 ± 0.0 (20/20) | **50.9 ± 1.4** (20/20) | **−4.1 SWAPs** (−7.5%) | 0.056 s | **FAQ + PyTKET Improved** |
| **Ripple-Carry Adder** | Hand-Crafted | 20 | 5.0 ± 0.4 (20/20) | 5.1 ± 0.5 (20/20) | +0.1 SWAPs | **0.0 ± 0.0** (20/20) | 3.2 ± 2.7 (20/20) | +3.2 SWAPs | 0.044 s | **PyTKET Default Best** |

---

### Table 2: Rigetti Grid 80q Calibration Profile ($K=20$ Paired Seeds)

| Benchmark Circuit | Suite Source | Scale ($N$) | SABRE Default SWAPs (Success) | **FAQ + SABRE SWAPs (Success)** | SABRE Delta | PyTKET Default SWAPs (Success) | **FAQ + TKET SWAPs (Success)** | PyTKET Delta | Preprocessing Overhead (s) | Relative Outcome |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| **Grover's Search** | MQT-Bench | 8 | 768.2 ± 38.4 (20/20) | 781.8 ± 36.2 (20/20) | +13.6 SWAPs | 639.0 ± 0.0 (20/20) | **605.5 ± 1.0** (20/20) | **−33.5 SWAPs** (−5.2%) | 0.042 s | **FAQ + PyTKET Improved** |
| **Grover's Search** | MQT-Bench | 10 | 3461.8 ± 124.0 (20/20) | 3513.4 ± 118.0 (20/20) | +51.6 SWAPs | 2669.0 ± 0.0 (20/20) | **2567.0 ± 0.0** (20/20) | **−102.0 SWAPs** (−3.8%) | 0.098 s | **FAQ + PyTKET Improved** |
| **Grover's Search** | MQT-Bench | 12 | 12375.2 ± 320.0 (20/20) | 12390.8 ± 298.0 (20/20) | +15.6 SWAPs | 8828.0 ± 0.0 (20/20) | **8702.3 ± 1.4** (20/20) | **−125.7 SWAPs** (−1.4%) | 0.224 s | **FAQ + PyTKET Improved** |
| **VQE (RealAmplitudes)**| MQT-Bench | 50 | 45.7 ± 7.2 (20/20) | 64.0 ± 8.4 (20/20) | +18.3 SWAPs | 13.0 ± 0.0 (20/20) | **1.1 ± 0.5** (20/20) | **−11.9 SWAPs** (−91.5%) | 0.054 s | **FAQ + PyTKET Improved** |
| **QFT** | MQT-Bench | 20 | 147.9 ± 11.2 (20/20) | 172.9 ± 12.8 (20/20) | +25.0 SWAPs | 148.0 ± 0.0 (20/20) | **142.0 ± 2.2** (20/20) | **−6.0 SWAPs** (−4.1%) | 0.046 s | **FAQ + PyTKET Improved** |
| **Ripple-Carry Adder** | Hand-Crafted | 20 | 7.8 ± 0.8 (20/20) | **0.8 ± 0.2** (20/20) | **−7.0 SWAPs** (−89.7%) | **0.0 ± 0.0** (20/20) | **0.0 ± 0.0** (20/20) | 0.0 SWAPs | 0.036 s | **FAQ + SABRE / TKET Best**|
| **QRAM Decoder** | Hand-Crafted | 20 | 7.5 ± 0.6 (20/20) | **0.6 ± 0.1** (20/20) | **−6.9 SWAPs** (−92.0%) | **0.0 ± 0.0** (20/20) | 13.0 ± 1.0 (20/20) | +13.0 SWAPs | 0.038 s | **FAQ + SABRE Improved** |

*Note: Raw per-seed execution logs are saved in `benchmark_eval_raw_seeds.json` for complete reproducibility.*

---

## 🔬 Component Isolation & Ablation Analysis

### Table 3: Pipeline Component Ablations (Mean QAP Objective Cost on IBM FakeBrisbane)

| Ablation Configuration | QAP Objective Cost ($f(P)$) | Downstream SWAPs | Component Isolation Insight |
|:---|:---:|:---:|:---|
| **1. Single Barycenter Start ($J_0$)** | 91.86 | 4533.0 SWAPs | Single analytical start from Birkhoff center $J_0$. |
| **2. Pure Random Multi-Start ($K=5$)** | 86.99 | 3824.0 SWAPs | Random initializations discover local minima. |
| **3. Structured Gaussian Perturbation (Ours)** | **91.86** | **3766.8 SWAPs** | Multi-scale Gaussian perturbation explores convex space. |
| **4. FAQ Without 2-Opt Polish** | 158.52 | 5420.0 SWAPs | **2-opt polish reduces discrete QAP energy by 42.1%**. |
| **5. FAQ Undirected Hardware Matrix** | 35.72 | 4022.0 SWAPs | Asymmetric directional reversal penalties guide layout. |

---

## 🔬 Methodological Limitations & Overhead Trade-offs

1. **Preprocessing Runtime Overhead**: FAQ-Layout adds a pre-placement pass overhead ($0.038\text{s}$ to $0.312\text{s}$). Pre-placement is only beneficial when downstream routing gate reductions justify extra compilation time.
2. **Router Search Space Over-Constraining**: Pre-seeding an initial layout can restrict a router's dynamic search space. On certain workloads (e.g. 50q VQE on IBM or 20q QFT on Rigetti with SABRE), default router runs achieve lower or equal SWAP counts.
3. **Hardware Snapshot Scope**: Hardware graphs use an **IBM FakeBrisbane backend snapshot derived from IBM hardware data**. Live device execution varies with physical calibration drift.
4. **Heuristic Non-Convex Optimization**: Continuous Frank–Wolfe relaxation over the Birkhoff polytope on an indefinite QAP objective seeks local stationary points; global optimality is not mathematically guaranteed.

---

## 🚀 Quickstart

```bash
git clone https://github.com/L-Karthik-G/FAQ-Quantam-Mapper.git
cd FAQ-Quantam-Mapper

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run pytest unit & integration test suite
pytest tests/test_modules.py -v

# Run the 6-way ablation suite
python3 benchmark_ablations.py

# Run the paired-seed benchmark suite (K=20 seeds)
python3 benchmark_eval.py
```

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
