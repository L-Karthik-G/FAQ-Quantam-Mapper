"""
Module A: DAG-Aware Interaction Matrix (A) Builder
Calculates the time-decayed two-qubit gate interaction matrix A for logical qubits.
Includes the Deep-Circuit Amnesia Fix (hybrid decay plateau for circuit depth > 100).
"""

import numpy as np
from qiskit import QuantumCircuit
from qiskit.converters import circuit_to_dag


class DAGInteractionMatrixBuilder:
    def __init__(self, gamma: float = 0.9, amnesia_threshold: int = 100, plateau_length: int = 20):
        """
        Args:
            gamma: Default decay factor (0 < gamma <= 1.0).
            amnesia_threshold: Circuit depth threshold to activate hybrid decay plateau.
            plateau_length: Number of early layers with flat weight gamma^0 = 1.0 when threshold is exceeded.
        """
        self.gamma = gamma
        self.amnesia_threshold = amnesia_threshold
        self.plateau_length = plateau_length

    def build_matrix(self, circuit: QuantumCircuit) -> np.ndarray:
        """
        Builds square matrix A (N_logical x N_logical) where A[i, j] is the total
        time-decayed interaction weight between logical qubits i and j.
        """
        if isinstance(circuit, str):
            # Parse OpenQASM string or file if string passed
            if circuit.startswith("OPENQASM") or "\n" in circuit:
                from qiskit.qasm2 import loads as qasm2_loads
                circuit = qasm2_loads(circuit)
            else:
                from qiskit.qasm2 import load as qasm2_load
                circuit = qasm2_load(circuit)

        num_qubits = circuit.num_qubits
        qubit_indices = {q: i for i, q in enumerate(circuit.qubits)}
        matrix_a = np.zeros((num_qubits, num_qubits), dtype=float)

        dag = circuit_to_dag(circuit)
        total_depth = dag.depth()
        use_hybrid_decay = total_depth > self.amnesia_threshold

        two_qubit_layer_idx = 0

        for layer in dag.layers():
            graph = layer["graph"]
            op_nodes = graph.op_nodes()
            has_two_qubit_gate = False

            for node in op_nodes:
                if len(node.qargs) == 2:
                    has_two_qubit_gate = True
                    q1_idx = qubit_indices[node.qargs[0]]
                    q2_idx = qubit_indices[node.qargs[1]]

                    # Calculate decay weight
                    if use_hybrid_decay:
                        if two_qubit_layer_idx < self.plateau_length:
                            weight = 1.0
                        else:
                            decay_exp = two_qubit_layer_idx - self.plateau_length
                            weight = self.gamma ** decay_exp
                    else:
                        weight = self.gamma ** two_qubit_layer_idx

                    matrix_a[q1_idx, q2_idx] += weight
                    matrix_a[q2_idx, q1_idx] += weight

            if has_two_qubit_gate:
                two_qubit_layer_idx += 1

        return matrix_a
