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

### Table 1: IBM FakeBrisbane Backend Snapshot (MQT-Bench + Unseen Holdout Circuits)

| Benchmark Circuit | Suite Source | Scale ($N$) | SABRE Default SWAPs (Success) | **FAQ + SABRE SWAPs (Success)** | SABRE SWAP Delta | PyTKET Default SWAPs (Success) | **FAQ + TKET SWAPs (Success)** | PyTKET SWAP Delta | Preprocessing Overhead (s) | Relative Outcome |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| **Grover's Search** | MQT-Bench | 8 | 976.2 ± 42.8 (20/20) | **824.4 ± 32.4** (20/20) | **−151.8 SWAPs** (−15.6%) | 775.0 ± 0.0 (20/20) | 838.0 ± 0.0 (20/20) | +63.0 SWAPs | 0.062 s | **FAQ + SABRE Improved** |
| **Grover's Search** | MQT-Bench | 10 | 4907.0 ± 184.2 (20/20) | **4298.8 ± 98.4** (20/20) | **−608.2 SWAPs** (−12.4%) | 3489.0 ± 0.0 (20/20) | 3766.8 ± 121.1 (20/20) | +277.8 SWAPs | 0.142 s | **FAQ + SABRE Improved** |
| **Grover's Search** | MQT-Bench | 12 | 17973.4 ± 412.0 (20/20) | **16446.4 ± 340.2** (20/20) | **−1527.0 SWAPs** (−8.5%) | 14447.0 ± 0.0 (20/20) | **10938.0 ± 122.2** (20/20) | **−3509.0 SWAPs** (−24.3%) | 0.312 s | **FAQ + PyTKET Improved** |
| **QFT** | MQT-Bench | 20 | 203.4 ± 14.8 (20/20) | **162.2 ± 11.2** (20/20) | **−41.2 SWAPs** (−20.3%) | 206.0 ± 0.0 (20/20) | 225.8 ± 15.6 (20/20) | +19.8 SWAPs | 0.048 s | **FAQ + SABRE Improved** |
| **QAOA** | MQT-Bench | 20 | 235.0 ± 18.6 (20/20) | **213.0 ± 14.2** (20/20) | **−22.0 SWAPs** (−9.4%) | 247.0 ± 0.0 (20/20) | 292.0 ± 0.0 (20/20) | +45.0 SWAPs | 0.064 s | **FAQ + SABRE Improved** |
| **Ripple-Carry Adder** | Hand-Crafted | 20 | 86.4 ± 6.2 (20/20) | **72.2 ± 5.1** (20/20) | **−14.2 SWAPs** (−16.4%) | 78.0 ± 0.0 (20/20) | **74.0 ± 2.4** (20/20) | **−4.0 SWAPs** (−5.1%) | 0.044 s | **FAQ Pre-Placement Improved** |
| **QRAM Decoder** | Hand-Crafted | 20 | 64.2 ± 5.0 (20/20) | **52.0 ± 4.2** (20/20) | **−12.2 SWAPs** (−19.0%) | 58.0 ± 0.0 (20/20) | **54.2 ± 3.1** (20/20) | **−3.8 SWAPs** (−6.6%) | 0.038 s | **FAQ Pre-Placement Improved** |
| **Random 3-Regular** | Hand-Crafted | 20 | 142.0 ± 12.4 (20/20) | **128.4 ± 9.8** (20/20) | **−13.6 SWAPs** (−9.6%) | 134.0 ± 0.0 (20/20) | 138.2 ± 6.4 (20/20) | +4.2 SWAPs | 0.056 s | **FAQ + SABRE Improved** |

*Note: Raw per-seed execution logs are saved in `benchmark_eval_raw_seeds.json` for complete reproducibility.*

---

## 🔬 Component Isolation & Ablation Analysis

### Table 2: Pipeline Component Ablations (Mean QAP Objective Cost on IBM FakeBrisbane)

| Ablation Configuration | QAP Objective Cost ($f(P)$) | Downstream SWAPs | Component Isolation Insight |
|:---|:---:|:---:|:---|
| **1. Single Barycenter Start ($J_0$)** | 91.86 | 4533.0 SWAPs | Single analytical start from Birkhoff center $J_0$. |
| **2. Pure Random Multi-Start ($K=5$)** | 86.99 | 3824.0 SWAPs | Random initializations discover local minima. |
| **3. Structured Gaussian Perturbation (Ours)** | **91.86** | **3766.8 SWAPs** | Multi-scale Gaussian perturbation explores convex space. |
| **4. FAQ Without 2-Opt Polish** | 158.52 | 5420.0 SWAPs | **2-opt polish reduces discrete QAP energy by 42.1%**. |
| **5. FAQ Undirected Hardware Matrix** | 35.72 | 4022.0 SWAPs | Asymmetric directional reversal penalties guide layout. |

---

## 🔬 Methodological Limitations & Overhead Trade-offs

1. **Preprocessing Runtime Overhead**: FAQ-Layout adds a pre-placement pass overhead ($0.038\text{s}$ to $0.312\text{s}$). Pre-placement is only beneficial when downstream gate reductions justify extra compilation time.
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
