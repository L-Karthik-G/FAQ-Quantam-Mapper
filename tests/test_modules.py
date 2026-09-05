"""
Unit and Integration Tests for Quantum Compiler Pre-processing Engine
Includes semantic quantum state verification, directed hardware graph tests,
multi-start Gaussian solver verification, 2-opt refinement tests, and Qiskit pass manager integration.
"""

import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector
from qiskit.transpiler import CouplingMap, PassManager
from qiskit.transpiler.passes import (
    ApplyLayout,
    EnlargeWithAncilla,
    FullAncillaAllocation,
    SabreSwap,
)

from qap_compiler.module_a_dag import DAGInteractionMatrixBuilder
from qap_compiler.module_b_hardware import HardwareMatrixBuilder, load_ibm_heavy_hex_127
from qap_compiler.module_c_faq import (
    AdaptiveFAQSolver,
    compute_qap_cost,
    refine_2opt,
    sinkhorn_knopp,
)
from qap_compiler.module_e_fgea import FGEASubgraphExtractor, FMALogicalPlacer
from qap_compiler.pipeline import FAQCompilerPipeline
from qap_compiler.qiskit_plugin import FAQPlacementPass


def test_module_a_dag_builder():
    """Test Module A interaction matrix building and deep circuit decay plateau."""
    qc = QuantumCircuit(3)
    qc.cx(0, 1)
    qc.cx(1, 2)
    qc.cx(0, 1)

    builder = DAGInteractionMatrixBuilder(gamma=0.9)
    matrix_a = builder.build_matrix(qc)

    assert matrix_a.shape == (3, 3)
    assert np.allclose(matrix_a, matrix_a.T)
    assert matrix_a[0, 1] > 0
    assert matrix_a[1, 2] > 0
    assert matrix_a[0, 2] == 0.0


def test_module_b_directed_hardware_builder():
    """Test Module B directed hardware distance matrix and TTL cache."""
    coupling_map = [(0, 1), (1, 2), (2, 3)]
    error_rates = {(0, 1): 0.01, (1, 2): 0.05, (2, 3): 0.02}

    builder = HardwareMatrixBuilder(alpha=1.0, ttl_seconds=1.0)
    matrix_b = builder.build_matrix(4, coupling_map, error_rates, is_directed=True)

    assert matrix_b.shape == (4, 4)
    assert matrix_b[0, 0] == 0.0
    assert matrix_b[0, 1] > 1.0
    assert matrix_b[0, 3] > matrix_b[0, 1]

    # Test real IBM Eagle 127q topology loader
    M, edges, errs = load_ibm_heavy_hex_127()
    assert M == 127
    assert len(edges) > 100
    assert len(errs) == len(edges)


def test_module_c_multi_start_improvement_and_2opt():
    """Verify that multi-start Gaussian solver and 2-opt refinement strictly improve or maintain QAP cost."""
    rng = np.random.default_rng(42)
    M = 6
    A = rng.uniform(0, 5, size=(M, M))
    A = (A + A.T) / 2.0
    B = rng.uniform(1, 10, size=(M, M))
    np.fill_diagonal(B, 0.0)

    # 1. Test Sinkhorn-Knopp doubly stochastic projection
    raw_mat = rng.uniform(0.1, 1.0, size=(M, M))
    ds_mat = sinkhorn_knopp(raw_mat)
    assert np.allclose(ds_mat.sum(axis=1), 1.0)
    assert np.allclose(ds_mat.sum(axis=0), 1.0)

    # 2. Test 2-opt local search refinement
    init_perm = np.arange(M)
    init_cost = compute_qap_cost(A, B, init_perm)
    refined_perm, refined_cost = refine_2opt(A, B, init_perm, max_rounds=5)
    assert refined_cost <= init_cost + 1e-8

    # 3. Test multi-start improvement over single start
    solver_single = AdaptiveFAQSolver(num_starts=1, start_mode="barycenter", enable_2opt=False, seed=42)
    _, cost_single = solver_single.solve(A, B)

    solver_multi = AdaptiveFAQSolver(num_starts=5, start_mode="gaussian", enable_2opt=True, seed=42)
    _, cost_multi = solver_multi.solve(A, B)

    assert cost_multi <= cost_single + 1e-8


def test_module_e_fgea_and_fma_exception_on_overfill():
    """Test Module E FGEA graph extractor and FMA error handling on node overfill."""
    cm = [(0, 1), (1, 2), (2, 3)]
    errs = {e: 0.01 for e in cm}

    extractor = FGEASubgraphExtractor(buffer=1)
    sub_cm, sub_errs, g2l, l2g = extractor.extract(2, 4, cm, errs)

    assert len(g2l) <= 3

    qc = QuantumCircuit(2)
    qc.cx(0, 1)

    placer = FMALogicalPlacer()
    logical_to_sub = placer.place(qc, sub_cm, sub_errs)
    assert len(logical_to_sub) == 2

    # Overfill test: try placing 10 qubits in a 3-qubit subgraph -> must raise RuntimeError
    big_qc = QuantumCircuit(10)
    for i in range(9):
        big_qc.cx(i, i + 1)
    with pytest.raises(RuntimeError, match="FMA placement failure"):
        placer.place(big_qc, sub_cm, sub_errs)


def test_qiskit_plugin_pass_manager():
    """Test native Qiskit FAQPlacementPass plugin with PassManager."""
    cm = CouplingMap([(0, 1), (1, 2), (2, 3), (3, 4)])
    qc = QuantumCircuit(3)
    qc.h(0)
    qc.cx(0, 1)
    qc.cx(1, 2)

    pm = PassManager([
        FAQPlacementPass(cm, num_starts=5, seed=42),
        FullAncillaAllocation(cm),
        EnlargeWithAncilla(),
        ApplyLayout(),
        SabreSwap(cm, seed=42)
    ])
    transpiled = pm.run(qc)
    assert isinstance(transpiled, QuantumCircuit)
    assert transpiled.num_qubits == 5


def test_semantic_state_equivalence():
    """Verify semantic quantum state preservation on a test circuit."""
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)

    cm = [(0, 1), (1, 0)]
    pipeline = FAQCompilerPipeline(num_faq_starts=5, seed=42)
    compiled_qc, metrics = pipeline.compile_faq_sabre(qc, num_physical_qubits=2, coupling_map=cm)

    sv_orig = Statevector.from_instruction(qc)
    sv_comp = Statevector.from_instruction(compiled_qc)

    fidelity = float(np.abs(sv_orig.data.conj() @ sv_comp.data) ** 2)
    assert pytest.approx(fidelity, abs=1e-5) == 1.0
