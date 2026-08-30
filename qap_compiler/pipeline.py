"""
Pipeline: End-to-End FAQ Pre-processing Quantum Compiler Engine
Integrates Modules A-E into a unified interface with support for multi-framework
baseline and hybrid FAQ / FGEA seeding comparisons (Qiskit SABRE, PyTKET, MQT QMAP).
"""

import time
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit.transpiler import CouplingMap

from pytket.architecture import Architecture
from pytket.extensions.qiskit import qiskit_to_tk, tk_to_qiskit
from pytket.passes import RoutingPass, PlacementPass
from pytket.placement import GraphPlacement

from .module_a_dag import DAGInteractionMatrixBuilder
from .module_b_hardware import HardwareMatrixBuilder
from .module_c_faq import AdaptiveFAQSolver
from .module_d_handoff import QMAPWarmStartHandoff
from .module_e_fgea import FGEASubgraphExtractor, FMAMapper


def decompose_to_basis_gates(circuit: QuantumCircuit) -> QuantumCircuit:
    """Decomposes custom/high-level gates into 1-qubit and 2-qubit basis gates."""
    return transpile(circuit, basis_gates=["cx", "h", "rz", "x", "sx"], optimization_level=0)


class FAQCompilerPipeline:
    def __init__(
        self,
        gamma: float = 0.9,
        alpha: float = 1.0,
        threshold_qubits: int = 10,
        amnesia_threshold: int = 100,
        num_faq_starts: int = 3,
        ttl_seconds: float = 3600.0,
        seed: int = 42,
        fgea_buffer: int = 4,
    ):
        self.dag_builder = DAGInteractionMatrixBuilder(
            gamma=gamma, amnesia_threshold=amnesia_threshold
        )
        self.hardware_builder = HardwareMatrixBuilder(alpha=alpha, ttl_seconds=ttl_seconds)
        self.faq_solver = AdaptiveFAQSolver(num_starts=num_faq_starts, seed=seed)
        self.handoff_handler = QMAPWarmStartHandoff(threshold_qubits=threshold_qubits)
        self.fgea_extractor = FGEASubgraphExtractor(buffer=fgea_buffer)
        self.fma_mapper = FMAMapper()

    def get_faq_layout(
        self,
        circuit: QuantumCircuit,
        num_physical_qubits: int,
        coupling_map: Union[List[Tuple[int, int]], set],
        error_rates: Optional[Dict[Tuple[int, int], float]] = None,
    ) -> Tuple[Dict[int, int], float]:
        """Computes the FAQ initial layout mapping {logical_idx: physical_idx}."""
        matrix_a = self.dag_builder.build_matrix(circuit)
        matrix_b = self.hardware_builder.build_matrix(num_physical_qubits, coupling_map, error_rates)
        mapping, cost = self.faq_solver.solve(matrix_a, matrix_b)
        return mapping, cost

    def compile(
        self,
        circuit: QuantumCircuit,
        num_physical_qubits: int,
        coupling_map: Union[List[Tuple[int, int]], set],
        error_rates: Optional[Dict[Tuple[int, int], float]] = None,
        force_faq: bool = False,
    ) -> Tuple[QuantumCircuit, Dict]:
        """Executes FAQ pre-processing + MQT QMAP compilation."""
        start_time = time.perf_counter()
        circuit = decompose_to_basis_gates(circuit)

        N = circuit.num_qubits
        M = num_physical_qubits

        bypass = self.handoff_handler.should_bypass(N) and not force_faq
        mapping = None
        preprocessing_time = 0.0

        if not bypass:
            prep_start = time.perf_counter()
            mapping, _ = self.get_faq_layout(circuit, M, coupling_map, error_rates)
            preprocessing_time = time.perf_counter() - prep_start

        qmap_start = time.perf_counter()
        mapped_qc, qmap_results = self.handoff_handler.compile_with_qmap(
            circuit, coupling_map, M, initial_mapping=mapping
        )
        qmap_time = time.perf_counter() - qmap_start
        total_time = time.perf_counter() - start_time

        swaps = getattr(qmap_results.output, "swaps", 0)

        metrics = {
            "total_time": total_time,
            "preprocessing_time": preprocessing_time,
            "routing_time": qmap_time,
            "swaps": swaps,
            "bypassed_faq": bypass,
            "initial_mapping": mapping,
            "original_depth": circuit.depth(),
            "mapped_depth": mapped_qc.depth(),
        }

        return mapped_qc, metrics

    def compile_faq_sabre(
        self,
        circuit: QuantumCircuit,
        num_physical_qubits: int,
        coupling_map: Union[List[Tuple[int, int]], set],
        error_rates: Optional[Dict[Tuple[int, int], float]] = None,
    ) -> Tuple[QuantumCircuit, Dict]:
        """Hybrid: FAQ Initial Layout + Qiskit SABRE Routing."""
        start_time = time.perf_counter()
        circuit = decompose_to_basis_gates(circuit)

        M = num_physical_qubits
        prep_start = time.perf_counter()
        mapping, _ = self.get_faq_layout(circuit, M, coupling_map, error_rates)
        preprocessing_time = time.perf_counter() - prep_start

        # Convert mapping dictionary {logical_idx: physical_idx} to list
        initial_layout_list = [mapping.get(i, i) for i in range(circuit.num_qubits)]
        cm = CouplingMap(couplinglist=list(coupling_map))

        sabre_start = time.perf_counter()
        mapped_qc = transpile(
            circuit,
            coupling_map=cm,
            initial_layout=initial_layout_list,
            layout_method=None,
            routing_method="sabre",
            optimization_level=1,
        )
        routing_time = time.perf_counter() - sabre_start
        total_time = time.perf_counter() - start_time

        ops = mapped_qc.count_ops()
        swaps = ops.get("swap", 0)

        metrics = {
            "total_time": total_time,
            "preprocessing_time": preprocessing_time,
            "routing_time": routing_time,
            "swaps": swaps,
            "bypassed_faq": False,
            "initial_mapping": mapping,
            "original_depth": circuit.depth(),
            "mapped_depth": mapped_qc.depth(),
        }

        return mapped_qc, metrics

    def compile_faq_tket(
        self,
        circuit: QuantumCircuit,
        num_physical_qubits: int,
        coupling_map: Union[List[Tuple[int, int]], set],
        error_rates: Optional[Dict[Tuple[int, int], float]] = None,
    ) -> Tuple[QuantumCircuit, Dict]:
        """Hybrid: FAQ Initial Layout + PyTKET LexiRoute RoutingPass."""
        start_time = time.perf_counter()
        circuit = decompose_to_basis_gates(circuit)

        M = num_physical_qubits
        prep_start = time.perf_counter()
        mapping, _ = self.get_faq_layout(circuit, M, coupling_map, error_rates)
        preprocessing_time = time.perf_counter() - prep_start

        # Embed circuit onto physical qubits M according to FAQ mapping
        qubit_indices = {q: i for i, q in enumerate(circuit.qubits)}
        clbit_indices = {c: i for i, c in enumerate(circuit.clbits)}
        seeded_circuit = QuantumCircuit(M, circuit.num_clbits)
        for inst in circuit.data:
            q_args = [seeded_circuit.qubits[mapping[qubit_indices[q]]] for q in inst.qubits]
            c_args = [seeded_circuit.clbits[clbit_indices[c]] for c in inst.clbits]
            seeded_circuit.append(inst.operation, q_args, c_args)

        tk_circ = qiskit_to_tk(seeded_circuit)
        arc = Architecture(list(coupling_map))

        tket_start = time.perf_counter()
        RoutingPass(arc).apply(tk_circ)
        routing_time = time.perf_counter() - tket_start

        mapped_qc = tk_to_qiskit(tk_circ)
        total_time = time.perf_counter() - start_time

        ops = mapped_qc.count_ops()
        swaps = ops.get("swap", 0)

        metrics = {
            "total_time": total_time,
            "preprocessing_time": preprocessing_time,
            "routing_time": routing_time,
            "swaps": swaps,
            "bypassed_faq": False,
            "initial_mapping": mapping,
            "original_depth": circuit.depth(),
            "mapped_depth": mapped_qc.depth(),
        }

        return mapped_qc, metrics

    def compile_baseline_qiskit_sabre(
        self,
        circuit: QuantumCircuit,
        num_physical_qubits: int,
        coupling_map: Union[List[Tuple[int, int]], set],
        optimization_level: int = 1,
    ) -> Tuple[QuantumCircuit, Dict]:
        """Baseline 1: Standard Qiskit transpiler with SABRE layout & routing."""
        start_time = time.perf_counter()

        circuit = decompose_to_basis_gates(circuit)
        cm = CouplingMap(couplinglist=list(coupling_map))
        mapped_qc = transpile(
            circuit,
            coupling_map=cm,
            layout_method="sabre",
            routing_method="sabre",
            optimization_level=optimization_level,
        )

        total_time = time.perf_counter() - start_time
        ops = mapped_qc.count_ops()
        swaps = ops.get("swap", 0)

        metrics = {
            "total_time": total_time,
            "preprocessing_time": 0.0,
            "routing_time": total_time,
            "swaps": swaps,
            "bypassed_faq": True,
            "original_depth": circuit.depth(),
            "mapped_depth": mapped_qc.depth(),
        }

        return mapped_qc, metrics

    def compile_baseline_vanilla_qmap(
        self,
        circuit: QuantumCircuit,
        num_physical_qubits: int,
        coupling_map: Union[List[Tuple[int, int]], set],
    ) -> Tuple[QuantumCircuit, Dict]:
        """Baseline 2: Native MQT QMAP solver without FAQ pre-processing seeds."""
        start_time = time.perf_counter()

        circuit = decompose_to_basis_gates(circuit)
        mapped_qc, qmap_results = self.handoff_handler.compile_with_qmap(
            circuit, coupling_map, num_physical_qubits, initial_mapping=None
        )

        total_time = time.perf_counter() - start_time
        swaps = getattr(qmap_results.output, "swaps", 0)

        metrics = {
            "total_time": total_time,
            "preprocessing_time": 0.0,
            "routing_time": total_time,
            "swaps": swaps,
            "bypassed_faq": True,
            "original_depth": circuit.depth(),
            "mapped_depth": mapped_qc.depth(),
        }

        return mapped_qc, metrics

    def compile_baseline_tket(
        self,
        circuit: QuantumCircuit,
        num_physical_qubits: int,
        coupling_map: Union[List[Tuple[int, int]], set],
    ) -> Tuple[QuantumCircuit, Dict]:
        """Baseline 3: PyTKET GraphPlacement & RoutingPass."""
        start_time = time.perf_counter()

        circuit = decompose_to_basis_gates(circuit)
        tk_circ = qiskit_to_tk(circuit)

        # Build TKET Architecture
        arc = Architecture(list(coupling_map))
        placement = GraphPlacement(arc)
        PlacementPass(placement).apply(tk_circ)
        RoutingPass(arc).apply(tk_circ)

        mapped_qc = tk_to_qiskit(tk_circ)

        total_time = time.perf_counter() - start_time
        ops = mapped_qc.count_ops()
        swaps = ops.get("swap", 0)

        metrics = {
            "total_time": total_time,
            "preprocessing_time": 0.0,
            "routing_time": total_time,
            "swaps": swaps,
            "bypassed_faq": True,
            "original_depth": circuit.depth(),
            "mapped_depth": mapped_qc.depth(),
        }

        return mapped_qc, metrics

    # ──────────────────────────────────────────────────────────────────────────
    # FGEA + FAQ Hybrid Methods (Module E integration)
    # ──────────────────────────────────────────────────────────────────────────

    def _get_fgea_faq_layout(
        self,
        circuit: QuantumCircuit,
        num_physical_qubits: int,
        coupling_map: Union[List[Tuple[int, int]], set],
        error_rates: Optional[Dict[Tuple[int, int], float]] = None,
    ) -> Tuple[Dict[int, int], Dict[int, int]]:
        """
        FGEA subgraph extraction followed by FAQ layout on the extracted subgraph.
        Returns full-chip mapping {logical: physical} and local_to_global index map.
        """
        N = circuit.num_qubits

        # Step 1: FGEA — extract cleanest K-qubit subgraph
        sub_cm, sub_err, global_to_local, local_to_global = self.fgea_extractor.extract(
            N, num_physical_qubits, list(coupling_map), error_rates
        )
        K = len(local_to_global)

        # Step 2: FAQ — solve on the subgraph matrices
        matrix_a = self.dag_builder.build_matrix(circuit)
        matrix_b = self.hardware_builder.build_matrix(K, sub_cm, sub_err)
        local_mapping, _ = self.faq_solver.solve(matrix_a, matrix_b)

        # Step 3: Re-map local subgraph indices back to global physical qubit indices
        global_mapping = {lq: local_to_global[local_mapping[lq]] for lq in local_mapping}
        return global_mapping, local_to_global

    def compile_fgea_faq_sabre(
        self,
        circuit: QuantumCircuit,
        num_physical_qubits: int,
        coupling_map: Union[List[Tuple[int, int]], set],
        error_rates: Optional[Dict[Tuple[int, int], float]] = None,
    ) -> Tuple[QuantumCircuit, Dict]:
        """FGEA Subgraph Extraction → FAQ Layout → Qiskit SABRE Routing."""
        start_time = time.perf_counter()
        circuit = decompose_to_basis_gates(circuit)

        prep_start = time.perf_counter()
        mapping, _ = self._get_fgea_faq_layout(circuit, num_physical_qubits, coupling_map, error_rates)
        preprocessing_time = time.perf_counter() - prep_start

        initial_layout_list = [mapping.get(i, i) for i in range(circuit.num_qubits)]
        cm = CouplingMap(couplinglist=list(coupling_map))

        sabre_start = time.perf_counter()
        mapped_qc = transpile(
            circuit,
            coupling_map=cm,
            initial_layout=initial_layout_list,
            layout_method=None,
            routing_method="sabre",
            optimization_level=1,
        )
        routing_time = time.perf_counter() - sabre_start
        total_time = time.perf_counter() - start_time

        ops = mapped_qc.count_ops()
        swaps = ops.get("swap", 0)
        return mapped_qc, {
            "total_time": total_time, "preprocessing_time": preprocessing_time,
            "routing_time": routing_time, "swaps": swaps, "bypassed_faq": False,
            "original_depth": circuit.depth(), "mapped_depth": mapped_qc.depth(),
        }

    def compile_fgea_faq_tket(
        self,
        circuit: QuantumCircuit,
        num_physical_qubits: int,
        coupling_map: Union[List[Tuple[int, int]], set],
        error_rates: Optional[Dict[Tuple[int, int], float]] = None,
    ) -> Tuple[QuantumCircuit, Dict]:
        """FGEA Subgraph Extraction → FAQ Layout → PyTKET LexiRoute Routing."""
        start_time = time.perf_counter()
        circuit = decompose_to_basis_gates(circuit)

        prep_start = time.perf_counter()
        mapping, _ = self._get_fgea_faq_layout(circuit, num_physical_qubits, coupling_map, error_rates)
        preprocessing_time = time.perf_counter() - prep_start

        qubit_indices = {q: i for i, q in enumerate(circuit.qubits)}
        clbit_indices = {c: i for i, c in enumerate(circuit.clbits)}
        seeded_circuit = QuantumCircuit(num_physical_qubits, circuit.num_clbits)
        for inst in circuit.data:
            q_args = [seeded_circuit.qubits[mapping[qubit_indices[q]]] for q in inst.qubits]
            c_args = [seeded_circuit.clbits[clbit_indices[c]] for c in inst.clbits]
            seeded_circuit.append(inst.operation, q_args, c_args)

        tk_circ = qiskit_to_tk(seeded_circuit)
        arc = Architecture(list(coupling_map))

        tket_start = time.perf_counter()
        RoutingPass(arc).apply(tk_circ)
        routing_time = time.perf_counter() - tket_start

        mapped_qc = tk_to_qiskit(tk_circ)
        total_time = time.perf_counter() - start_time
        ops = mapped_qc.count_ops()
        swaps = ops.get("swap", 0)
        return mapped_qc, {
            "total_time": total_time, "preprocessing_time": preprocessing_time,
            "routing_time": routing_time, "swaps": swaps, "bypassed_faq": False,
            "original_depth": circuit.depth(), "mapped_depth": mapped_qc.depth(),
        }

    def compile_fgea_faq_qmap(
        self,
        circuit: QuantumCircuit,
        num_physical_qubits: int,
        coupling_map: Union[List[Tuple[int, int]], set],
        error_rates: Optional[Dict[Tuple[int, int], float]] = None,
    ) -> Tuple[QuantumCircuit, Dict]:
        """FGEA Subgraph Extraction → FAQ Layout → MQT QMAP Routing."""
        start_time = time.perf_counter()
        circuit = decompose_to_basis_gates(circuit)

        prep_start = time.perf_counter()
        mapping, _ = self._get_fgea_faq_layout(circuit, num_physical_qubits, coupling_map, error_rates)
        preprocessing_time = time.perf_counter() - prep_start

        qmap_start = time.perf_counter()
        mapped_qc, qmap_results = self.handoff_handler.compile_with_qmap(
            circuit, coupling_map, num_physical_qubits, initial_mapping=mapping
        )
        routing_time = time.perf_counter() - qmap_start
        total_time = time.perf_counter() - start_time

        swaps = getattr(qmap_results.output, "swaps", 0)
        return mapped_qc, {
            "total_time": total_time, "preprocessing_time": preprocessing_time,
            "routing_time": routing_time, "swaps": swaps, "bypassed_faq": False,
            "original_depth": circuit.depth(), "mapped_depth": mapped_qc.depth(),
        }

    def compile_paper_method(
        self,
        circuit: QuantumCircuit,
        num_physical_qubits: int,
        coupling_map: Union[List[Tuple[int, int]], set],
        error_rates: Optional[Dict[Tuple[int, int], float]] = None,
    ) -> Tuple[QuantumCircuit, Dict]:
        """
        Faithful re-implementation of the IEEE QCE 2023 paper method.
        FGEA (fidelity subgraph extraction) + FMA (greedy freq-based mapping) + SABRE (proxy for HRA).
        Reference: 'Towards Fidelity-Optimal Qubit Mapping on NISQ Computers', IEEE QCE 2023 (DOI: 10.1109/QCE57702.2023.10313857)
        """
        start_time = time.perf_counter()
        circuit = decompose_to_basis_gates(circuit)
        N = circuit.num_qubits

        prep_start = time.perf_counter()

        # Step 1: FGEA — extract best-fidelity subgraph of size K = N + buffer
        sub_cm, sub_err, global_to_local, local_to_global = self.fgea_extractor.extract(
            N, num_physical_qubits, list(coupling_map), error_rates
        )
        K = len(local_to_global)

        # Step 2: FMA — greedy frequency-based mapping onto the sub-graph
        local_mapping = self.fma_mapper.map(circuit, sub_cm, K, sub_err)

        # Remap to global physical qubit indices
        mapping = {lq: local_to_global[local_mapping[lq]] for lq in local_mapping if local_mapping[lq] in local_to_global}
        # Fallback for any missing
        used = set(mapping.values())
        free = [p for p in range(num_physical_qubits) if p not in used]
        for lq in range(N):
            if lq not in mapping:
                mapping[lq] = free.pop(0) if free else lq

        preprocessing_time = time.perf_counter() - prep_start

        # Step 3: SABRE routing (proxy for HRA — their proprietary heuristic router)
        initial_layout_list = [mapping.get(i, i) for i in range(N)]
        cm = CouplingMap(couplinglist=list(coupling_map))

        sabre_start = time.perf_counter()
        mapped_qc = transpile(
            circuit,
            coupling_map=cm,
            initial_layout=initial_layout_list,
            layout_method=None,
            routing_method="sabre",
            optimization_level=1,
        )
        routing_time = time.perf_counter() - sabre_start
        total_time = time.perf_counter() - start_time

        ops = mapped_qc.count_ops()
        swaps = ops.get("swap", 0)
        return mapped_qc, {
            "total_time": total_time, "preprocessing_time": preprocessing_time,
            "routing_time": routing_time, "swaps": swaps, "bypassed_faq": False,
            "original_depth": circuit.depth(), "mapped_depth": mapped_qc.depth(),
        }

