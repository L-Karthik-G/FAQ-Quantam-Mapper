"""
Unit and Integration Tests for Quantum Compiler Pre-processing Engine
"""

import time
import numpy as np
import pytest
from qiskit import QuantumCircuit

from qap_compiler.module_a_dag import DAGInteractionMatrixBuilder
from qap_compiler.module_b_hardware import HardwareMatrixBuilder
from qap_compiler.module_c_faq import AdaptiveFAQSolver, sinkhorn_knopp
from qap_compiler.module_d_handoff import QMAPWarmStartHandoff
from qap_compiler.pipeline import FAQCompilerPipeline


def test_module_a_dag_builder():
    """Test Module A interaction matrix building and deep circuit decay plateau."""
    # Test 1: Simple 3-qubit circuit
    qc = QuantumCircuit(3)
    qc.cx(0, 1)
    qc.cx(1, 2)
    qc.cx(0, 1)

    builder = DAGInteractionMatrixBuilder(gamma=0.9, amnesia_threshold=100)
    matrix_a = builder.build_matrix(qc)

    assert matrix_a.shape == (3, 3)
    assert np.allclose(matrix_a, matrix_a.T)  # Matrix must be symmetric
    assert matrix_a[0, 1] > 0
    assert matrix_a[1, 2] > 0
    assert matrix_a[0, 2] == 0.0  # Q0 and Q2 had no direct 2-qubit gate

    # Test 2: Deep circuit (> 100 depth) amnesia fix
    deep_qc = QuantumCircuit(2)
    for _ in range(120):
        deep_qc.cx(0, 1)

    builder_amnesia = DAGInteractionMatrixBuilder(gamma=0.9, amnesia_threshold=100, plateau_length=20)
    matrix_deep = builder_amnesia.build_matrix(deep_qc)

    assert matrix_deep.shape == (2, 2)
    # Expected weight: 20 * 1.0 + sum_{k=0}^{99} (0.9^k)
    expected_weight = 20 * 1.0 + sum(0.9 ** k for k in range(100))
    assert pytest.approx(matrix_deep[0, 1], abs=1e-3) == expected_weight


def test_module_b_hardware_builder():
    """Test Module B hardware distance matrix and TTL cache."""
    # Line graph 0-1-2-3
    coupling_map = [(0, 1), (1, 0), (1, 2), (2, 1), (2, 3), (3, 2)]
    error_rates = {(0, 1): 0.01, (1, 2): 0.05, (2, 3): 0.02}

    builder = HardwareMatrixBuilder(alpha=1.0, ttl_seconds=1.0)
    matrix_b1 = builder.build_matrix(4, coupling_map, error_rates)

    assert matrix_b1.shape == (4, 4)
    assert matrix_b1[0, 0] == 0.0
    assert matrix_b1[0, 1] > 1.0  # Weighted distance > 1 due to error rate
    assert matrix_b1[0, 3] > matrix_b1[0, 1]  # Path length to 3 is longer than to 1

    # Test TTL cache hit
    matrix_b2 = builder.build_matrix(4, coupling_map, error_rates)
    assert np.array_equal(matrix_b1, matrix_b2)

    # Test TTL cache expiration
    time.sleep(1.1)
    matrix_b3 = builder.build_matrix(4, coupling_map, error_rates)
    assert np.array_equal(matrix_b1, matrix_b3)


def test_module_c_faq_solver():
    """Test Module C FAQ solver, Sinkhorn-Knopp, and N < M matrix zero padding."""
    # Test Sinkhorn-Knopp normalization
    raw_mat = np.array([[1.0, 2.0], [3.0, 4.0]])
    ds_mat = sinkhorn_knopp(raw_mat)
    assert np.allclose(ds_mat.sum(axis=1), 1.0)
    assert np.allclose(ds_mat.sum(axis=0), 1.0)

    # Test N < M padded solver
    # 3 logical qubits, 5 physical qubits
    A = np.array([[0, 2, 1], [2, 0, 3], [1, 3, 0]], dtype=float)
    # Line graph 0-1-2-3-4 distance matrix
    B = np.array([
        [0, 1, 2, 3, 4],
        [1, 0, 1, 2, 3],
        [2, 1, 0, 1, 2],
        [3, 2, 1, 0, 1],
        [4, 3, 2, 1, 0]
    ], dtype=float)

    solver = AdaptiveFAQSolver(num_starts=3, seed=42)
    mapping, cost = solver.solve(A, B)

    assert len(mapping) == 3
    assert set(mapping.keys()) == {0, 1, 2}
    assert len(set(mapping.values())) == 3  # All mapped physical qubits must be unique
    assert cost >= 0


