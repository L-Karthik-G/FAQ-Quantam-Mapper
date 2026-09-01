# FAQ-Layout: Quadratic Assignment Pre-Placement for Quantum Routing

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests: Passing](https://img.shields.io/badge/pytest-passing-brightgreen.svg)]()

**FAQ-Layout** is an initial placement heuristic for quantum circuit compilation. It formulates logical-to-physical qubit assignment as an approximate Quadratic Assignment Problem (QAP) over the Birkhoff polytope, solved via continuous Frank–Wolfe relaxation (SciPy FAQ engine) combined with multi-scale Gaussian perturbation, Sinkhorn–Knopp projection, and discrete 2-opt refinement.

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
1. **Barycenter Prior**: Starts from the Birkhoff barycenter $J_0 = \frac{1}{M}\mathbf{1}\mathbf{1}^T$.
2. **Multi-Scale Perturbations**: 5 Gaussian starts ($\sigma = \alpha / M$) around $J_0$.
3. **Sinkhorn–Knopp Projection**: Normalizes candidate matrices onto $\mathcal{D}_M$.
4. **Discrete 2-Opt Polish**: Post-Hungarian discrete local search refinement.

---

## 📊 Benchmark Evaluation Summary (MQT-Bench, Paired Seeds $K=5$)

*All reported statistics include explicit compilation success rates ($N_{\text{success}} / N_{\text{total}}$).*

### Architecture: IBM Eagle 127q Brisbane Calibration Profile

| Benchmark | Scale ($N$) | SABRE Default (Success %) | PyTKET Default (Success %) | Paper (FGEA+FMA) | **FAQ + SABRE (Ours)** | **FAQ + TKET (Ours)** | **Best Method** | **Delta vs. Best Baseline** |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|:---|
| **Grover's Search** | 8 | 961.4 (100%) | 891.0 (100%) | 1155.0 (100%) | 874.0 (100%) | **851.6 ± 37.8** (100%) | **FAQ + PyTKET** | **−4.4% vs TKET, −11.4% vs SABRE** |
| **Grover's Search** | 10 | 5096.8 (100%) | 4533.0 (100%) | 5054.8 (100%) | 4129.8 (100%) | **3766.8 ± 121.1** (100%) | **FAQ + PyTKET** | **−16.9% vs TKET (−766 SWAPs), −26.1% vs SABRE** |
| **Grover's Search** | 12 | 17718.6 (100%) | 11067.0 (100%) | 18111.4 (100%) | 17580.0 (100%) | **10894.0 ± 149.6** (100%) | **FAQ + PyTKET** | **−1.6% vs TKET (−173 SWAPs), −38.5% vs SABRE** |
| **QFT** | 20 | 203.0 (100%) | 216.0 (100%) | 292.0 (100%) | **160.4 ± 11.2** (100%) | 216.6 (100%) | **FAQ + SABRE** | **−21.0% vs SABRE Default** |
| **QAOA** | 10 | 48.0 (100%) | 59.0 (100%) | 56.8 (100%) | **36.0 ± 3.8** (100%) | 53.2 (100%) | **FAQ + SABRE** | **−25.0% vs SABRE Default** |
| **QAOA** | 20 | 245.2 (100%) | 274.0 (100%) | 271.8 (100%) | **219.8 ± 14.2** (100%) | 288.0 (100%) | **FAQ + SABRE** | **−10.4% vs SABRE Default** |

### Architecture: Rigetti Grid 80q Calibration Profile

| Benchmark | Scale ($N$) | SABRE Default (Success %) | PyTKET Default (Success %) | Paper (FGEA+FMA) | **FAQ + SABRE (Ours)** | **FAQ + TKET (Ours)** | **Best Method** | **Delta vs. Best Baseline** |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|:---|
| **Grover's Search** | 8 | 768.6 (100%) | 639.0 (100%) | 798.2 (100%) | 794.0 (100%) | **605.0 ± 0.0** (100%) | **FAQ + PyTKET** | **−5.3% vs TKET, −21.3% vs SABRE** |
| **Grover's Search** | 10 | 3466.6 (100%) | 2669.0 (100%) | 3507.6 (100%) | 3499.4 (100%) | **2567.0 ± 0.0** (100%) | **FAQ + PyTKET** | **−3.8% vs TKET (−102 SWAPs), −25.9% vs SABRE** |
| **Grover's Search** | 12 | 12358.0 (100%) | 8828.0 (100%) | 12414.6 (100%) | 12472.4 (100%) | **8702.6 ± 4.1** (100%) | **FAQ + PyTKET** | **−1.4% vs TKET (−125.4 SWAPs), −29.6% vs SABRE** |
| **VQE (RealAmplitudes)**| 50 | 44.0 (100%) | 13.0 (100%) | 59.8 (100%) | 50.0 (100%) | **0.4 ± 1.1** (100%) | **FAQ + PyTKET** | **−96.9% vs TKET, −99.1% vs SABRE** |

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
