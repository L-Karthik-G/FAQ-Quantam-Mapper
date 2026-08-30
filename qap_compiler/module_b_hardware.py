"""
Module B: Fidelity-Weighted Hardware Matrix (B) Builder
Builds the physical device distance matrix B using Dijkstra shortest paths weighted by log-fidelity.
Includes a 1-hour Time-To-Live (TTL) cache to prevent stale calibration profiles.
"""

import math
import time
from typing import Dict, List, Optional, Tuple, Union
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
        coupling_map: Union[List[Tuple[int, int]], set],
        error_rates: Optional[Dict[Tuple[int, int], float]] = None,
    ) -> np.ndarray:
        """
        Builds square matrix B (M x M) representing physical qubit shortest path distances.

        Args:
            num_physical_qubits: Total number of physical qubits (M).
            coupling_map: List or set of directed/undirected coupling edges (u, v).
            error_rates: Dictionary mapping physical edge (u, v) -> CNOT error rate E_{u,v}.
        """
        cache_key = self._make_cache_key(num_physical_qubits, coupling_map, error_rates)
        now = time.time()

        if cache_key in self._cache:
            timestamp, cached_matrix = self._cache[cache_key]
            if now - timestamp < self.ttl_seconds:
                return cached_matrix.copy()

        # Build undirected graph G
        G = nx.Graph()
        G.add_nodes_from(range(num_physical_qubits))

        edges = list(coupling_map)
        error_dict = error_rates if error_rates is not None else {}

        # Add edges with fidelity-weighted distances
        for u, v in edges:
            err = error_dict.get((u, v), error_dict.get((v, u), None))
            if err is not None and 0 <= err < 1.0:
                fidelity = max(1 - err, 1e-6)
                weight = 1.0 + self.alpha * (-math.log(fidelity))
            else:
                weight = 1.0

            if G.has_edge(u, v):
                # If edge already exists, update weight if lower
                G[u][v]["weight"] = min(G[u][v]["weight"], weight)
            else:
                G.add_edge(u, v, weight=weight)

        # Compute all-pairs shortest paths using Dijkstra's algorithm
        path_lengths = dict(nx.all_pairs_dijkstra_path_length(G, weight="weight"))

        matrix_b = np.zeros((num_physical_qubits, num_physical_qubits), dtype=float)
        for i in range(num_physical_qubits):
            for j in range(num_physical_qubits):
                if i != j:
                    if j in path_lengths.get(i, {}):
                        matrix_b[i, j] = path_lengths[i][j]
                    else:
                        # Disconnected nodes fallback to large distance penalty
                        matrix_b[i, j] = 1e6

        self._cache[cache_key] = (now, matrix_b)
        return matrix_b.copy()

    def clear_cache(self) -> None:
        """Clears the calibration TTL cache."""
        self._cache.clear()

    def _make_cache_key(self, M: int, coupling_map: Union[List, set], error_rates: Optional[Dict]) -> Tuple:
        sorted_map = tuple(sorted(list(coupling_map)))
        sorted_errors = tuple(sorted(list(error_rates.items()))) if error_rates else ()
        return (M, sorted_map, sorted_errors, self.alpha)