def test_module_d_handoff():
    """Test Module D threshold switch and initial layout handoff."""
    handoff = QMAPWarmStartHandoff(threshold_qubits=10)

    assert handoff.should_bypass(5) is True
    assert handoff.should_bypass(12) is False

    qc = QuantumCircuit(3)
    qc.cx(0, 1)
    qc.cx(1, 2)

    mapping = {0: 1, 1: 2, 2: 4}
    cm = [(0, 1), (1, 0), (1, 2), (2, 1), (2, 3), (3, 2), (3, 4), (4, 3)]

    mapped_qc, results = handoff.compile_with_qmap(qc, cm, num_physical_qubits=5, initial_mapping=mapping)

    assert isinstance(mapped_qc, QuantumCircuit)
    assert mapped_qc.num_qubits == 5
    assert hasattr(results.output, "swaps")


def test_pipeline_end_to_end():
    """Integration test for FAQCompilerPipeline."""
    pipeline = FAQCompilerPipeline(threshold_qubits=5)

    qc = QuantumCircuit(6)
    for i in range(5):
        qc.cx(i, i + 1)
    qc.cx(0, 5)

    # 10-qubit line graph
    cm = [(i, i + 1) for i in range(9)] + [(i + 1, i) for i in range(9)]

    mapped_qc, metrics = pipeline.compile(qc, num_physical_qubits=10, coupling_map=cm)

    assert isinstance(mapped_qc, QuantumCircuit)
    assert metrics["bypassed_faq"] is False
    assert metrics["swaps"] >= 0
    assert metrics["total_time"] > 0


def test_module_e_fgea_and_fma():
    """Test Module E FGEASubgraphExtractor and FMAMapper."""
    from qap_compiler.module_e_fgea import FGEASubgraphExtractor, FMAMapper

    # 8-qubit coupling map
    cm = [(i, i + 1) for i in range(7)] + [(i + 1, i) for i in range(7)]
    errors = {(i, i + 1): 0.01 * (i + 1) for i in range(7)}

    extractor = FGEASubgraphExtractor(buffer=2)
    sub_cm, sub_err, g2l, l2g = extractor.extract(
        N=4, num_physical_qubits=8, coupling_map=cm, error_rates=errors
    )

    assert len(l2g) == 6  # N=4 + buffer=2
    assert len(sub_cm) > 0

    qc = QuantumCircuit(4)
    qc.cx(0, 1)
    qc.cx(1, 2)
    qc.cx(2, 3)

    mapper = FMAMapper()
    mapping = mapper.map(qc, sub_cm, len(l2g), sub_err)

    assert len(mapping) == 4
    assert len(set(mapping.values())) == 4


def test_all_pipeline_methods():
    """Verify all 10 pipeline compilation methods execute cleanly."""
    pipeline = FAQCompilerPipeline(threshold_qubits=4, seed=42)

    qc = QuantumCircuit(4)
    qc.cx(0, 1)
    qc.cx(1, 2)
    qc.cx(2, 3)
    qc.cx(0, 3)

    cm = [(i, i + 1) for i in range(7)] + [(i + 1, i) for i in range(7)]
    errors = {(i, i + 1): 0.01 for i in range(7)}

    methods = [
        ("FAQ + SABRE", lambda: pipeline.compile_faq_sabre(qc, 8, cm, errors)),
        ("FAQ + PyTKET", lambda: pipeline.compile_faq_tket(qc, 8, cm, errors)),
        ("SABRE Default", lambda: pipeline.compile_baseline_qiskit_sabre(qc, 8, cm)),
        ("QMAP Default", lambda: pipeline.compile_baseline_vanilla_qmap(qc, 8, cm)),
        ("PyTKET Default", lambda: pipeline.compile_baseline_tket(qc, 8, cm)),
        ("FGEA + FAQ + SABRE", lambda: pipeline.compile_fgea_faq_sabre(qc, 8, cm, errors)),
        ("FGEA + FAQ + PyTKET", lambda: pipeline.compile_fgea_faq_tket(qc, 8, cm, errors)),
        ("FGEA + FAQ + QMAP", lambda: pipeline.compile_fgea_faq_qmap(qc, 8, cm, errors)),
        ("Paper Method (FGEA+FMA)", lambda: pipeline.compile_paper_method(qc, 8, cm, errors)),
    ]

    for name, fn in methods:
        mapped_qc, metrics = fn()
        assert isinstance(mapped_qc, QuantumCircuit), f"{name} failed to return QuantumCircuit"
        assert metrics["swaps"] >= 0, f"{name} returned invalid SWAPs: {metrics['swaps']}"
        assert metrics["total_time"] > 0, f"{name} returned invalid time: {metrics['total_time']}"

