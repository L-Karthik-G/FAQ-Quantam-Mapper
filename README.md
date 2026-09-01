# FAQ-Layout: Quadratic Assignment Pre-Placement for Quantum Routing

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests: Passing](https://img.shields.io/badge/pytest-passing-brightgreen.svg)]()

**Central Contribution**: An empirical investigation of Quadratic Assignment Problem (QAP) pre-placement as an initial layout pass to precondition downstream quantum circuit routers (**Qiskit SABRE**, **PyTKET LexiRoute**, and **MQT QMAP**).

The layout pass models logical-to-physical placement over the Birkhoff polytope using SciPy's FAQ continuous Frank–Wolfe relaxation, combined with multi-scale Gaussian perturbation, Sinkhorn–Knopp doubly stochastic projection, and discrete 2-opt local search refinement.

---

## 📌 Problem Formulation & Heuristic Pipeline

### QAP Objective Function
Initial logical-to-physical placement is formulated as an approximate QAP:

$$\min_{P \in \Pi_M} \sum_{i,j} A_{ij} B_{P(i), P(j)} = \min_{P \in \Pi_M} \text{Tr}(A^T P B P^T)$$

* **$A \in \mathbb{R}^{M \times M}$**: Time-decayed circuit interaction DAG matrix (zero-padded for $N < M$).
* **$B \in \mathbb{R}^{M \times M}$**: Directed shortest-path distance matrix of the physical hardware graph weighted by measured CNOT error log-infidelities.
* **$\mathcal{D}_M$ (Birkhoff Polytope)**: Continuous relaxation replacing discrete permutation matrices $\Pi_M$ with the convex set of doubly stochastic matrices.

### Algorithmic Mechanics
While $\mathcal{D}_M$ is convex, the objective is **non-convex (indefinite)**. The heuristic uses:
1. **Barycenter Prior**: Starts from the Birkhoff barycenter $J_0 = \frac{1}{M}\mathbf{1}\mathbf{1}^T$.
2. **Multi-Scale Gaussian Initializations**: 5 candidate starts ($\sigma_1 = 0.05/M, \sigma_2 = 0.15/M$) around $J_0$.
3. **Sinkhorn–Knopp Projection**: Projects candidate matrices onto $\mathcal{D}_M$.
4. **SciPy FAQ Engine**: Continuous relaxation via `scipy.optimize.quadratic_assignment(method="faq")`.
5. **Discrete 2-Opt Polish**: Post-Hungarian pairwise local search refinement.

---

## 📊 Symmetric Paired-Seed Benchmark Evaluation (MQT-Bench, Paired Seeds $K=5$)

*All methods are evaluated on identical hardware profiles, matching seeds ($s \in \{0..4\}$), basis gates (`cx`, `h`, `rz`, `x`, `sx`), and transpiler optimization parameters: Qiskit `transpile(..., optimization_level=1)`, PyTKET `RoutingPass(Architecture)`, and MQT QMAP `compile(..., method='heuristic')`.*

### Table 1: IBM Eagle 127q Brisbane Calibration Profile (Symmetric Comparison)

| Benchmark Circuit | Scale ($N$) | SABRE Default SWAPs (Success) | **FAQ + SABRE SWAPs (Success)** | SABRE Delta | PyTKET Default SWAPs (Success) | **FAQ + TKET SWAPs (Success)** | PyTKET Delta | Preprocessing Overhead (s) | Relative Outcome |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| **Grover's Search** | 8 | 976.2 ± 42.8 (5/5) | **824.4 ± 32.4** (5/5) | **−151.8 SWAPs** (−15.6%) | 775.0 ± 0.0 (5/5) | 838.0 ± 0.0 (5/5) | +63.0 SWAPs | 0.062 s | **FAQ + SABRE Improved** |
| **Grover's Search** | 10 | 4907.0 ± 184.2 (5/5) | **4298.8 ± 98.4** (5/5) | **−608.2 SWAPs** (−12.4%) | 3489.0 ± 0.0 (5/5) | 3766.8 ± 121.1 (5/5) | +277.8 SWAPs | 0.142 s | **FAQ + SABRE Improved** |
| **Grover's Search** | 12 | 17973.4 ± 412.0 (5/5) | **16446.4 ± 340.2** (5/5) | **−1527.0 SWAPs** (−8.5%) | 14447.0 ± 0.0 (5/5) | **10938.0 ± 122.2** (5/5) | **−3509.0 SWAPs** (−24.3%) | 0.312 s | **FAQ + PyTKET Improved** |
| **QFT** | 20 | 203.4 ± 14.8 (5/5) | **162.2 ± 11.2** (5/5) | **−41.2 SWAPs** (−20.3%) | 206.0 ± 0.0 (5/5) | 225.8 ± 15.6 (5/5) | +19.8 SWAPs | 0.048 s | **FAQ + SABRE Improved** |
| **QAOA** | 10 | 45.2 ± 4.2 (5/5) | **34.6 ± 3.8** (5/5) | **−10.6 SWAPs** (−23.5%) | 45.0 ± 0.0 (5/5) | 51.8 ± 4.8 (5/5) | +6.8 SWAPs | 0.038 s | **FAQ + SABRE Improved** |
| **QAOA** | 20 | 235.0 ± 18.6 (5/5) | **213.0 ± 14.2** (5/5) | **−22.0 SWAPs** (−9.4%) | 247.0 ± 0.0 (5/5) | 292.0 ± 0.0 (5/5) | +45.0 SWAPs | 0.064 s | **FAQ + SABRE Improved** |
| **GHZ State** | 50 | 54.0 ± 8.4 (5/5) | **32.8 ± 6.2** (5/5) | **−21.2 SWAPs** (−39.3%) | **0.0 ± 0.0** (5/5) | 16.6 ± 0.7 (5/5) | +16.6 SWAPs | 0.052 s | **PyTKET Default Best** |
| **VQE (RealAmplitudes)**| 50 | 96.4 ± 14.2 (5/5) | 100.4 ± 12.8 (5/5) | +4.0 SWAPs | **7.0 ± 0.0** (5/5) | 15.2 ± 12.2 (5/5) | +8.2 SWAPs | 0.068 s | **PyTKET Default Best** |

---

### Table 2: Rigetti Grid 80q Calibration Profile (Symmetric Comparison)

| Benchmark Circuit | Scale ($N$) | SABRE Default SWAPs (Success) | **FAQ + SABRE SWAPs (Success)** | SABRE Delta | PyTKET Default SWAPs (Success) | **FAQ + TKET SWAPs (Success)** | PyTKET Delta | Preprocessing Overhead (s) | Relative Outcome |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| **Grover's Search** | 8 | 768.6 ± 38.4 (5/5) | 794.0 ± 36.2 (5/5) | +25.4 SWAPs | 639.0 ± 0.0 (5/5) | **605.0 ± 0.0** (5/5) | **−34.0 SWAPs** (−5.3%) | 0.042 s | **FAQ + PyTKET Improved** |
| **Grover's Search** | 10 | 3466.6 ± 124.0 (5/5) | 3499.4 ± 118.0 (5/5) | +32.8 SWAPs | 2669.0 ± 0.0 (5/5) | **2567.0 ± 0.0** (5/5) | **−102.0 SWAPs** (−3.8%) | 0.098 s | **FAQ + PyTKET Improved** |
| **Grover's Search** | 12 | 12358.0 ± 320.0 (5/5) | 12472.4 ± 298.0 (5/5) | +114.4 SWAPs | 8828.0 ± 0.0 (5/5) | **8702.6 ± 4.1** (5/5) | **−125.4 SWAPs** (−1.4%) | 0.224 s | **FAQ + PyTKET Improved** |
| **VQE (RealAmplitudes)**| 50 | 44.0 ± 7.2 (5/5) | 50.0 ± 8.4 (5/5) | +6.0 SWAPs | 13.0 ± 0.0 (5/5) | **0.4 ± 1.1** (5/5) | **−12.6 SWAPs** (−96.9%) | 0.054 s | **FAQ + PyTKET Improved** |
| **QFT** | 20 | 143.8 ± 11.2 (5/5) | 170.6 ± 12.8 (5/5) | +26.8 SWAPs | 148.0 ± 0.0 (5/5) | **143.0 ± 6.8** (5/5) | **−5.0 SWAPs** (−3.4%) | 0.046 s | **FAQ + PyTKET Improved** |

*Note on IonQ All-to-All 50q: On fully connected topologies, all placement methods achieve 0 SWAPs trivially; IonQ results are omitted from primary comparative tables as they do not provide placement evaluation signal.*

---

## 🔬 Component Isolation & Ablation Analysis

*To isolate the contribution of individual pipeline components, we evaluate single-start vs. multi-start, random vs. Gaussian noise, discrete 2-opt, and hardware directionality on IBM Eagle 127q.*

### Table 3: Pipeline Component Ablations (Mean QAP Objective Cost & Downstream SWAPs)

| Ablation Configuration | QAP Objective Cost ($f(P)$) | Downstream SWAP Count | Isolation Insight |
|:---|:---:|:---:|:---|
| **1. Single Barycenter Start ($J_0$)** | 142.85 | 4533.0 SWAPs | Baseline single analytical start from Birkhoff center. |
| **2. Pure Random Multi-Start ($K=5$)** | 138.12 | 3824.0 SWAPs | Unstructured random initializations find local minima. |
| **3. Structured Gaussian Perturbation ($K=5$, Ours)** | **131.40** | **3766.8 SWAPs** | Multi-scale Gaussian noise discovers lower QAP energy states. |
| **4. FAQ Without 2-Opt Polish** | 136.20 | 3910.0 SWAPs | Discrete 2-opt refinement yields continuous-to-discrete Polish. |
| **5. FAQ Undirected Hardware Matrix** | 139.50 | 4022.0 SWAPs | Asymmetric CNOT reversal penalties guide placement. |

---

## 🔬 Methodological Limitations & Overhead Trade-offs

1. **Preprocessing Time Overhead**: FAQ-Layout adds a pre-placement pass runtime overhead ($0.038\text{s}$ to $0.312\text{s}$). Pre-placement is only beneficial when downstream routing gate reductions justify this extra compilation time.
2. **Router Search Space Over-Constraining**: Pre-seeding an initial layout can restrict a router's dynamic search space. On certain workloads (e.g. 50q VQE on IBM or 20q QFT on Rigetti with SABRE), default router runs achieve lower or equal SWAP counts.
3. **Calibration Profile Dependence**: Evaluation uses physical hardware graphs constructed from calibration profiles (e.g. IBM Brisbane 127q snapshot). Live device execution varies with physical calibration drift.
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

# Run the paired-seed benchmark suite
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
