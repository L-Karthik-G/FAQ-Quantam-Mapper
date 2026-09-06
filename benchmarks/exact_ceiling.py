"""Exact joint layout+routing ground-truth ceiling on small circuits (roadmap item 8).

The README results are all heuristic-vs-heuristic. This module computes the
*theoretical optimum* SWAP count for tiny circuits by exhaustive search over the
joint layout+routing problem:

  state = (current mapping of the N logical qubits onto the N physical qubits,
           position in the two-qubit gate list)
  moves: SWAP the physical positions of any topologically-adjacent pair of logicals
         (cost 1), or fire the next two-qubit gate if its two logicals are currently
         adjacent on the topology (cost 0). 1-qubit gates never require a SWAP and
         are skipped.

With N == M (no spare ancillas) the mapping is a permutation of N elements, so the
search space is N! x (gates+1) states and a 0-1 BFS finds the exact minimum number
of routing SWAPs. The initial layout is free (every permutation starts at cost 0),
so this is the true *joint* layout+routing optimum for the circuit/topology pair.

Heuristic arms on the same cells (K=20 seeds where a seed exists):
  sabre_def  - Qiskit o1 default SABRE
  sabre_o3   - Qiskit o3 default (runs VF2PostLayout)
  faq_sabre  - FAQ layout hard-constrained (random multi-start FAQ)
  faq_soft   - FAQ layout as one extra trial in SABRE's pool
FAQ arms use a synthetic uniform 1-3% error profile on the tiny topology (same
construction as the synthetic grid in the main suite), so the same QAP objective
applies. Output: per-cell exact optimum + arm means, from which mean-vs-optimum
ratios ("% of theoretical optimum") can be reported.

Usage: uv run python benchmarks/exact_ceiling.py
"""
from __future__ import annotations

import itertools
import json
import os
import sys
import time
from collections import deque
from typing import Dict, List, Tuple

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
if _BENCH_DIR not in sys.path:
    sys.path.insert(0, _BENCH_DIR)

import networkx as nx
import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit.transpiler import CouplingMap
from qiskit.transpiler.basepasses import AnalysisPass
from qiskit.transpiler.layout import Layout
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

from qap_compiler.module_a_dag import DAGInteractionMatrixBuilder
from qap_compiler.module_b_hardware import HardwareMatrixBuilder
from qap_compiler.module_c_faq import AdaptiveFAQSolver

SEEDS = list(range(20))
CELLS = [
    ("line", 4, "ripple"), ("line", 4, "qram"), ("line", 4, "random3"),
    ("line", 5, "ripple"), ("line", 5, "qram"),
    ("grid2x3", 6, "ripple"), ("grid2x3", 6, "qram"), ("grid2x3", 6, "random3"),
]


