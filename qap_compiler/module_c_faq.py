"""
Module C: Multi-Start Quadratic Assignment Problem (QAP) Pre-Placement Solver
Solves initial logical-to-physical qubit layout over the Birkhoff polytope using
SciPy's FAQ heuristic (quadratic_assignment) and a discrete 2-opt local search refinement.

Multi-start initialization: since the multi-cell ablation (see reports/a5_results.md) showed
that the structured-Gaussian perturbation scheme does **not** beat plain random restarts once
2-opt is applied, **random multi-start + 2-opt is the default and recommended configuration**.
The structured-Gaussian start mode is retained only for reproducing the earlier ablation/eval
datasets and is deprecated (see `AdaptiveFAQSolver`).

IMPORTANT (terminology): SciPy's `quadratic_assignment(method="faq")` returns a discrete
permutation (`res.col_ind`), and `res.fun` is the *discrete* QAP cost of that permutation
(it equals sum(A*B[perm][:,perm])). The Frank-Wolfe relaxation is internal to SciPy and is
not returned. So the cost recorded *before* 2-opt polish is a discrete permutation cost, NOT
a "continuous relaxation cost". It is tracked separately from the post-2-opt cost only so the
2-opt refinement gain can be reported in the ablation study.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
from scipy.optimize import quadratic_assignment


def sinkhorn_knopp(matrix: np.ndarray, num_iters: int = 50, tol: float = 1e-6) -> np.ndarray:
    """
    Projects a non-negative square matrix onto the Birkhoff polytope (doubly stochastic).
    Guarantees row sums == 1.0 and column sums == 1.0.
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
    Discrete 2-opt pairwise local search refinement.
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
                perm[i], perm[j] = perm[j], perm[i]
                new_cost = compute_qap_cost(A, B, perm)
                if new_cost < best_cost - 1e-8:
                    best_cost = new_cost
                    improved = True
                else:
                    perm[i], perm[j] = perm[j], perm[i]
                    
    return perm, best_cost


