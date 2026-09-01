"""
Module B: Fidelity-Weighted Hardware Matrix (B) Builder
Builds the physical device distance matrix B using directed Dijkstra shortest paths
weighted by log-fidelity and directional CNOT gate error rates.
Includes a 1-hour Time-To-Live (TTL) cache to prevent stale calibration profiles.
"""

import math
import time
from typing import Dict, List, Optional, Set, Tuple, Union
import networkx as nx
import numpy as np


class HardwareMatrixBuilder:
    def __init__(self, alpha: float = 1.0, ttl_seconds: float = 3600.0):
        """
        Args:
            alpha: Fidelity weighting scaling factor alpha (default 1.0).
            ttl_seconds: Cache TTL in seconds (default 3600s / 1 hour).
        """
        self.alpha = alpha
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[Tuple, Tuple[float, np.ndarray]] = {}

    def build_matrix(
        self,
        num_physical_qubits: int,
        coupling_map: Union[List[Tuple[int, int]], Set[Tuple[int, int]]],
        error_rates: Optional[Dict[Tuple[int, int], float]] = None,
        is_directed: bool = True,
    ) -> np.ndarray:
        """
        Builds square matrix B (M x M) representing physical qubit shortest path distances.

        Args:
            num_physical_qubits: Total number of physical qubits (M).
            coupling_map: List or set of directed coupling edges (u, v).
            error_rates: Dictionary mapping physical edge (u, v) -> CNOT error rate E_{u,v}.
            is_directed: If True, builds a directed graph DiGraph preserving asymmetric gate directions.
        """
        cache_key = self._make_cache_key(num_physical_qubits, coupling_map, error_rates, is_directed)
        now = time.time()

        if cache_key in self._cache:
            timestamp, cached_matrix = self._cache[cache_key]
            if now - timestamp < self.ttl_seconds:
                return cached_matrix.copy()

        # Build Graph (DiGraph to preserve CNOT directionality and asymmetric errors)
        G = nx.DiGraph() if is_directed else nx.Graph()
        G.add_nodes_from(range(num_physical_qubits))

        edges = list(coupling_map)
        error_dict = error_rates if error_rates is not None else {}

        # Add directed edges with fidelity-weighted distances
        for u, v in edges:
            err = error_dict.get((u, v), None)
            if err is None and not is_directed:
                err = error_dict.get((v, u), None)

            if err is not None and 0.0 <= err < 1.0:
                fidelity = max(1.0 - err, 1e-6)
                weight = 1.0 + self.alpha * (-math.log(fidelity))
            else:
                weight = 1.0

            G.add_edge(u, v, weight=weight)

            # If reverse edge is also in physical hardware but not explicitly listed,
            # or in undirected mode, ensure connectivity
            if not is_directed:
                G.add_edge(v, u, weight=weight)

        # Compute all-pairs shortest paths using Dijkstra's algorithm
        path_lengths = dict(nx.all_pairs_dijkstra_path_length(G, weight="weight"))

        matrix_b = np.zeros((num_physical_qubits, num_physical_qubits), dtype=float)
        for i in range(num_physical_qubits):
            for j in range(num_physical_qubits):
                if i != j:
                    if j in path_lengths.get(i, {}):
                        matrix_b[i, j] = path_lengths[i][j]
                    else:
                        # Fallback for disconnected paths or reverse-unreachable:
                        # If reverse exists, add reverse + penalty, otherwise large penalty
                        if i in path_lengths.get(j, {}):
                            matrix_b[i, j] = path_lengths[j][i] + 1.0  # 1 extra bridge step
                        else:
                            matrix_b[i, j] = 1e6

        self._cache[cache_key] = (now, matrix_b)
        return matrix_b.copy()

    def clear_cache(self) -> None:
        """Clears the calibration TTL cache."""
        self._cache.clear()

    def _make_cache_key(
        self,
        M: int,
        coupling_map: Union[List, Set],
        error_rates: Optional[Dict],
        is_directed: bool,
    ) -> Tuple:
        sorted_map = tuple(sorted(list(coupling_map)))
        sorted_errors = tuple(sorted(list(error_rates.items()))) if error_rates else ()
        return (M, sorted_map, sorted_errors, self.alpha, is_directed)


def load_ibm_heavy_hex_127(rng: Optional[np.random.Generator] = None) -> Tuple[int, List[Tuple[int, int]], Dict[Tuple[int, int], float]]:
    """
    Constructs a realistic IBM Eagle 127-qubit Heavy-Hex topology with directional CNOT error rates.
    """
    if rng is None:
        rng = np.random.default_rng(42)

    M = 127
    edges: Set[Tuple[int, int]] = set()

    # Heavy-hex 127 layout: lattice with hex rings
    for i in range(M - 1):
        if (i % 14 != 13) and i + 1 < M:
            edges.add((i, i + 1))
            edges.add((i + 1, i))
        if i + 14 < M and (i % 7 == 0 or i % 7 == 3):
            edges.add((i, i + 14))
            edges.add((i + 14, i))

    edge_list = list(edges)
    error_rates = {
        edge: float(rng.uniform(0.008, 0.018)) for edge in edge_list
    }
    return M, edge_list, error_rates
