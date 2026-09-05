"""
Qiskit Plugin: Native FAQ-Layout TransformationPass
Allows seamless integration of the FAQ QAP pre-placement engine into standard
Qiskit PassManager pipelines.

Usage:
    from qiskit.transpiler import PassManager, CouplingMap
    from qiskit.transpiler.passes import SabreSwap, FullAncillaAllocation, EnlargeWithAncilla
    from qap_compiler.qiskit_plugin import FAQPlacementPass

    coupling_map = CouplingMap([(0, 1), (1, 2), (2, 3)])
    pm = PassManager([
        FAQPlacementPass(coupling_map, num_starts=5),
        FullAncillaAllocation(coupling_map),
        EnlargeWithAncilla(),
        SabreSwap(coupling_map)
    ])
    transpiled_circuit = pm.run(circuit)
"""

from typing import Dict, List, Optional, Tuple, Union
import numpy as np
from qiskit import QuantumCircuit
from qiskit.transpiler.basepasses import TransformationPass
from qiskit.transpiler.layout import Layout
from qiskit.transpiler import CouplingMap

from qap_compiler.module_a_dag import DAGInteractionMatrixBuilder
from qap_compiler.module_b_hardware import HardwareMatrixBuilder
from qap_compiler.module_c_faq import AdaptiveFAQSolver


class FAQPlacementPass(TransformationPass):
    """
    Qiskit TransformationPass that computes an initial layout via an approximate
    Quadratic Assignment Problem (QAP) pre-placement (SciPy FAQ + 2-opt polish).
    """

    def __init__(
        self,
        coupling_map: Union[CouplingMap, List[Tuple[int, int]]],
        error_rates: Optional[Dict[Tuple[int, int], float]] = None,
        num_starts: int = 5,
        start_mode: str = "gaussian",
        enable_2opt: bool = True,
        time_decay_gamma: float = 0.9,
        seed: int = 42,
    ):
        super().__init__()
        if isinstance(coupling_map, CouplingMap):
            self.coupling_list = list(coupling_map.get_edges())
            self.num_physical_qubits = coupling_map.size()
        else:
            self.coupling_list = list(coupling_map)
            all_nodes = set([u for u, v in self.coupling_list] + [v for u, v in self.coupling_list])
            self.num_physical_qubits = max(all_nodes) + 1 if all_nodes else 0

        self.error_rates = error_rates
        self.num_starts = num_starts
        self.start_mode = start_mode
        self.enable_2opt = enable_2opt
        self.time_decay_gamma = time_decay_gamma
        self.seed = seed

        self.dag_builder = DAGInteractionMatrixBuilder(decay_rate=self.time_decay_gamma)
        self.hw_builder = HardwareMatrixBuilder(alpha=1.0)
        self.faq_solver = AdaptiveFAQSolver(
            num_starts=self.num_starts,
            start_mode=self.start_mode,
            enable_2opt=self.enable_2opt,
            seed=self.seed,
        )

    def run(self, dag):
        """
        Runs the FAQ placement algorithm and sets the initial layout on property_set.
        """
        matrix_a = self.dag_builder.build_matrix_from_dag(dag)
        matrix_b = self.hw_builder.build_matrix(
            self.num_physical_qubits, self.coupling_list, self.error_rates
        )

        mapping, cost = self.faq_solver.solve(matrix_a, matrix_b)

        # Construct Qiskit Layout object
        layout_dict = {}
        qubits = list(dag.qubits)
        for logical_idx, phys_idx in mapping.items():
            if logical_idx < len(qubits):
                layout_dict[qubits[logical_idx]] = phys_idx

        layout = Layout(layout_dict)
        self.property_set["layout"] = layout
        return dag
