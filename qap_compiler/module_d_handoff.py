"""
Module D: QMAP Warm-Start Handoff & Safeguards
Handles threshold switch safeguard (N < 10 bypass) and converts FAQ layout
permutations into soft-constraint heuristic seeds for MQT QMAP.
"""

from typing import Dict, List, Optional, Tuple, Union
import mqt.core as core
from mqt.qmap import sc
from qiskit import QuantumCircuit
import qiskit.qasm3


class QMAPWarmStartHandoff:
    def __init__(self, threshold_qubits: int = 10):
        """
        Args:
            threshold_qubits: If N < threshold_qubits, bypass FAQ optimization and use default layout.
        """
        self.threshold_qubits = threshold_qubits

    def should_bypass(self, num_logical_qubits: int) -> bool:
        """Returns True if circuit size N is below the threshold switch."""
        return num_logical_qubits < self.threshold_qubits

    def embed_initial_layout(self, circuit: QuantumCircuit, mapping: Dict[int, int], num_physical_qubits: int) -> QuantumCircuit:
        """
        Embeds a logical QuantumCircuit (N qubits) onto a physical register (M qubits)
        according to the initial layout mapping {logical_idx: physical_idx}.
        """
        N = circuit.num_qubits
        M = num_physical_qubits

        qubit_indices = {q: i for i, q in enumerate(circuit.qubits)}
        clbit_indices = {c: i for i, c in enumerate(circuit.clbits)}
        seeded_circuit = QuantumCircuit(M, circuit.num_clbits)

        for inst in circuit.data:
            q_args = [seeded_circuit.qubits[mapping[qubit_indices[q]]] for q in inst.qubits]
            c_args = [seeded_circuit.clbits[clbit_indices[c]] for c in inst.clbits]
            seeded_circuit.append(inst.operation, q_args, c_args)

        return seeded_circuit

    def compile_with_qmap(
        self,
        circuit: QuantumCircuit,
        coupling_map: Union[List[Tuple[int, int]], set],
        num_physical_qubits: int,
        initial_mapping: Optional[Dict[int, int]] = None,
        method: str = "heuristic",
    ) -> Tuple[QuantumCircuit, sc.MappingResults]:
        """
        Handoffs circuit (with optional FAQ initial layout seed) to MQT QMAP router.

        Returns:
            mapped_circuit: Post-routing Qiskit QuantumCircuit.
            results: MQT QMAP MappingResults metadata.
        """
        # If mapping is provided, embed circuit onto physical qubits first
        if initial_mapping is not None:
            comp_circuit = self.embed_initial_layout(circuit, initial_mapping, num_physical_qubits)
        else:
            comp_circuit = circuit

        comp = core.load(comp_circuit)
        cm_set = set(coupling_map)
        arch = sc.Architecture(num_physical_qubits, cm_set)

        config = sc.Configuration()
        if method == "heuristic":
            config.method = sc.Method.heuristic
        elif method == "exact":
            config.method = sc.Method.exact

        mapped_comp, results = sc.map_(comp, arch, config)

        # Convert mapped QuantumComputation back to Qiskit QuantumCircuit
        qasm_str = mapped_comp.qasm3_str()
        mapped_qc = qiskit.qasm3.loads(qasm_str)

        return mapped_qc, results
