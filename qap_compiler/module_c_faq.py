"""
Module C: Adaptive QAP / FAQ Solver (N <= M)
Solves the Quadratic Assignment Problem using SciPy FAQ with zero-padding for N < M
and a multi-start Sinkhorn-Knopp doubly stochastic initialization wrapper.
"""

from typing import Dict, Tuple
import numpy as np
from scipy.optimize import quadratic_assignment


def sinkhorn_knopp(matrix: np.ndarray, num_iters: int = 30, tol: float = 1e-6) -> np.ndarray:
    """
    Normalizes a square matrix to be doubly stochastic using the Sinkhorn-Knopp algorithm.
    """
    P = np.copy(matrix)
    P = np.maximum(P, 1e-12)
    for _ in range(num_iters):
        r_sum = P.sum(axis=1, keepdims=True)
        r_sum[r_sum == 0] = 1.0
        P /= r_sum

        c_sum = P.sum(axis=0, keepdims=True)
        c_sum[c_sum == 0] = 1.0
        P /= c_sum
    return P


class AdaptiveFAQSolver:
    def __init__(self, num_starts: int = 3, noise_std: float = 0.01, seed: int = 42):
        """
        Args:
            num_starts: Total solver initialization runs (1 standard + (num_starts - 1) noisy).
            noise_std: Standard deviation for Gaussian noise injection (default 0.01).
            seed: Random seed for reproducible initialization.
        """
        self.num_starts = num_starts
        self.noise_std = noise_std
        self.seed = seed

    def solve(self, matrix_a: np.ndarray, matrix_b: np.ndarray) -> Tuple[Dict[int, int], float]:
        """
        Solves QAP for interaction matrix A (N x N) and hardware distance matrix B (M x M).

        Returns:
            mapping: Dict mapping logical qubit index -> physical qubit index.
            best_cost: Minimum objective value trace(A_padded^T * P * B * P^T).
        """
        N = matrix_a.shape[0]
        M = matrix_b.shape[0]

        if N > M:
            raise ValueError(f"Logical qubit count ({N}) exceeds physical qubit count ({M}).")

        # Zero-pad matrix A up to M x M if N < M
        if N < M:
            A_padded = np.zeros((M, M), dtype=float)
            A_padded[:N, :N] = matrix_a
        else:
            A_padded = np.copy(matrix_a)

        best_perm = None
        best_cost = float("inf")

        np_rng = np.random.default_rng(self.seed)

        # Multi-start runs
        for start_idx in range(self.num_starts):
            if start_idx == 0:
                # Run 1: Standard barycenter (uniform doubly stochastic matrix)
                P0 = "barycenter"
            else:
                # Runs 2+: Injected Gaussian noise on uniform doubly stochastic matrix
                base_P0 = np.ones((M, M), dtype=float) / M
                noise = np_rng.normal(0.0, self.noise_std, size=(M, M))
                P0 = sinkhorn_knopp(base_P0 + noise)

            try:
                res = quadratic_assignment(A_padded, matrix_b, method="faq", options={"P0": P0})
                cost = res.fun
                col_ind = res.col_ind

                if cost < best_cost:
                    best_cost = cost
                    best_perm = col_ind
            except Exception as e:
                # If a specific solver run fails, continue trying other starts
                continue

        if best_perm is None:
            # Fallback to identity mapping if solver fails
            best_perm = np.arange(M)
            best_cost = float(np.trace(A_padded.T @ matrix_b))

        # Map logical qubits 0..N-1 to their assigned physical qubits
        mapping = {logical_idx: int(best_perm[logical_idx]) for logical_idx in range(N)}
        return mapping, float(best_cost)
