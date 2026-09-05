# FAQ-Layout — How It Works & How to Reproduce

A concise walkthrough. The full formulation, tables and limitations live in **`../README.md`**.

## The idea

Pre-placement decides *which physical qubits the logical qubits should start on* before a
router inserts SWAPs. FAQ-Layout solves this as an approximate **QAP**:

$$ \min_{P \in \Pi_M} \text{Tr}(A^\top P B P^\top) $$

1. **Interaction matrix $A$** — count 2-qubit gate contacts between logical qubits, decayed by
   circuit layer (`qap_compiler/module_a_dag.py`).
2. **Hardware matrix $B$** — directed, fidelity-weighted shortest-path distances over the
   device coupling graph from a Qiskit `FakeBrisbane` snapshot (`module_b_hardware.py`).
3. **Solve** — SciPy FAQ from 5 starts (barycenter + Gaussian Sinkhorn perturbations), then a
   discrete **2-opt** polish (`module_c_faq.py`). FAQ returns a discrete permutation; its cost
   is the discrete QAP cost (not a "continuous relaxation cost").
4. **Hand off** — the layout seeds Qiskit SABRE, PyTKET, or MQT-QMAP routing (`pipeline.py`,
   `module_d_handoff.py`, `module_e_fgea.py`, `qiskit_plugin.py`).

## Reproduce everything

```bash
# dependencies (uv; Python 3.12 pinned in .python-version)
uv sync

# unit/integration tests
uv run pytest tests/test_modules.py -v

# QAP-cost ablation table -> writes benchmarks/results/benchmark_ablation_results.json
uv run python benchmarks/benchmark_ablations.py

# canonical K=20 paired-seed benchmark -> writes benchmarks/results/benchmark_eval_results.json + raw seeds
uv run python benchmarks/benchmark_eval.py            # serial (slow)
uv run python benchmarks/benchmark_eval_parallel.py 6 # same results, CPU-parallel

# In sandboxes that block multiprocessing Pools, use the strided driver instead:
#   uv run python benchmarks/benchmark_eval_strided.py 6 0   # ...remainder 0..5, then merge partials

# Paired significance testing (Wilcoxon + BH FDR) on the committed per-seed log (analysis-only)
uv run python benchmarks/analyze_significance.py

# Fidelity-loss proxy on the routed circuits (heavy; deterministic re-route).
# Launch 6 strided slices in parallel, then merge and render the delta table:
uv run python benchmarks/benchmark_fidelity.py 6 0   # ...remainder 0..5
uv run python benchmarks/benchmark_fidelity.py --merge 6
uv run python benchmarks/report_fidelity.py
```

CI (`.github/workflows/ci.yml`) lints/tests on every push and diffs the regenerated ablation +
significance JSON against the checked-in files; the expensive fidelity re-run is a manual
`workflow_dispatch` job.

## Notes

- The committed canonical results (`benchmarks/results/benchmark_eval_results.json` / `_raw_seeds.json`) are fully
  reproducible: a full re-run matched them exactly (mean diff 0; 0/1600 per-seed mismatches).
- The fidelity re-run (`benchmarks/benchmark_fidelity.py`) also matched 0/1600 SWAP values, so
  its fidelity-loss proxies describe the same routed circuits as the canonical tables.
- Paired significance (`benchmarks/analyze_significance.py`) and the fidelity proxy
  (`benchmarks/report_fidelity.py`) are summarised in
  [`reports/statistical_fidelity_analysis.md`](statistical_fidelity_analysis.md).
- Older, inconsistent experiment files are archived under `../historical/`.
- This work is CPU-bound; a GPU provides no speedup (no GPU code paths in Qiskit/PyTKET routing
  or SciPy FAQ).
