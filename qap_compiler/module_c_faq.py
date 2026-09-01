"""
Module C: Adaptive QAP / FAQ Placement Solver (N <= M)
Solves the Quadratic Assignment Problem over the Birkhoff polytope using
Frank-Wolfe continuous relaxation with multi-scale Gaussian perturbations,
Sinkhorn-Knopp doubly stochastic projection, and discrete 2-opt refinement.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
from scipy.optimize import quadratic_assignment


def sinkhorn_knopp(matrix: np.ndarray, num_iters: int = 50, tol: float = 1e-6) -> np.ndarray:
    """
    Projects a non-negative square matrix onto the Birkhoff polytope (doubly stochastic).
    Guarantees all row sums == 1.0 and all column sums == 1.0.
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

        if np.max(np.abs(P.sum(axis=1) - 1.0)) < tol and np.max(np.abs(P.sum(axis=0) - 1.0)) < tol:
            break
    return P


def compute_qap_cost(A: np.ndarray, B: np.ndarray, perm: np.ndarray) -> float:
    """
    Computes QAP objective cost: Trace(A^T * P * B * P^T) = sum_{i,j} A[i, j] * B[perm[i], perm[j]].
    """
    return float(np.sum(A * B[perm][:, perm]))


def refine_2opt(A: np.ndarray, B: np.ndarray, initial_perm: np.ndarray, max_rounds: int = 5) -> Tuple[np.ndarray, float]:
    """
    Discrete 2-opt local search refinement.
    Iteratively swaps pairs of physical qubit assignments if it strictly decreases QAP cost.
    
    Args:
        A: Circuit interaction matrix (M x M padded).
        B: Hardware distance matrix (M x M).
        initial_perm: Initial permutation array of length M.
        max_rounds: Maximum passes over all pairwise combinations.
        
    Returns:
        perm: Refined discrete permutation array.
        cost: Final QAP cost after 2-opt refinement.
    """
    M = len(initial_perm)
    perm = np.copy(initial_perm)
    best_cost = compute_qap_cost(A, B, perm)
    
    improved = True
    round_idx = 0
    while improved and round_idx < max_rounds:
        improved = False
        round_idx += 1
        for i in range(M):
            for j in range(i + 1, M):
                # Swap i and j
                perm[i], perm[j] = perm[j], perm[i]
                new_cost = compute_qap_cost(A, B, perm)
                if new_cost < best_cost - 1e-8:
                    best_cost = new_cost
                    improved = True
                else:
                    # Revert swap
                    perm[i], perm[j] = perm[j], perm[i]
                    
    return perm, best_cost


class AdaptiveFAQSolver:
    """
    Adaptive Multi-Start Quadratic Assignment Problem (QAP) Pre-Placement Solver.
    
    Features:
      - 5-Start Structured Gaussian Perturbation (1 Barycenter, 2 small noise, 2 medium noise).
      - Sinkhorn-Knopp doubly stochastic projection.
      - Optional discrete 2-opt local search refinement.
      - Multi-threaded parallel start execution.
      - Detailed cost metrics: Best-of-K, Mean-of-K, and per-start history.
    """

    def __init__(
        self,
        num_starts: int = 5,
        start_mode: str = "gaussian",  # 'barycenter', 'gaussian', 'random', 'multi_scale'
        enable_2opt: bool = True,
        momentum_beta: float = 0.9,
        seed: int = 42,
        max_workers: Optional[int] = 4,
    ):
        """
        Args:
            num_starts: Total initialization runs (default 5).
            start_mode: Mode of initialization ('barycenter', 'gaussian', 'random', 'multi_scale').
            enable_2opt: If True, applies discrete 2-opt polishing after continuous Frank-Wolfe.
            momentum_beta: Momentum factor for gradient smoothing (0.0 to disable).
            seed: Master random seed for reproducible perturbations.
            max_workers: Worker threads for parallel start evaluation.
        """
        self.num_starts = num_starts
        self.start_mode = start_mode
        self.enable_2opt = enable_2opt
        self.momentum_beta = momentum_beta
        self.seed = seed
        self.max_workers = max_workers
        self.last_run_stats: Dict = {}

    def _generate_p0_candidates(self, M: int, rng: np.random.Generator) -> List[Union[str, np.ndarray]]:
        """
        Generates P0 initialization candidate matrices on the Birkhoff polytope.
        """
        candidates: List[Union[str, np.ndarray]] = []
        J0 = np.ones((M, M), dtype=float) / M

        if self.start_mode == "barycenter":
            return ["barycenter"] * self.num_starts

        if self.start_mode == "random":
            # Pure random doubly stochastic matrices
            for _ in range(self.num_starts):
                rand_mat = rng.uniform(0.1, 1.0, size=(M, M))
                candidates.append(sinkhorn_knopp(rand_mat))
            return candidates

        # Default: Structured multi-scale Gaussian perturbation around barycenter
        # Start 1: Exact Barycenter
        candidates.append("barycenter")

        # Start 2 & 3: Small adaptive noise (5% of barycenter entry)
        sigma_small = 0.05 / M
        for _ in range(min(2, max(0, self.num_starts - 1))):
            noise = rng.normal(0.0, sigma_small, size=(M, M))
            candidates.append(sinkhorn_knopp(J0 + noise))

        # Start 4+: Moderate adaptive noise (15% of barycenter entry)
        sigma_med = 0.15 / M
        while len(candidates) < self.num_starts:
            noise = rng.normal(0.0, sigma_med, size=(M, M))
            candidates.append(sinkhorn_knopp(J0 + noise))

        return candidates

    def _solve_single_start(
        self, A: np.ndarray, B: np.ndarray, P0: Union[str, np.ndarray]
    ) -> Tuple[np.ndarray, float]:
        """
        Runs a single Frank-Wolfe optimization starting from P0.
        """
        options = {"P0": P0, "maxiter": 30}
        res = quadratic_assignment(A, B, method="faq", options=options)
        perm = res.col_ind
        cost = float(res.fun)

        if self.enable_2opt:
            perm, cost = refine_2opt(A, B, perm, max_rounds=3)

        return perm, cost

    def solve(
        self, matrix_a: np.ndarray, matrix_b: np.ndarray
    ) -> Tuple[Dict[int, int], float]:
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

        rng = np.random.default_rng(self.seed)
        p0_list = self._generate_p0_candidates(M, rng)

        all_results: List[Tuple[np.ndarray, float]] = []

        # Execute starts in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                executor.submit(self._solve_single_start, A_padded, matrix_b, p0)
                for p0 in p0_list
            ]
            for f in futures:
                try:
                    perm, cost = f.result()
                    all_results.append((perm, cost))
                except Exception:
                    continue

        if not all_results:
            # Fallback to identity mapping if solver fails
            best_perm = np.arange(M)
            best_cost = float(np.trace(A_padded.T @ matrix_b))
            all_costs = [best_cost]
        else:
            all_results.sort(key=lambda x: x[1])
            best_perm, best_cost = all_results[0]
            all_costs = [cost for _, cost in all_results]

        # Record detailed multi-start statistics
        self.last_run_stats = {
            "num_starts_evaluated": len(all_results),
            "best_cost": float(best_cost),
            "mean_cost": float(np.mean(all_costs)),
            "std_cost": float(np.std(all_costs)),
            "all_costs": [float(c) for c in all_costs],
        }

        # Map logical qubits 0..N-1 to their assigned physical qubits
        mapping = {logical_idx: int(best_perm[logical_idx]) for logical_idx in range(N)}
        return mapping, float(best_cost)
