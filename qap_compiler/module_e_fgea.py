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
import numpy as np
from qiskit import QuantumCircuit
from qiskit.converters import circuit_to_dag


class FGEASubgraphExtractor:
    """
    Fidelity-aware Graph Extraction Algorithm.
    Identifies the best-quality connected subgraph of K physical qubits
    from the full hardware coupling map, guided by edge fidelity scores.

    Algorithm:
    1. Score each physical edge: Score(u,v) = 1 - E_uv  (higher = better fidelity)
    2. Build a weighted graph where edge weight = -Score (for min-heap priority)
    3. Seed from the node with highest sum of neighbour fidelities
    4. Expand via priority BFS (greedy fidelity frontier) until K nodes collected
    5. Return the induced subgraph coupling map, error rates, and index mapping
    """

    def __init__(self, buffer: int = 4):
        """
        Args:
            buffer: Extra physical qubits beyond N to include in the subgraph.
                    K = N + buffer. More buffer gives the router more routing slack.
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
        Extracts the best-fidelity connected subgraph of size K = N + buffer.

        Returns:
            sub_coupling_map: List of (u, v) edges using re-indexed [0, K) labels
            sub_error_rates:  Dict keyed by re-indexed (u, v) pairs
            global_to_local:  Dict mapping original physical qubit idx -> local subgraph idx
            local_to_global:  Dict mapping local subgraph idx -> original physical qubit idx
        """
        K = min(N + self.buffer, num_physical_qubits)

        # Build undirected graph with fidelity-weighted edges
        G = nx.Graph()
        G.add_nodes_from(range(num_physical_qubits))

        for u, v in coupling_map:
            err = error_rates.get((u, v), error_rates.get((v, u), 0.01)) if error_rates else 0.01
            fidelity = max(1.0 - err, 1e-6)
            if not G.has_edge(u, v):
                G.add_edge(u, v, fidelity=fidelity, weight=-fidelity)  # negative for min-heap
            else:
                # If already exists, keep highest fidelity
                G[u][v]["fidelity"] = max(G[u][v]["fidelity"], fidelity)
                G[u][v]["weight"] = -G[u][v]["fidelity"]

        # Score each node as the sum of fidelities of its incident edges (degree + quality)
        node_scores = {}
        for node in G.nodes():
            neighbors = list(G.neighbors(node))
            if neighbors:
                sum_fidelity = sum(G[node][nb]["fidelity"] for nb in neighbors)
                node_scores[node] = sum_fidelity
            else:
                node_scores[node] = 0.0

        # Seed from the node with the highest neighbourhood fidelity sum
        seed_node = max(node_scores, key=node_scores.get)

        # Priority BFS expansion: (-fidelity, neighbor_node)
        selected: Set[int] = {seed_node}
        frontier = []  # min-heap on -fidelity

        for nb in G.neighbors(seed_node):
            fidelity = G[seed_node][nb]["fidelity"]
            heapq.heappush(frontier, (-fidelity, nb))

        while len(selected) < K and frontier:
            neg_fid, node = heapq.heappop(frontier)
            if node in selected:
                continue
            selected.add(node)
            # Expand frontier with unvisited neighbors
            for nb in G.neighbors(node):
                if nb not in selected:
                    fidelity = G[node][nb]["fidelity"]
                    heapq.heappush(frontier, (-fidelity, nb))

        # If graph is disconnected and selected < K, fill remaining from highest scored nodes
        if len(selected) < K:
            sorted_remaining = sorted(
                [n for n in G.nodes() if n not in selected],
                key=lambda x: node_scores.get(x, 0.0),
                reverse=True
            )
            for n in sorted_remaining:
                if len(selected) >= K:
                    break
                selected.add(n)

        selected_list = sorted(list(selected))

        # Create global <-> local bijective mappings
        global_to_local = {g_idx: l_idx for l_idx, g_idx in enumerate(selected_list)}
        local_to_global = {l_idx: g_idx for l_idx, g_idx in enumerate(selected_list)}

        # Extract induced subgraph edges and re-index to [0, K)
        sub_coupling_map: List[Tuple[int, int]] = []
        sub_error_rates: Dict[Tuple[int, int], float] = {}

        for u, v in coupling_map:
            if u in selected and v in selected:
                lu = global_to_local[u]
                lv = global_to_local[v]
                sub_coupling_map.append((lu, lv))
                if error_rates and (u, v) in error_rates:
                    sub_error_rates[(lu, lv)] = error_rates[(u, v)]
                else:
                    sub_error_rates[(lu, lv)] = 0.01

        return sub_coupling_map, sub_error_rates, global_to_local, local_to_global


