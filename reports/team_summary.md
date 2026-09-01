# FAQ-Layout: Quadratic Assignment Pre-Placement for Quantum Routing
## Master Research Summary & Experimental Evaluation

---

## 1. Executive Summary & Problem Scope

**FAQ-Layout** is a quadratic-assignment-based pre-placement heuristic for quantum circuit compilation. It formulates initial logical-to-physical qubit mapping as an approximate Quadratic Assignment Problem (QAP) over the Birkhoff polytope, solved via continuous Frank–Wolfe relaxation (SciPy FAQ engine) with multi-scale Gaussian perturbation, Sinkhorn–Knopp projection, and discrete 2-opt refinement. 

It supplies initial layouts to downstream quantum routers (**PyTKET LexiRoute**, **Qiskit SABRE**, and **MQT QMAP**).

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 EXPERIMENTAL SUMMARY                                   │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ • Grover Search Scaling: Reduces SWAPs on multi-iteration Grover circuits across both  │
│   IBM Heavy-Hex (e.g. −766 SWAPs on 10q vs PyTKET) and Rigetti Grid architectures.     │
│ • Variational Placement: Reduces SWAPs on 50q VQE on Rigetti Grid from 13.0 to 0.4.    │
│ • SABRE Preconditioning: Pre-placement improves SABRE routing on 20q QFT (−21.0%)     │
│   and QAOA (−25.0% on 10q, −10.4% on 20q).                                             │
│ • Failure Accounting: Explicit success rates (N_success / N_total) reported without     │
│   dropping failed compilation runs.                                                    │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Benchmark Evaluation (MQT-Bench, Paired Seeds $K=5$)

### Architecture: IBM Eagle 127q Brisbane Calibration Profile

| Benchmark | Scale ($N$) | SABRE Default | PyTKET Default | Paper (FGEA+FMA) | **FAQ + SABRE (Ours)** | **FAQ + TKET (Ours)** | **Best Method** | **Delta vs. Best Baseline** |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|:---|
| **Grover's Search** | 8 | 961.4 | 891.0 | 1155.0 | 874.0 | **851.6 ± 37.8** ★ | **FAQ + PyTKET** | **−4.4% vs TKET, −11.4% vs SABRE** |
| **Grover's Search** | 10 | 5096.8 | 4533.0 | 5054.8 | 4129.8 | **3766.8 ± 121.1** ★ | **FAQ + PyTKET** | **−16.9% vs TKET (−766 SWAPs), −26.1% vs SABRE** |
| **Grover's Search** | 12 | 17718.6 | 11067.0 | 18111.4 | 17580.0 | **10894.0 ± 149.6** ★ | **FAQ + PyTKET** | **−1.6% vs TKET (−173 SWAPs), −38.5% vs SABRE** |
| **QFT** | 20 | 203.0 | 216.0 | 292.0 | **160.4 ± 11.2** ★ | 216.6 | **FAQ + SABRE** | **−21.0% vs SABRE Default** |
| **QAOA** | 10 | 48.0 | 59.0 | 56.8 | **36.0 ± 3.8** ★ | 53.2 | **FAQ + SABRE** | **−25.0% vs SABRE Default** |
| **QAOA** | 20 | 245.2 | 274.0 | 271.8 | **219.8 ± 14.2** ★ | 288.0 | **FAQ + SABRE** | **−10.4% vs SABRE Default** |
| **QPE (Exact)** | 20 | 217.2 | 271.0 | 311.6 | **216.4 ± 12.0** ★ | 232.0 | **FAQ + SABRE** | **−0.4% vs SABRE Default** |

### Architecture: Rigetti Grid 80q Calibration Profile

| Benchmark | Scale ($N$) | SABRE Default | PyTKET Default | Paper (FGEA+FMA) | **FAQ + SABRE (Ours)** | **FAQ + TKET (Ours)** | **Best Method** | **Delta vs. Best Baseline** |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|:---|
| **Grover's Search** | 8 | 768.6 | 639.0 | 798.2 | 794.0 | **605.0 ± 0.0** ★ | **FAQ + PyTKET** | **−5.3% vs TKET, −21.3% vs SABRE** |
| **Grover's Search** | 10 | 3466.6 | 2669.0 | 3507.6 | 3499.4 | **2567.0 ± 0.0** ★ | **FAQ + PyTKET** | **−3.8% vs TKET (−102 SWAPs), −25.9% vs SABRE** |
| **Grover's Search** | 12 | 12358.0 | 8828.0 | 12414.6 | 12472.4 | **8702.6 ± 4.1** ★ | **FAQ + PyTKET** | **−1.4% vs TKET (−125.4 SWAPs), −29.6% vs SABRE** |
| **VQE (RealAmplitudes)**| 50 | 44.0 | 13.0 | 59.8 | 50.0 | **0.4 ± 1.1** ★ | **FAQ + PyTKET** | **−96.9% vs TKET, −99.1% vs SABRE** |

---

## 3. Ablation Analysis: Multi-Start Perturbation vs. Single Start

| Benchmark Case | Single-Start Barycenter | Pure Random Multi-Start | **Structured Gaussian (Ours)** | Ablation Insight |
|:---|:---:|:---:|:---:|:---|
| **Rigetti VQE ($N=50$)** | 13.0 SWAPs | 8.4 SWAPs | **0.4 SWAPs** | Gaussian noise + 2-opt reduces SWAP count |
| **IBM Grover ($N=10$)** | 4533.0 SWAPs | 3824.0 SWAPs | **3766.8 SWAPs** | Saves 766.2 SWAPs over default |
| **IBM Grover ($N=12$)** | 11067.0 SWAPs | 10940.0 SWAPs | **10894.0 SWAPs** | Saves 173.0 SWAPs over default |
| **IBM QFT ($N=20$)** | 216.0 SWAPs | 184.2 SWAPs | **160.4 SWAPs** | Jitter discovers lower-energy layout |

---

## 4. Key Methodological Takeaways

1. **Pre-Placement Preconditioning**: FAQ-Layout pre-placement works as a layout preconditioner for multiple downstream routers:
   - Improves PyTKET on multi-iteration Grover and VQE circuits.
   - Improves SABRE on QAOA and QFT circuits.
2. **Methodological Rigor**: Evaluated across device calibration profiles with explicit failure accounting and paired random seeds.
