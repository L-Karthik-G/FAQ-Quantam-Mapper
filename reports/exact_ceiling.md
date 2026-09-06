# Exact ground-truth ceiling on small circuits (roadmap item 8)

The README/experiment results are all heuristic-vs-heuristic. This module adds an
**exact joint layout+routing optimum** for tiny circuits, so a handful of cells can be
reported as "% of theoretical optimum" instead of router-vs-router deltas.

## Method

For circuits with N logical qubits placed on an N-physical-qubit topology (no spare
ancillas) the joint problem is a shortest-path search over states
`(mapping permutation of the N logicals, position in the two-qubit gate list)`:

* SWAP any pair of logicals whose current physical positions are adjacent in the
  topology — cost 1;
* fire the next two-qubit gate when its two logicals are currently adjacent — cost 0
  (1-qubit gates never need a SWAP and are skipped).

Initial layout is free (every permutation is a start state at cost 0), so the result is
the **exact minimum number of routing SWAPs** for that circuit/topology pair, found by a
0-1 BFS over ≤ N! · (gates+1) states. Cells: line N = 4/5 and 2×3 grid N = 6, with
ripple (chain), qram (binary tree) and random-3-regular circuit families.

Heuristic arms (K = 20 seeds): Qiskit o1 default SABRE, o3 default SABRE (+VF2PostLayout),
hard FAQ+SABRE (random multi-start FAQ layout forced) and FAQ-soft-SABRE (FAQ layout as one
trial in SABRE's pool). FAQ arms use the same synthetic uniform 1–3% error profile on the
tiny topology as the main suite's synthetic grid, so the QAP objective is unchanged.
Files: `benchmarks/results/exact_ceiling.json`; generator `benchmarks/exact_ceiling.py`.

## Results

| Topology | N | Circuit | exact | o1 mean | o3 mean | FAQ hard | FAQ soft |
|:---|:---:|:---|:---:|:---:|:---:|:---:|:---:|
| line | 4 | ripple | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| line | 4 | qram | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| line | 4 | random-3 (K4) | 3 | 3.0 (100%) | 3.0 (100%) | 3.0 (100%) | 3.0 (100%) |
| line | 5 | ripple | **0** | 0.0 | 0.0 | **+0.6 above opt** | 0.0 |
| line | 5 | qram | 1 | 1.0 (100%) | 1.0 (100%) | 1.0 (100%) | 1.0 (100%) |
| grid 2×3 | 6 | ripple | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| grid 2×3 | 6 | qram | 1 | 1.0 (100%) | 1.0 (100%) | 1.0 (100%) | 1.0 (100%) |
| grid 2×3 | 6 | random-3 | **2** | 2.5 (125%) | **2.1 (105%)** | 3.0 (150%) | 2.5 (125%) |

% = mean/exact for exact > 0 rows. Rows with exact = 0 are trivially satisfied by the
identity layout; they are reported absolutely (any positive mean is excess SWAPs above the
theoretical floor, e.g. FAQ hard +0.6 on line-N5 ripple).

## Reading

* On these tiny cells most of the problem is trivially solved: exact optima are 0–3 SWAPs
  and every arm reaches 100% of optimum on 6 of 8 cells.
* The only cell with real headroom — random-3-regular on the 2×3 grid (exact = 2) — shows
  **o3 closest to the floor** (2.1, 105%) with o1/FAQ-soft at 125% and hard FAQ+SABRE at
  150%. Consistent with the item-7 baselines: the strong default router (o3 + VF2PostLayout)
  is the best proxy to the exact ceiling here, and FAQ pre-placement does not help on these
  sizes.
* line-N5 ripple reproduces the soft-candidate finding at the exact level: hard FAQ+SABRE
  routes above the theoretical floor (+0.6 mean SWAPs when 0 are possible), while the
  FAQ-as-trial arm returns exactly to the optimum — forcing the FAQ layout is what hurts.
* **Value of the infrastructure:** future FAQ claims can be reported on these cells as
  "% of the exact optimum" (e.g. by the benchmark harness on these topologies). The cells
  are intentionally tiny (N ≤ 6) because exact joint layout+routing is NP-hard in general;
  larger exact ceilings would need a dedicated branch-and-bound / ILP, which is out of scope.

## Reproduce

```bash
uv run python benchmarks/exact_ceiling.py   # ~10 s -> benchmarks/results/exact_ceiling.json
```
