"""
Module A: DAG-Aware Interaction Matrix (A) Builder
Calculates the time-decayed two-qubit gate interaction matrix A for logical qubits.
Includes the Deep-Circuit Amnesia Fix (hybrid decay plateau for circuit depth > 100).
"""

import numpy as np
from qiskit import QuantumCircuit
from qiskit.converters import circuit_to_dag


class DAGInteractionMatrixBuilder:
    def __init__(self, gamma: float = 0.9, decay_rate: float = None, amnesia_threshold: int = 100, plateau_length: int = 20):
        """
        Args:
            gamma: Default decay factor (0 < gamma <= 1.0).
            decay_rate: Alias for gamma.
            amnesia_threshold: Circuit depth threshold to activate hybrid decay plateau.
            plateau_length: Number of early layers with flat weight gamma^0 = 1.0 when threshold is exceeded.
        """
        self.gamma = decay_rate if decay_rate is not None else gamma
        self.amnesia_threshold = amnesia_threshold
        self.plateau_length = plateau_length

    def build_matrix_from_dag(self, dag) -> np.ndarray:
        """Builds interaction matrix A directly from a Qiskit DAGCircuit."""
        qubits = list(dag.qubits)
        num_qubits = len(qubits)
        qubit_indices = {q: i for i, q in enumerate(qubits)}
        matrix_a = np.zeros((num_qubits, num_qubits), dtype=float)

        layers = list(dag.layers())
        total_layers = len(layers)
        is_deep = total_layers > self.amnesia_threshold

        for layer_idx, layer in enumerate(layers):
            if is_deep and layer_idx < self.plateau_length:
                decay = 1.0
            else:
                effective_idx = (layer_idx - self.plateau_length) if is_deep else layer_idx
                decay = self.gamma ** effective_idx

            for node in layer["graph"].op_nodes():
                if len(node.qargs) == 2:
                    q1_idx = qubit_indices[node.qargs[0]]
                    q2_idx = qubit_indices[node.qargs[1]]
                    matrix_a[q1_idx, q2_idx] += decay
                    matrix_a[q2_idx, q1_idx] += decay

        return matrix_a

    def build_matrix(self, circuit: QuantumCircuit) -> np.ndarray:
        """
        Builds square matrix A (N_logical x N_logical) where A[i, j] is the total
        time-decayed interaction weight between logical qubits i and j.
        """
        if isinstance(circuit, str):
            if circuit.startswith("OPENQASM") or "\n" in circuit:
                from qiskit.qasm2 import loads as qasm2_loads
                circuit = qasm2_loads(circuit)
            else:
                from qiskit.qasm2 import load as qasm2_load
                circuit = qasm2_load(circuit)

        dag = circuit_to_dag(circuit)
        return self.build_matrix_from_dag(dag)
