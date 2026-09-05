"""
Module E: FGEA (Fidelity-aware Graph Extraction Algorithm) & FMA (Frequency-based Mapping Algorithm)
Inspired by: "Towards Fidelity-Optimal Qubit Mapping on NISQ Computers" (IEEE QCE 2023, DOI: 10.1109/QCE57702.2023.10313857)

FGEA: Extracts the highest-fidelity connected subgraph of size K = N + buffer from the physical chip.
FMA:  Greedily maps logical qubits to physical qubit slots based on 2-qubit interaction frequency.
"""

import heapq
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx
from qiskit import QuantumCircuit
from qiskit.converters import circuit_to_dag


class FGEASubgraphExtractor:
    """
    Fidelity-aware Graph Extraction Algorithm.
    Identifies the best-quality connected subgraph of K physical qubits
    from the full hardware coupling map, guided by directed edge fidelity scores.
    """

    def __init__(self, buffer: int = 4):
        """
        Args:
            buffer: Extra physical qubits beyond N to include in the subgraph.
                    K = N + buffer.
        """
        self.buffer = buffer

    def extract(
        self,
        N: int,
        num_physical_qubits: int,
        coupling_map: List[Tuple[int, int]],
        error_rates: Optional[Dict[Tuple[int, int], float]] = None,
    ) -> Tuple[List[Tuple[int, int]], Dict[Tuple[int, int], float], Dict[int, int], Dict[int, int]]:
        """
        Extracts the best-fidelity connected subgraph of size K = N + buffer using directed graph structure.

        Returns:
            sub_coupling_map: List of (u, v) edges using re-indexed [0, K) labels
            sub_error_rates:  Dict keyed by re-indexed (u, v) pairs
            global_to_local:  Dict mapping original physical qubit idx -> local subgraph idx
            local_to_global:  Dict mapping local subgraph idx -> original physical qubit idx
        """
        K = min(N + self.buffer, num_physical_qubits)

        # Build directed graph preserving CNOT edge directionality and asymmetric infidelities
        G = nx.DiGraph()
        G.add_nodes_from(range(num_physical_qubits))

        error_dict = error_rates if error_rates is not None else {}
        for u, v in coupling_map:
            err = error_dict.get((u, v), 0.01)
            fidelity = max(1.0 - err, 1e-6)
            G.add_edge(u, v, fidelity=fidelity, weight=-fidelity)

        # Node score: Sum of outgoing and incoming edge fidelities
        node_scores = {}
        for node in G.nodes():
            in_f = sum(data["fidelity"] for _, _, data in G.in_edges(node, data=True))
            out_f = sum(data["fidelity"] for _, _, data in G.out_edges(node, data=True))
            node_scores[node] = in_f + out_f

        seed_node = max(node_scores, key=node_scores.get)

        selected: Set[int] = {seed_node}
        frontier = []

        neighbors = set(G.successors(seed_node)).union(set(G.predecessors(seed_node)))
        for nb in neighbors:
            f1 = G[seed_node][nb]["fidelity"] if G.has_edge(seed_node, nb) else 0.0
            f2 = G[nb][seed_node]["fidelity"] if G.has_edge(nb, seed_node) else 0.0
            best_f = max(f1, f2)
            heapq.heappush(frontier, (-best_f, nb))

        while len(selected) < K and frontier:
            neg_fid, node = heapq.heappop(frontier)
            if node in selected:
                continue
            selected.add(node)
            nbrs = set(G.successors(node)).union(set(G.predecessors(node)))
            for nb in nbrs:
                if nb not in selected:
                    f1 = G[node][nb]["fidelity"] if G.has_edge(node, nb) else 0.0
                    f2 = G[nb][node]["fidelity"] if G.has_edge(nb, node) else 0.0
                    best_f = max(f1, f2)
                    heapq.heappush(frontier, (-best_f, nb))

        # Re-index selected physical qubits to [0, K)
        sorted_selected = sorted(list(selected))
        global_to_local = {g: loc for loc, g in enumerate(sorted_selected)}
        local_to_global = {loc: g for loc, g in enumerate(sorted_selected)}

        sub_coupling_map: List[Tuple[int, int]] = []
        sub_error_rates: Dict[Tuple[int, int], float] = {}

        for u, v in coupling_map:
            if u in selected and v in selected:
                u_loc, v_loc = global_to_local[u], global_to_local[v]
                sub_coupling_map.append((u_loc, v_loc))
                if (u, v) in error_dict:
                    sub_error_rates[(u_loc, v_loc)] = error_dict[(u, v)]

        return sub_coupling_map, sub_error_rates, global_to_local, local_to_global