# --- tiny circuits and topologies ------------------------------------------
def make_circuit(kind: str, n: int) -> QuantumCircuit:
    qc = QuantumCircuit(n)
    if kind == "ripple":
        for i in range(n - 1):
            qc.h(i)
            qc.cx(i, i + 1)
            qc.rz(0.1, i + 1)
            qc.cx(i, i + 1)
    elif kind == "qram":
        for i in range(n // 2):
            left, right = 2 * i + 1, 2 * i + 2
            if left < n:
                qc.cx(i, left)
            if right < n:
                qc.cx(i, right)
    elif kind == "random3":
        g = nx.random_regular_graph(3, n, seed=12345)
        for u, v in g.edges():
            qc.cx(u, v)
            qc.rz(0.2, v)
            qc.cx(u, v)
    else:
        raise ValueError(kind)
    return transpile(qc, basis_gates=["cx", "h", "rz", "x", "sx"], optimization_level=0)


def topology(n: int, name: str) -> Tuple[List[Tuple[int, int]], Dict]:
    """Returns (undirected topology edges, synthetic uniform error dict)."""
    if name == "line":
        edges = [(i, i + 1) for i in range(n - 1)]
    elif name == "grid2x3":
        g = nx.convert_node_labels_to_integers(nx.grid_2d_graph(2, 3))
        edges = list(g.edges())
    else:
        raise ValueError(name)
    undirected = [tuple(sorted(e)) for e in edges]
    rng = np.random.default_rng(12345)
    errs = {}
    for u, v in undirected:
        errs[(u, v)] = errs[(v, u)] = float(rng.uniform(0.01, 0.03))
    return undirected, errs


# --- exact solver -----------------------------------------------------------
def exact_min_swaps(qc: QuantumCircuit, undirected_edges: List[Tuple[int, int]]) -> int:
    """Exact min routing SWAPs via 0-1 BFS over (mapping, gate position) states."""
    n = qc.num_qubits
    perms = list(itertools.permutations(range(n)))
    perm_index = {p: i for i, p in enumerate(perms)}

    # swap-neighbours per mapping: swapping any two topologically adjacent logicals
    adj = []
    for p in perms:
        pos = {q: i for i, q in enumerate(p)}
        nbrs = set()
        for u, v in undirected_edges:
            lst = list(p)
            pu, pv = pos[u], pos[v]
            lst[pu], lst[pv] = lst[pv], lst[pu]
            nbrs.add(perm_index[tuple(lst)])
        adj.append(sorted(nbrs))

    qmap = {q: i for i, q in enumerate(qc.qubits)}
    twoq = [inst for inst in qc.data if len(inst.qubits) == 2]
    pairs = [(qmap[inst.qubits[0]], qmap[inst.qubits[1]]) for inst in twoq]
    if not pairs:
        return 0
    edgeset = {tuple(sorted(e)) for e in undirected_edges}
    n_gates = len(pairs)
    width = n_gates + 1

    # 0-1 BFS. dist flattened [perm * width + gate_pos]; -1 = unvisited.
    dist = np.full(len(perms) * width, -1, dtype=int)
    dq = deque()
    for i in range(len(perms)):  # free initial layout
        dist[i * width] = 0
        dq.append((i, 0))
    while dq:
        pi, g = dq.popleft()
        d = dist[pi * width + g]
        if g == n_gates:
            return int(d)
        p = perms[pi]
        a, b = pairs[g]
        # fire the gate for free if its logicals are adjacent in the topology
        if tuple(sorted((p[a], p[b]))) in edgeset:
            ni = pi * width + (g + 1)
            if dist[ni] == -1:
                dist[ni] = d
                dq.appendleft((pi, g + 1))
        for nj in adj[pi]:
            ni = nj * width + g
            if dist[ni] == -1:
                dist[ni] = d + 1
                dq.append((nj, g))
    raise RuntimeError("unreachable: exact search did not terminate")


# --- heuristic arms ---------------------------------------------------------
class _SetSabreStartingLayouts(AnalysisPass):
    def __init__(self, layouts):
        super().__init__()
        self.layouts = layouts

    def run(self, dag):
        self.property_set["sabre_starting_layouts"] = list(self.layouts)
        return dag


def faq_mapping(qc: QuantumCircuit, undirected_edges: List[Tuple[int, int]],
                errs: Dict, seed: int):
    n = qc.num_qubits
    dag = DAGInteractionMatrixBuilder(gamma=0.9)
    hw = HardwareMatrixBuilder(alpha=1.0)
    faq = AdaptiveFAQSolver(num_starts=5, start_mode="random", enable_2opt=True, seed=seed)
    A = dag.build_matrix(qc)
    directed = [(u, v) for u, v in undirected_edges] + [(v, u) for u, v in undirected_edges]
    B = hw.build_matrix(n, directed, errs, is_directed=True)
    mapping, _cost = faq.solve(A, B)
    return mapping


def arm_swaps(kind: str, n: int, topo: str, seed: int, arm: str) -> int:
    qc = make_circuit(kind, n)
    undirected, errs = topology(n, topo)
    directed = [(u, v) for u, v in undirected] + [(v, u) for u, v in undirected]
    cm = CouplingMap(directed)
    if arm == "sabre_def":
        res = transpile(qc, coupling_map=cm, seed_transpiler=seed, optimization_level=1)
    elif arm == "sabre_o3":
        res = transpile(qc, coupling_map=cm, seed_transpiler=seed, optimization_level=3)
    elif arm in ("faq_sabre", "faq_soft"):
        mapping = faq_mapping(qc, undirected, errs, seed)
        if arm == "faq_sabre":
            res = transpile(
                qc, coupling_map=cm,
                initial_layout=[mapping.get(i, i) for i in range(n)],
                layout_method=None, routing_method="sabre",
                seed_transpiler=seed, optimization_level=1,
            )
        else:
            layout = Layout({qc.qubits[i]: int(mapping[i]) for i in range(n)})
            pm = generate_preset_pass_manager(optimization_level=1, coupling_map=cm,
                                              layout_method="sabre",
                                              routing_method="sabre",
                                              seed_transpiler=seed)
            pm.layout._tasks.insert(0, [_SetSabreStartingLayouts([layout])])
            res = pm.run(qc)
    else:
        raise ValueError(arm)
    return res.count_ops().get("swap", 0)


def main() -> None:
    t_start = time.time()
    rows = []
    for topo, n, kind in CELLS:
        qc = make_circuit(kind, n)
        undirected, _errs = topology(n, topo)
        exact = exact_min_swaps(qc, undirected)
        means = {}
        for arm in ("sabre_def", "sabre_o3", "faq_sabre", "faq_soft"):
            vals = [arm_swaps(kind, n, topo, s, arm) for s in SEEDS]
            means[arm] = float(np.mean(vals))
        row = {"topology": topo, "qubits": n, "kind": kind,
               "cx_gates": sum(1 for i in qc.data if len(i.qubits) == 2),
               "exact_min_swaps": exact,
               "mean_sabre_def": means["sabre_def"], "mean_sabre_o3": means["sabre_o3"],
               "mean_faq_sabre": means["faq_sabre"], "mean_faq_soft": means["faq_soft"]}
        rows.append(row)
        print(f"{topo:8s} N={n} {kind:8s} exact={exact:3d} | o1={means['sabre_def']:5.1f} "
              f"o3={means['sabre_o3']:5.1f} faqHard={means['faq_sabre']:5.1f} "
              f"faqSoft={means['faq_soft']:5.1f}  ({time.time() - t_start:.0f}s)")
    out = os.path.join(_BENCH_DIR, "results", "exact_ceiling.json")
    with open(out, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
