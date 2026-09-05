# Implementation Plan: Rigorous FAQ-Layout Quantum Placement Engine

This plan implements all architectural, mathematical, benchmarking, and reporting upgrades recommended in the research review to transition FAQ from a prototype to a defensible, top-tier publication-ready research engine.

## User Review Required

> [!IMPORTANT]
> - **Mathematical Reframing**: The theory will be updated to explicitly specify *continuous relaxation onto the convex Birkhoff polytope with non-convex Frank–Wolfe descent* rather than "convex relaxation".
> - **Fair Baseline Protocol**: Performance is evaluated against $\min(\text{all baselines})$ on fixed hardware profiles across paired transpiler seeds ($s \in \{0, 1, 2, 3, 4\}$).
> - **Compilation Success Rate**: Explicitly tracked and reported without silent `-1` masking.

---

## Proposed Changes

### Component 1: Core Solver & Algorithmic Enhancements

#### [MODIFY] [`qap_compiler/module_c_faq.py`](qap_compiler/module_c_faq.py)
- **5-Start Gaussian Perturbation**:
  - Start 1: Exact Analytical Barycenter ($J_0 = \frac{1}{M}\mathbf{1}\mathbf{1}^T$).
  - Starts 2–3: Adaptive Gaussian noise ($\sigma = 0.05 / M$) + Sinkhorn-Knopp projection.
  - Starts 4–5: Medium Gaussian noise ($\sigma = 0.15 / M$) + Sinkhorn-Knopp projection.
- **Momentum-Guided Frank–Wolfe**:
  - Maintain velocity gradient vector $v_t = \beta v_{t-1} + (1-\beta)\nabla f(P_t)$ with $\beta = 0.9$ to eliminate boundary zig-zagging and blast past shallow saddle points.
- **Discrete 2-Opt Local Search Polish**:
  - Add fast $O(N^2)$ pairwise swap refinement on the Hungarian output to guarantee discrete local minimality.
- **Parallel Multi-Start Execution**:
  - Execute starts concurrently via `ThreadPoolExecutor`.
- **Return Multi-Start Metrics**:
  - Return best permutation layout along with best-of-k and mean-of-k energies.

#### [MODIFY] [`qap_compiler/module_e_fgea.py`](qap_compiler/module_e_fgea.py)
- Fix edge handling logic to ensure directed edges $(u, v)$ where $u > v$ are preserved.
- Align seed node selection to use `sum()` of neighbor fidelities instead of `np.mean()`.

---

### Component 2: Hardware Architecture & Noise Modeling

#### [MODIFY] [`qap_compiler/module_b_hardware.py`](qap_compiler/module_b_hardware.py)
- Update graph representation to `nx.DiGraph()` to preserve directional CNOT error rates ($q_1 \to q_2 \neq q_2 \to q_1$).
- Add real IBM Eagle 127-qubit (`ibm_brisbane` / `ibm_kyoto`) calibration snapshot loaders.
- Compute directed Dijkstra shortest-path distance matrix $B$ weighted by edge log-infidelities.

---

### Component 3: Packaging & Native Qiskit Plugin

#### [NEW] [`qap_compiler/qiskit_plugin.py`](qap_compiler/qiskit_plugin.py)
- Native Qiskit `TransformationPass` (`FAQPlacementPass`) that plugs directly into Qiskit's `PassManager`.

#### [NEW] [`pyproject.toml`](pyproject.toml)
- Standard packaging metadata with pinned dependencies (managed via `uv`; `uv.lock` pins the
  resolved environment).

---

### Component 4: Testing & Verification

#### [MODIFY] [`tests/test_modules.py`](tests/test_modules.py)
- Add small-scale ($N \le 5$) semantic equivalence tests verifying `Operator(qc_in).equiv(Operator(qc_out))`.
- Test directed hardware distance matrices.
- Test 5-start Gaussian solver with momentum and 2-opt polishing.
- Test native Qiskit pass manager plugin.

---

### Component 5: Rigorous Benchmarking & Ablation Suite

#### [NEW] [`benchmark_rigorous.py`](benchmark_rigorous.py)
- Strict paired-seed protocol ($s \in \{0, 1, 2, 3, 4\}$) on fixed hardware profiles.
- Evaluate SABRE Default, PyTKET Default, MQT QMAP Default, Paper Baseline (FGEA+FMA), and FAQ+PyTKET / FAQ+QMAP / FAQ+SABRE.
- Dedicated Ablation Study:
  - (a) Single-start Barycenter FAQ
  - (b) Pure Random Multi-Start FAQ
  - (c) 5-Start Gaussian + Momentum FAQ
- Output clean JSON results (`benchmark_rigorous_results.json`).

---

### Component 6: Master Reports & Documentation

#### [MODIFY] [`reports/team_summary.md`](reports/team_summary.md) & [`reports/walkthrough.md`](reports/walkthrough.md) & [`README.md`](README.md)
- Update title and framing: *"FAQ-Layout: A Quadratic Assignment Pre-placement Engine for Quantum Routers"*.
- Replace "convex relaxation" with rigorous non-convex Frank–Wolfe theory on the Birkhoff polytope.
- Include the new rigorous benchmark results with paired confidence intervals, success rates, and ablation tables.
- Update ECF naming to *"Analytical Two-Qubit Error Survival Proxy (ECF)"*.

---

## Verification Plan

### Automated Tests
- Run full pytest test suite:
  ```bash
  PYTHONPATH=. pytest tests/test_modules.py -v
  ```

### Benchmark Run
- Execute `benchmark_rigorous.py` to collect fresh paired-seed datasets and ablation metrics.
- Validate that all compilation runs record 100% success rate and verified semantic unitary equivalence.
