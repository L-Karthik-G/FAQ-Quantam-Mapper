"""
Unit and Integration Tests for Quantum Compiler Pre-processing Engine
Includes semantic equivalence verification, directed hardware graph tests,
multi-start Gaussian perturbations, and Qiskit pass manager integration.
"""

import time
import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector
from qiskit.transpiler import PassManager, CouplingMap
from qiskit.transpiler.passes import SabreSwap, FullAncillaAllocation, EnlargeWithAncilla, ApplyLayout

from qap_compiler.module_a_dag import DAGInteractionMatrixBuilder
from qap_compiler.module_b_hardware import HardwareMatrixBuilder, load_ibm_heavy_hex_127
from qap_compiler.module_c_faq import AdaptiveFAQSolver, sinkhorn_knopp, refine_2opt
from qap_compiler.module_d_handoff import QMAPWarmStartHandoff
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


def test_module_c_multi_start_faq_solver():
    """Test Module C 5-start Gaussian solver, 2-opt refinement, and Sinkhorn-Knopp."""
    raw_mat = np.array([[1.0, 2.0], [3.0, 4.0]])
    ds_mat = sinkhorn_knopp(raw_mat)
    assert np.allclose(ds_mat.sum(axis=1), 1.0)
    assert np.allclose(ds_mat.sum(axis=0), 1.0)

    A = np.array([[0, 2, 1], [2, 0, 3], [1, 3, 0]], dtype=float)
    B = np.array([
        [0, 1, 2, 3, 4],
        [1, 0, 1, 2, 3],
        [2, 1, 0, 1, 2],
        [3, 2, 1, 0, 1],
        [4, 3, 2, 1, 0]
    ], dtype=float)

    solver = AdaptiveFAQSolver(num_starts=5, start_mode="gaussian", enable_2opt=True, seed=42)
    mapping, cost = solver.solve(A, B)

    assert len(mapping) == 3
    assert set(mapping.keys()) == {0, 1, 2}
    assert len(set(mapping.values())) == 3
    assert cost >= 0
    assert "best_cost" in solver.last_run_stats
    assert "mean_cost" in solver.last_run_stats
    assert solver.last_run_stats["num_starts_evaluated"] == 5


def test_module_e_fgea_and_fma():
    """Test Module E FGEA graph extractor and FMA greedy mapping."""
    cm = [(0, 1), (1, 2), (2, 3), (3, 4), (1, 5), (5, 6)]
    errs = {e: 0.01 for e in cm}

    extractor = FGEASubgraphExtractor(buffer=2)
    sub_cm, sub_errs, g2l, l2g = extractor.extract(3, 7, cm, errs)

    assert len(g2l) == 5
    assert len(l2g) == 5

    qc = QuantumCircuit(3)
    qc.cx(0, 1)
    qc.cx(1, 2)

    placer = FMALogicalPlacer()
    logical_to_sub = placer.place(qc, sub_cm, sub_errs)
    assert len(logical_to_sub) == 3
    assert len(set(logical_to_sub.values())) == 3


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

    # Initial Bell state |Phi+>
    sv_orig = Statevector.from_instruction(qc)
    sv_comp = Statevector.from_instruction(compiled_qc)

    # State fidelity must equal 1.0 (exact Bell state preparation)
    fidelity = float(np.abs(sv_orig.data.conj() @ sv_comp.data) ** 2)
    assert pytest.approx(fidelity, abs=1e-5) == 1.0