class FMALogicalPlacer:
    """
    Frequency-based Mapping Algorithm.
    Greedily maps logical qubits to physical subgraph nodes based on 2-qubit gate interaction frequencies.
    Raises explicit RuntimeError if physical slots are exhausted (no silent fallback).
    """

    def place(
        self,
        circuit: QuantumCircuit,
        sub_coupling_map: List[Tuple[int, int]],
        sub_error_rates: Optional[Dict[Tuple[int, int], float]] = None,
    ) -> Dict[int, int]:
        dag = circuit_to_dag(circuit)
        qubit_indices = {q: idx for idx, q in enumerate(circuit.qubits)}
        N = len(circuit.qubits)

        interaction_freq: Dict[Tuple[int, int], int] = defaultdict(int)
        for node in dag.op_nodes():
            if len(node.qargs) == 2:
                q1 = qubit_indices[node.qargs[0]]
                q2 = qubit_indices[node.qargs[1]]
                pair = (min(q1, q2), max(q1, q2))
                interaction_freq[pair] += 1

        sub_adj: Dict[int, Set[int]] = defaultdict(set)
        for u, v in sub_coupling_map:
            sub_adj[u].add(v)
            sub_adj[v].add(u)

        all_sub_nodes = set(sub_adj.keys())
        if all_sub_nodes:
            all_sub_nodes.update(range(max(all_sub_nodes) + 1))

        sorted_pairs = sorted(interaction_freq.items(), key=lambda x: x[1], reverse=True)

        logical_to_sub: Dict[int, int] = {}
        occupied_sub_nodes: Set[int] = set()

        node_degrees = {node: len(sub_adj[node]) for node in all_sub_nodes}

        for (q1, q2), freq in sorted_pairs:
            q1_placed = q1 in logical_to_sub
            q2_placed = q2 in logical_to_sub

            if not q1_placed and not q2_placed:
                free_nodes = [n for n in all_sub_nodes if n not in occupied_sub_nodes]
                if not free_nodes:
                    break
                best_p1 = max(free_nodes, key=lambda n: node_degrees.get(n, 0))
                logical_to_sub[q1] = best_p1
                occupied_sub_nodes.add(best_p1)

                free_neighbors = [nb for nb in sub_adj[best_p1] if nb not in occupied_sub_nodes]
                if free_neighbors:
                    best_p2 = max(free_neighbors, key=lambda n: node_degrees.get(n, 0))
                else:
                    free_nodes = [n for n in all_sub_nodes if n not in occupied_sub_nodes]
                    if not free_nodes:
                        break
                    best_p2 = max(free_nodes, key=lambda n: node_degrees.get(n, 0))
                logical_to_sub[q2] = best_p2
                occupied_sub_nodes.add(best_p2)

            elif q1_placed and not q2_placed:
                p1 = logical_to_sub[q1]
                free_neighbors = [nb for nb in sub_adj[p1] if nb not in occupied_sub_nodes]
                if free_neighbors:
                    best_p2 = max(free_neighbors, key=lambda n: node_degrees.get(n, 0))
                else:
                    free_nodes = [n for n in all_sub_nodes if n not in occupied_sub_nodes]
                    if not free_nodes:
                        break
                    best_p2 = max(free_nodes, key=lambda n: node_degrees.get(n, 0))
                logical_to_sub[q2] = best_p2
                occupied_sub_nodes.add(best_p2)

            elif not q1_placed and q2_placed:
                p2 = logical_to_sub[q2]
                free_neighbors = [nb for nb in sub_adj[p2] if nb not in occupied_sub_nodes]
                if free_neighbors:
                    best_p1 = max(free_neighbors, key=lambda n: node_degrees.get(n, 0))
                else:
                    free_nodes = [n for n in all_sub_nodes if n not in occupied_sub_nodes]
                    if not free_nodes:
                        break
                    best_p1 = max(free_nodes, key=lambda n: node_degrees.get(n, 0))
                logical_to_sub[q1] = best_p1
                occupied_sub_nodes.add(best_p1)

        # Explicit failure handling: raise RuntimeError if physical slots are insufficient
        for q in range(N):
            if q not in logical_to_sub:
                free_nodes = [n for n in all_sub_nodes if n not in occupied_sub_nodes]
                if free_nodes:
                    best_p = max(free_nodes, key=lambda n: node_degrees.get(n, 0))
                    logical_to_sub[q] = best_p
                    occupied_sub_nodes.add(best_p)
                else:
                    raise RuntimeError(
                        f"FMA placement failure: Logical qubit {q} cannot be placed. "
                        f"Insufficient free physical slots in extracted subgraph of size {len(all_sub_nodes)}."
                    )

        return logical_to_sub


FMAMapper = FMALogicalPlacer