class AdaptiveFAQSolver:
    """
    Multi-Start QAP Pre-Placement Solver.

    Combines:
      - SciPy's quadratic_assignment (FAQ method) approximate QAP pre-placement
        (returns a discrete permutation; the Frank-Wolfe relaxation is internal to SciPy).
      - Random multi-start initialization over the Birkhoff polytope (default, K starts).
      - Discrete 2-opt pairwise local search refinement.
      - Thread-pooled multi-core parallel execution.

    The default is **random multi-start + 2-opt**, which the multi-cell ablation
    (reports/a5_results.md) showed is equal-or-better than the previously-default structured
    Gaussian perturbation scheme. `start_mode="gaussian"` is deprecated and retained only for
    reproducing the earlier ablation/evaluation datasets.
    """

    def __init__(
        self,
        num_starts: int = 5,
        start_mode: str = "random",  # 'random' (default), 'barycenter', 'gaussian' (deprecated)
        enable_2opt: bool = True,
        seed: int = 42,
        max_workers: Optional[int] = 4,
    ):
        """
        Args:
            num_starts: Total multi-start initializations (default 5).
            start_mode: Mode of initialization ('random' default, 'barycenter',
                or 'gaussian' which is deprecated).
            enable_2opt: If True, applies discrete 2-opt polishing after the FAQ permutation.
            seed: Master random seed for reproducible initializations.
            max_workers: Worker threads for parallel start evaluation.
        """
        if start_mode not in ("random", "barycenter", "gaussian"):
            raise ValueError(f"Unknown start_mode: {start_mode!r}")
        self.num_starts = num_starts
        self.start_mode = start_mode
        self.enable_2opt = enable_2opt
        self.seed = seed
        self.max_workers = max_workers
        self.last_run_stats: Dict = {}

    def _generate_p0_candidates(self, M: int, rng: np.random.Generator) -> List[Union[str, np.ndarray]]:
        """
        Generates P0 initialization candidate matrices on the Birkhoff polytope.

        start_mode='random' (default) samples i.i.d. doubly-stochastic matrices; this is the
        recommended scheme (multi-cell ablation shows it equals or beats the old Gaussian
        scheme after 2-opt). start_mode='gaussian' is deprecated for new use but retained so the
        earlier ablation/eval datasets can be reproduced (see reports/a5_results.md).
        """
        candidates: List[Union[str, np.ndarray]] = []
        J0 = np.ones((M, M), dtype=float) / M

        if self.start_mode == "barycenter":
            return ["barycenter"] * self.num_starts

        if self.start_mode == "random":
            for _ in range(self.num_starts):
                rand_mat = rng.uniform(0.1, 1.0, size=(M, M))
                candidates.append(sinkhorn_knopp(rand_mat))
            return candidates

        # start_mode == "gaussian" (deprecated, kept for reproduction):
        # structured multi-scale Gaussian perturbation around barycenter J0
        candidates.append("barycenter")

        # Small noise (5% entry scale relative to 1/M)
        sigma_small = 0.05 / M
        for _ in range(min(2, max(0, self.num_starts - 1))):
            noise = rng.normal(0.0, sigma_small, size=(M, M))
            candidates.append(sinkhorn_knopp(J0 + noise))

        # Moderate noise (15% entry scale relative to 1/M)
        sigma_med = 0.15 / M
        while len(candidates) < self.num_starts:
            noise = rng.normal(0.0, sigma_med, size=(M, M))
            candidates.append(sinkhorn_knopp(J0 + noise))

        return candidates

    def _solve_single_start(
        self, A: np.ndarray, B: np.ndarray, P0: Union[str, np.ndarray]
    ) -> Tuple[np.ndarray, float, float]:
        """
        Runs a single optimization run starting from P0 via SciPy FAQ algorithm.

        Returns (perm, faq_perm_cost, polished_cost), where:
          - perm is the discrete permutation returned by FAQ.
          - faq_perm_cost is the discrete QAP cost of that permutation before 2-opt polish
            (res.fun -- NOT a continuous-relaxation value; see module docstring).
          - polished_cost is the cost after optional discrete 2-opt polish.
        """
        options = {"P0": P0, "maxiter": 30}
        res = quadratic_assignment(A, B, method="faq", options=options)
        perm = res.col_ind
        faq_perm_cost = float(res.fun)

        if self.enable_2opt:
            perm, final_polished_cost = refine_2opt(A, B, perm, max_rounds=3)
        else:
            final_polished_cost = faq_perm_cost

        return perm, faq_perm_cost, final_polished_cost

    def solve(
        self, matrix_a: np.ndarray, matrix_b: np.ndarray
    ) -> Tuple[Dict[int, int], float]:
        """
        Solves approximate QAP for interaction matrix A (N x N) and distance matrix B (M x M).

        Returns:
            mapping: Dict mapping logical qubit index -> physical qubit index.
            best_cost: Minimum objective value trace(A_padded^T * P * B * P^T) after optional 2-opt.
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

        all_results: List[Tuple[np.ndarray, float, float]] = []
        failed_starts_count = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                executor.submit(self._solve_single_start, A_padded, matrix_b, p0)
                for p0 in p0_list
            ]
            for f in futures:
                try:
                    perm, raw_faq_cost, polished_cost = f.result()
                    all_results.append((perm, raw_faq_cost, polished_cost))
                except Exception:
                    failed_starts_count += 1

        if not all_results:
            best_perm = np.arange(M)
            best_cost = float(np.trace(A_padded.T @ matrix_b))
            raw_faq_costs = [best_cost]
            polished_costs = [best_cost]
        else:
            all_results.sort(key=lambda x: x[2])  # Sort by final polished cost
            best_perm, best_raw_faq_cost, best_cost = all_results[0]
            raw_faq_costs = [c1 for _, c1, _ in all_results]
            polished_costs = [c2 for _, _, c2 in all_results]

        self.last_run_stats = {
            "num_starts_requested": len(p0_list),
            "num_starts_evaluated": len(all_results),
            "failed_starts_count": failed_starts_count,
            "best_faq_perm_cost": float(best_raw_faq_cost),
            "best_polished_cost": float(best_cost),
            "mean_faq_perm_cost": float(np.mean(raw_faq_costs)),
            "mean_polished_cost": float(np.mean(polished_costs)),
            "all_faq_perm_costs": [float(c) for c in raw_faq_costs],
            "all_polished_costs": [float(c) for c in polished_costs],
        }

        mapping = {logical_idx: int(best_perm[logical_idx]) for logical_idx in range(N)}
        return mapping, float(best_cost)
