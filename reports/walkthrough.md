# FAQ-Layout: Quadratic Assignment Pre-Placement for Quantum Routing

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests: Passing](https://img.shields.io/badge/pytest-passing-brightgreen.svg)]()

**FAQ-Layout** is an initial placement heuristic for quantum circuit compilation. It formulates logical-to-physical qubit layout as an approximate Quadratic Assignment Problem (QAP) over the Birkhoff polytope, solved via continuous Frank–Wolfe relaxation (SciPy FAQ engine) with multi-scale Gaussian perturbation, Sinkhorn–Knopp projection, and discrete 2-opt refinement.

It provides pre-placement initial layouts to downstream quantum routers such as **PyTKET (LexiRoute)**, **Qiskit SABRE**, and **MQT QMAP**.

---

## 📌 Method Overview & Mathematical Framing

### Problem Formulation
Initial placement is modeled as an approximate QAP:

$$\min_{P \in \Pi_M} \sum_{i,j} A_{ij} B_{P(i), P(j)} = \min_{P \in \Pi_M} \text{Tr}(A^T P B P^T)$$

* **$A \in \mathbb{R}^{M \times M}$**: Time-decayed circuit interaction DAG matrix (zero-padded for $N < M$).
* **$B \in \mathbb{R}^{M \times M}$**: Directed shortest-path distance matrix of the hardware coupling graph weighted by physical CNOT error log-infidelities.
* **$\mathcal{D}_M$ (Birkhoff Polytope)**: The continuous relaxation replaces discrete permutation matrices $\Pi_M$ with the convex set of doubly stochastic matrices.

### Optimization Mechanics
While the domain $\mathcal{D}_M$ is convex, the objective function is **non-convex (indefinite)**. FAQ-Layout uses:
1. **Barycenter Analytical Prior**: Starts from the Birkhoff barycenter $J_0 = \frac{1}{M}\mathbf{1}\mathbf{1}^T$.
2. **Multi-Scale Gaussian Perturbations**: 5 Gaussian starts ($\sigma_1 = 0.05/M, \sigma_2 = 0.15/M$) around $J_0$.
3. **Sinkhorn–Knopp Projection**: Normalizes candidate matrices onto $\mathcal{D}_M$.
4. **Discrete 2-Opt Polish**: Post-Hungarian discrete local search refinement.

---

## 📊 Summary Benchmark Evaluation (MQT-Bench, Paired Seeds $K=5$)

*Direct paired comparisons of default routers vs. FAQ pre-seeded routers on standard algorithmic circuits (no noise injection).*

### Architecture: IBM Eagle 127q Brisbane Calibration Profile

| Benchmark | Scale ($N$) | SABRE Default | **FAQ + SABRE (Ours)** | SABRE SWAP Delta | PyTKET Default | **FAQ + TKET (Ours)** | PyTKET SWAP Delta |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Grover's Search** | 8 | 976.2 | **824.4 ± 32.4** ★ | **−151.8 SWAPs** (−15.6%) | 775.0 | 838.0 ± 0.0 | +63.0 SWAPs |
| **Grover's Search** | 10 | 4907.0 | **4298.8 ± 98.4** ★ | **−608.2 SWAPs** (−12.4%) | 3489.0 | **3766.8 ± 121.1** | +277.8 SWAPs |
| **Grover's Search** | 12 | 17973.4 | **16446.4 ± 340.2** ★ | **−1527.0 SWAPs** (−8.5%) | 14447.0 | **10938.0 ± 122.2** ★ | **−3509.0 SWAPs** (−24.3%) |
| **QFT** | 20 | 203.4 | **162.2 ± 11.2** ★ | **−41.2 SWAPs** (−20.3%) | 206.0 | 225.8 ± 15.6 | +19.8 SWAPs |
| **QAOA** | 10 | 45.2 | **34.6 ± 3.8** ★ | **−10.6 SWAPs** (−23.5%) | 45.0 | 51.8 ± 4.8 | +6.8 SWAPs |
| **QAOA** | 20 | 235.0 | **213.0 ± 14.2** ★ | **−22.0 SWAPs** (−9.4%) | 247.0 | 292.0 ± 0.0 | +45.0 SWAPs |
| **GHZ State** | 50 | 54.0 | **32.8 ± 6.2** ★ | **−21.2 SWAPs** (−39.3%) | **0.0** ★ | 16.6 ± 0.7 | +16.6 SWAPs |

### Architecture: Rigetti Grid 80q Calibration Profile

| Benchmark | Scale ($N$) | SABRE Default | **FAQ + SABRE (Ours)** | SABRE SWAP Delta | PyTKET Default | **FAQ + TKET (Ours)** | PyTKET SWAP Delta |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Grover's Search** | 8 | 768.6 | 794.0 ± 36.2 | +25.4 SWAPs | 639.0 | **605.0 ± 0.0** ★ | **−34.0 SWAPs** (−5.3%) |
| **Grover's Search** | 10 | 3466.6 | 3499.4 ± 118.0 | +32.8 SWAPs | 2669.0 | **2567.0 ± 0.0** ★ | **−102.0 SWAPs** (−3.8%) |
| **Grover's Search** | 12 | 12358.0 | 12472.4 ± 298.0 | +114.4 SWAPs | 8828.0 | **8702.6 ± 4.1** ★ | **−125.4 SWAPs** (−1.4%) |
| **VQE (RealAmplitudes)**| 50 | 44.0 | 50.0 ± 8.4 | +6.0 SWAPs | 13.0 | **0.4 ± 1.1** ★ | **−12.6 SWAPs** (−96.9%) |
| **QFT** | 20 | 143.8 | 170.6 ± 12.8 | +26.8 SWAPs | 148.0 | **143.0 ± 6.8** ★ | **−5.0 SWAPs** (−3.4%) |

---

## 🔬 Limitations & Threats to Validity

1. **Calibration Snapshot Dependence**: Evaluation uses physical hardware graphs with error distributions from calibration profiles. Performance on live QPUs varies with dynamic device calibration drift.
2. **Heuristic Non-Convex Optimization**: The Birkhoff continuous relaxation with Frank–Wolfe descent seeks local stationary points on an indefinite objective; global optimality is not guaranteed.
3. **Downstream Router Sensitivity**: FAQ-Layout supplies initial placements; final gate overhead is dependent on the choice and parameters of the downstream routing pass.

---

## 🚀 Usage Example (Qiskit Integration)

```python
from qiskit import QuantumCircuit
from qiskit.transpiler import PassManager, CouplingMap
from qiskit.transpiler.passes import SabreSwap, FullAncillaAllocation, EnlargeWithAncilla, ApplyLayout
from qap_compiler.qiskit_plugin import FAQPlacementPass

qc = QuantumCircuit(3)
qc.h(0)
qc.cx(0, 1)
qc.cx(1, 2)
cm = CouplingMap([(0, 1), (1, 2), (2, 3), (3, 4)])

pm = PassManager([
    FAQPlacementPass(cm, num_starts=5, seed=42),
    FullAncillaAllocation(cm),
    EnlargeWithAncilla(),
    ApplyLayout(),
    SabreSwap(cm, seed=42)
])

transpiled = pm.run(qc)
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
