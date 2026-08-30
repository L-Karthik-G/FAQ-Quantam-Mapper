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
            if u < v:  # Only add undirected edges once
                err = error_rates.get((u, v), error_rates.get((v, u), 0.01)) if error_rates else 0.01
                fidelity = 1.0 - err
                G.add_edge(u, v, fidelity=fidelity, weight=-fidelity)  # negative for min-heap

        # Score each node as the average fidelity of its incident edges
        node_scores = {}
        for node in G.nodes():
            neighbors = list(G.neighbors(node))
            if neighbors:
                avg_fidelity = np.mean([G[node][nb]["fidelity"] for nb in neighbors])
                node_scores[node] = avg_fidelity
            else:
                node_scores[node] = 0.0

        # Seed from the node with the highest neighbourhood fidelity
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

        # Build local index maps
        selected_sorted = sorted(selected)
        global_to_local = {g: l for l, g in enumerate(selected_sorted)}
        local_to_global = {l: g for l, g in enumerate(selected_sorted)}

        # Extract subgraph edges (re-indexed)
        sub_coupling_map = []
        sub_error_rates = {}
        for u, v in coupling_map:
            if u in selected and v in selected:
                lu, lv = global_to_local[u], global_to_local[v]
                sub_coupling_map.append((lu, lv))
                err = error_rates.get((u, v), 0.01) if error_rates else 0.01
                sub_error_rates[(lu, lv)] = err
                sub_error_rates[(lv, lu)] = err

        return sub_coupling_map, sub_error_rates, global_to_local, local_to_global


class FMAMapper:
    """
    Frequency-based Mapping Algorithm (FMA) from IEEE QCE 2023.
    Greedily assigns logical qubits to physical qubit slots based on
    2-qubit interaction frequency from the circuit DAG.

    Algorithm:
    1. Count interaction frequency f(i,j) for each logical qubit pair (i,j)
    2. Sort pairs by frequency (descending)
    3. For each high-frequency pair, assign logical qubits to adjacent physical slots
       that minimize the distance between them in the hardware graph
    4. Return initial layout dict {logical_qubit_idx: physical_qubit_idx}
    """

    def map(
        self,
        circuit: QuantumCircuit,
        coupling_map: List[Tuple[int, int]],
        num_physical_qubits: int,
        error_rates: Optional[Dict[Tuple[int, int], float]] = None,
    ) -> Dict[int, int]:
        """
        Greedy frequency-based placement.

        Returns:
            Dict mapping logical qubit index -> physical qubit index
        """
        N = circuit.num_qubits
        qubit_indices = {q: i for i, q in enumerate(circuit.qubits)}

        # Step 1: Count 2-qubit interaction frequencies from circuit DAG
        dag = circuit_to_dag(circuit)
        freq = defaultdict(int)
        for node in dag.two_qubit_ops():
            qargs = node.qargs
            if len(qargs) == 2:
                i = qubit_indices[qargs[0]]
                j = qubit_indices[qargs[1]]
                pair = (min(i, j), max(i, j))
                freq[pair] += 1

        # Step 2: Sort pairs by frequency descending
        sorted_pairs = sorted(freq.items(), key=lambda x: -x[1])

        # Step 3: Build hardware adjacency for greedy placement
        G_hw = nx.Graph()
        G_hw.add_nodes_from(range(num_physical_qubits))
        for u, v in coupling_map:
            if u < v:
                err = error_rates.get((u, v), error_rates.get((v, u), 0.01)) if error_rates else 0.01
                G_hw.add_edge(u, v, fidelity=1.0 - err)

        # Greedy assignment
        logical_to_physical = {}
        used_physical = set()

        # Find best seed physical qubit (highest average neighbor fidelity)
        node_scores = {}
        for node in G_hw.nodes():
            neighbors = list(G_hw.neighbors(node))
            if neighbors:
                node_scores[node] = np.mean([G_hw[node][nb]["fidelity"] for nb in neighbors])
            else:
                node_scores[node] = 0.0

        for (li, lj), f in sorted_pairs:
            if li in logical_to_physical and lj in logical_to_physical:
                continue

            if li not in logical_to_physical and lj not in logical_to_physical:
                # Find best unoccupied adjacent pair on hardware
                best_pair = None
                best_score = -1.0
                for pu, pv, data in G_hw.edges(data=True):
                    if pu not in used_physical and pv not in used_physical:
                        score = data.get("fidelity", 0.9)
                        if score > best_score:
                            best_score = score
                            best_pair = (pu, pv)
                if best_pair:
                    logical_to_physical[li] = best_pair[0]
                    logical_to_physical[lj] = best_pair[1]
                    used_physical.add(best_pair[0])
                    used_physical.add(best_pair[1])

            elif li in logical_to_physical and lj not in logical_to_physical:
                # Assign lj to the best unoccupied neighbor of li's physical slot
                pi = logical_to_physical[li]
                best_nb = None
                best_fid = -1.0
                for nb in G_hw.neighbors(pi):
                    if nb not in used_physical:
                        fid = G_hw[pi][nb].get("fidelity", 0.9)
                        if fid > best_fid:
                            best_fid = fid
                            best_nb = nb
                if best_nb is not None:
                    logical_to_physical[lj] = best_nb
                    used_physical.add(best_nb)

            elif lj in logical_to_physical and li not in logical_to_physical:
                pj = logical_to_physical[lj]
                best_nb = None
                best_fid = -1.0
                for nb in G_hw.neighbors(pj):
                    if nb not in used_physical:
                        fid = G_hw[pj][nb].get("fidelity", 0.9)
                        if fid > best_fid:
                            best_fid = fid
                            best_nb = nb
                if best_nb is not None:
                    logical_to_physical[li] = best_nb
                    used_physical.add(best_nb)

        # Fill any remaining unassigned logical qubits with any free physical slot
        all_physical = set(range(num_physical_qubits))
        free_physical = sorted(all_physical - used_physical)
        for lq in range(N):
            if lq not in logical_to_physical:
                if free_physical:
                    pq = free_physical.pop(0)
                    logical_to_physical[lq] = pq
                    used_physical.add(pq)
                else:
                    # Fallback: identity mapping
                    logical_to_physical[lq] = lq % num_physical_qubits

        return logical_to_physical
