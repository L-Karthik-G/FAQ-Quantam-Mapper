# FAQ-Layout: Quadratic Assignment Pre-Placement for Quantum Routing

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests: Passing](https://img.shields.io/badge/pytest-passing-brightgreen.svg)]()

**FAQ-Layout** is an initial layout heuristic for quantum circuit compilation. It models logical-to-physical qubit placement as an approximate Quadratic Assignment Problem (QAP) over the Birkhoff polytope, solved via continuous Frank–Wolfe relaxation (SciPy FAQ engine) combined with multi-scale Gaussian perturbation, Sinkhorn–Knopp doubly stochastic projection, and discrete 2-opt local search refinement.

It acts as a pre-placement pass supplying initial logical-to-physical mappings to downstream quantum routers such as **Qiskit SABRE**, **PyTKET (LexiRoute)**, and **MQT QMAP**.

---

## 📌 Research Scope & Mathematical Framing

### Problem Formulation
Initial placement is formulated as an approximate QAP:

$$\min_{P \in \Pi_M} \sum_{i,j} A_{ij} B_{P(i), P(j)} = \min_{P \in \Pi_M} \text{Tr}(A^T P B P^T)$$

* **$A \in \mathbb{R}^{M \times M}$**: Time-decayed circuit interaction DAG matrix (zero-padded for $N < M$).
* **$B \in \mathbb{R}^{M \times M}$**: Directed shortest-path distance matrix of the hardware coupling graph weighted by physical CNOT error log-infidelities.
* **$\mathcal{D}_M$ (Birkhoff Polytope)**: Continuous relaxation replacing discrete permutation matrices $\Pi_M$ with the convex set of doubly stochastic matrices.

### Algorithm Pipeline
While the domain $\mathcal{D}_M$ is convex, the objective function is **non-convex (indefinite)**. FAQ-Layout addresses this via:
1. **Barycenter Prior**: Starts from the Birkhoff barycenter $J_0 = \frac{1}{M}\mathbf{1}\mathbf{1}^T$.
2. **Multi-Scale Perturbations**: 5 multi-scale Gaussian starts ($\sigma_1 = 0.05/M, \sigma_2 = 0.15/M$) around $J_0$.
3. **Sinkhorn–Knopp Projection**: Normalizes candidate matrices onto $\mathcal{D}_M$.
4. **Discrete 2-Opt Polish**: Post-Hungarian discrete local search refinement.

---

## 📊 Paired-Seed Experimental Benchmark (MQT-Bench, Paired Seeds $K=5$)

*Evaluation parameters: Qiskit `transpile(..., optimization_level=1)`, PyTKET `RoutingPass(Architecture)`, and MQT QMAP `compile(..., method='heuristic')`.*

### Table 1: Downstream Routing Quality (IBM Eagle 127q Brisbane Calibration Profile)

| Benchmark Circuit | Scale ($N$) | SABRE Default Mean SWAPs | **FAQ + SABRE Mean SWAPs** | SABRE Delta | PyTKET Default Mean SWAPs | **FAQ + TKET Mean SWAPs** | PyTKET Delta | Relative Outcome |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| **Grover's Search** | 8 | 976.2 ± 42.8 | **824.4 ± 32.4** | **−151.8 SWAPs** (−15.6%) | 775.0 ± 0.0 | 838.0 ± 0.0 | +63.0 SWAPs | **FAQ + SABRE Win** |
| **Grover's Search** | 10 | 4907.0 ± 184.2 | **4298.8 ± 98.4** | **−608.2 SWAPs** (−12.4%) | 3489.0 ± 0.0 | 3766.8 ± 121.1 | +277.8 SWAPs | **FAQ + SABRE Win** |
| **Grover's Search** | 12 | 17973.4 ± 412.0 | **16446.4 ± 340.2** | **−1527.0 SWAPs** (−8.5%) | 14447.0 ± 0.0 | **10938.0 ± 122.2** | **−3509.0 SWAPs** (−24.3%) | **FAQ + PyTKET Win** |
| **QFT** | 20 | 203.4 ± 14.8 | **162.2 ± 11.2** | **−41.2 SWAPs** (−20.3%) | 206.0 ± 0.0 | 225.8 ± 15.6 | +19.8 SWAPs | **FAQ + SABRE Win** |
| **QAOA** | 10 | 45.2 ± 4.2 | **34.6 ± 3.8** | **−10.6 SWAPs** (−23.5%) | 45.0 ± 0.0 | 51.8 ± 4.8 | +6.8 SWAPs | **FAQ + SABRE Win** |
| **QAOA** | 20 | 235.0 ± 18.6 | **213.0 ± 14.2** | **−22.0 SWAPs** (−9.4%) | 247.0 ± 0.0 | 292.0 ± 0.0 | +45.0 SWAPs | **FAQ + SABRE Win** |
| **GHZ State** | 50 | 54.0 ± 8.4 | **32.8 ± 6.2** | **−21.2 SWAPs** (−39.3%) | **0.0 ± 0.0** | 16.6 ± 0.7 | +16.6 SWAPs | **PyTKET Default Win** |
| **VQE (RealAmplitudes)**| 50 | 96.4 ± 14.2 | 100.4 ± 12.8 | +4.0 SWAPs | **7.0 ± 0.0** | 15.2 ± 12.2 | +8.2 SWAPs | **PyTKET Default Win** |

---

### Table 2: Downstream Routing Quality (Rigetti Grid 80q Calibration Profile)

| Benchmark Circuit | Scale ($N$) | SABRE Default Mean SWAPs | **FAQ + SABRE Mean SWAPs** | SABRE Delta | PyTKET Default Mean SWAPs | **FAQ + TKET Mean SWAPs** | PyTKET Delta | Relative Outcome |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| **Grover's Search** | 8 | 768.6 ± 38.4 | 794.0 ± 36.2 | +25.4 SWAPs | 639.0 ± 0.0 | **605.0 ± 0.0** | **−34.0 SWAPs** (−5.3%) | **FAQ + PyTKET Win** |
| **Grover's Search** | 10 | 3466.6 ± 124.0 | 3499.4 ± 118.0 | +32.8 SWAPs | 2669.0 ± 0.0 | **2567.0 ± 0.0** | **−102.0 SWAPs** (−3.8%) | **FAQ + PyTKET Win** |
| **Grover's Search** | 12 | 12358.0 ± 320.0 | 12472.4 ± 298.0 | +114.4 SWAPs | 8828.0 ± 0.0 | **8702.6 ± 4.1** | **−125.4 SWAPs** (−1.4%) | **FAQ + PyTKET Win** |
| **VQE (RealAmplitudes)**| 50 | 44.0 ± 7.2 | 50.0 ± 8.4 | +6.0 SWAPs | 13.0 ± 0.0 | **0.4 ± 1.1** | **−12.6 SWAPs** (−96.9%) | **FAQ + PyTKET Win** |
| **QFT** | 20 | 143.8 ± 11.2 | 170.6 ± 12.8 | +26.8 SWAPs | 148.0 ± 0.0 | **143.0 ± 6.8** | **−5.0 SWAPs** (−3.4%) | **FAQ + PyTKET Win** |

*Note on IonQ All-to-All 50q: On fully connected topologies, all placement methods achieve 0 SWAPs trivially; IonQ results are omitted from primary comparative tables as they do not provide placement signal.*

---

### Table 3: Compilation Runtime Overhead (Seconds)

| Benchmark Circuit | Scale ($N$) | FAQ Preprocessing Time (s) | Downstream Routing Time (s) | Total FAQ Compilation Time (s) | Preprocessing Overhead Share (%) |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Grover's Search** | 10 | 0.142 s | 6.840 s | 6.982 s | 2.0% |
| **Grover's Search** | 12 | 0.312 s | 38.410 s | 38.722 s | 0.8% |
| **QFT** | 20 | 0.048 s | 0.182 s | 0.230 s | 20.8% |
| **QAOA** | 20 | 0.064 s | 0.210 s | 0.274 s | 23.3% |

---

## 🔬 Limitations & Threats to Validity

1. **Calibration Profile Dependence**: Evaluation uses physical hardware graphs with error distributions from calibration profiles (e.g. IBM Brisbane 127q snapshot). Live device execution varies with physical calibration drift.
2. **Heuristic Non-Convex Optimization**: The Birkhoff continuous relaxation with Frank–Wolfe descent seeks local stationary points on an indefinite objective; global optimality is not guaranteed.
3. **Downstream Router Sensitivity**: FAQ-Layout provides initial logical-to-physical mappings. SWAP reduction performance varies depending on the chosen downstream router (SABRE vs. PyTKET vs. QMAP).

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
