# Implementation Plan: FGEA Integration & 10-Method Benchmark Suite

## Goal
Implement **FGEA (Fidelity-aware Graph Extraction Algorithm)** and **FMA (Frequency-based Mapping Algorithm)** from the IEEE QCE 2023 paper, integrate them with our existing FAQ pipeline, and run a unified 10-method benchmark across all 36 test configurations.

---

## The 10 Methods to Benchmark

| # | Method | Description |
|:---:|:---|:---|
| 1 | **SABRE Default** | Qiskit SABRE layout + routing (no pre-processing) |
| 2 | **QMAP Default** | MQT QMAP A* exact solver (no pre-processing) |
| 3 | **PyTKET Default** | PyTKET GraphPlacement + LexiRoute |
| 4 | **FAQ + SABRE** | Our FAQ pre-processing → Qiskit SABRE routing |
| 5 | **FAQ + PyTKET** | Our FAQ pre-processing → PyTKET LexiRoute |
| 6 | **FAQ + QMAP** | Our FAQ pre-processing → MQT QMAP |
| 7 | **FAQ + FGEA + SABRE** | FGEA chip slicing → FAQ pre-processing → Qiskit SABRE |
| 8 | **FAQ + FGEA + PyTKET** | FGEA chip slicing → FAQ pre-processing → PyTKET LexiRoute |
| 9 | **FAQ + FGEA + QMAP** | FGEA chip slicing → FAQ pre-processing → MQT QMAP |
| 10 | **Paper Method (FGEA + FMA + SABRE)** | Faithful reimplementation of IEEE QCE 2023 approach |

---

## Proposed Changes

### [NEW] `qap_compiler/module_e_fgea.py`

**`FGEASubgraphExtractor`**:
- Scores every physical edge: `Score(u,v) = 1 - E_uv` (fidelity proxy)
- Seeds BFS from the highest-quality connected node
- Grows a connected subgraph of size `K = N + buffer` (default buffer=4)
- Returns: `(sub_coupling_map, sub_error_rates, physical_node_index_map)`

**`FMAMapper`**:
- Reimplementation of the paper's Frequency-based Mapping Algorithm
- Counts 2-qubit interaction frequency per logical qubit pair from circuit DAG
- Sorts pairs by frequency (descending), assigns greedily to physical qubit slots within the FGEA sub-graph
- Returns: `initial_layout_dict {logical: physical}`

---

### [MODIFY] `qap_compiler/pipeline.py`

Add 4 new compilation methods:
- `compile_fgea_faq_sabre()` — FGEA subgraph → FAQ on sub-matrix → SABRE on full chip
- `compile_fgea_faq_tket()` — FGEA subgraph → FAQ on sub-matrix → PyTKET on full chip
- `compile_fgea_faq_qmap()` — FGEA subgraph → FAQ on sub-matrix → QMAP on full chip
- `compile_paper_method()` — FGEA + FMA greedy placer + SABRE (proxy for paper's HRA)

> [!NOTE]
> FGEA operates only during the layout phase. The downstream router still runs on the full physical chip with the high-fidelity seeded layout.

---

### [MODIFY] `benchmark_suite.py`

- Extend to call all 10 methods per test configuration
- K=5 seeds, 95% CI — identical statistical methodology to existing runs
- Output: `benchmark_fgea_results.json` and `benchmark_fgea_summary.md`

---

## Estimated Run Time
- 10 methods × 5 seeds × 36 configurations = **1,800 individual compilations**
- Estimated wall-clock time: **30–50 minutes**