class FMALogicalPlacer:
    """
    Frequency-based Mapping Algorithm (FMA).
    Greedily maps logical qubits to the extracted physical subgraph:
    1. Sort 2-qubit interactions by total interaction frequency (descending).
    2. Greedily assign the most frequent logical qubit pairs to adjacent physical
       qubits in the subgraph that maximize available high-fidelity coupling edges.
    3. Unassigned logical qubits are placed greedily on the nearest free physical slots.
    """

    def place(
        self,
        circuit: QuantumCircuit,
        sub_coupling_map: List[Tuple[int, int]],
        sub_error_rates: Optional[Dict[Tuple[int, int], float]] = None,
    ) -> Dict[int, int]:
        """
        Maps logical qubits 0..N-1 to subgraph physical slots 0..K-1.

        Returns:
            logical_to_local: Dict mapping logical qubit idx -> local subgraph qubit idx
        """
        dag = circuit_to_dag(circuit)
        qubit_indices = {q: idx for idx, q in enumerate(circuit.qubits)}
        N = len(circuit.qubits)

        # Count 2-qubit interaction frequencies
        interaction_freq: Dict[Tuple[int, int], int] = defaultdict(int)
        for node in dag.op_nodes():
            if len(node.qargs) == 2:
                q1 = qubit_indices[node.qargs[0]]
                q2 = qubit_indices[node.qargs[1]]
                pair = (min(q1, q2), max(q1, q2))
                interaction_freq[pair] += 1

        # Build physical adjacency graph for the subgraph
        sub_adj: Dict[int, Set[int]] = defaultdict(set)
        for u, v in sub_coupling_map:
            sub_adj[u].add(v)
            sub_adj[v].add(u)

        all_sub_nodes = set(sub_adj.keys())
        # Also include any isolated nodes in the subgraph
        all_sub_nodes.update(range(max(all_sub_nodes, default=-1) + 1))

        # Sort logical pairs by interaction frequency (descending)
        sorted_pairs = sorted(interaction_freq.items(), key=lambda x: x[1], reverse=True)

        logical_to_sub: Dict[int, int] = {}
        occupied_sub_nodes: Set[int] = set()

        # Score physical nodes by degree in the subgraph (centrality)
        node_degrees = {node: len(sub_adj[node]) for node in all_sub_nodes}

        for (q1, q2), freq in sorted_pairs:
            q1_placed = q1 in logical_to_sub
            q2_placed = q2 in logical_to_sub

            if not q1_placed and not q2_placed:
                # Place q1 on the highest-degree available physical node
                free_nodes = [n for n in all_sub_nodes if n not in occupied_sub_nodes]
                if not free_nodes:
                    break
                best_p1 = max(free_nodes, key=lambda n: node_degrees.get(n, 0))
                logical_to_sub[q1] = best_p1
                occupied_sub_nodes.add(best_p1)

                # Place q2 on the best adjacent free neighbor of best_p1
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

        # Place any remaining unplaced logical qubits
        for q in range(N):
            if q not in logical_to_sub:
                free_nodes = [n for n in all_sub_nodes if n not in occupied_sub_nodes]
                if free_nodes:
                    best_p = max(free_nodes, key=lambda n: node_degrees.get(n, 0))
                    logical_to_sub[q] = best_p
                    occupied_sub_nodes.add(best_p)
                else:
                    logical_to_sub[q] = q

        return logical_to_sub
FMAMapper = FMALogicalPlacer
