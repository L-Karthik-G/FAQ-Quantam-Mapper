"""A6 - Gamma decay sensitivity benchmark runner.

Evaluates the FAQ interaction-decay parameter ``gamma`` in
``DAGInteractionMatrixBuilder(gamma=...)`` (weight = gamma ** DAG-layer) against
downstream routing performance. Fixed mapper configuration throughout: random
multi-start (K=5) + 2-opt, seeds {0..19} reused identically across every gamma
condition (matched blocks). Two router conditions: Qiskit SABRE downstream
(FAQ layout hard-constrained) and PyTKET RoutingPass (FAQ embedded).

Every (cell, gamma, router, seed) run records: swaps, routed depth, total 2q gate
count, prep seconds, and Matrix-A sanity diagnostics (total weight, nonzero count,
min/max nonzero weight, layer count). Raw per-seed rows are kept (not means).

Cells (authorized A6 list, mirrors the A5 cells):
  1. grover10-bris  (IBM FakeBrisbane 127q, grover N=10)
  2. vqe50-grid     (synthetic 8x10 grid 80q, vqe_real_amp N=50)
  3. qram20-bris    (IBM FakeBrisbane 127q, qram holdout N=20)
  4. grover12-bris  (IBM FakeBrisbane 127q, grover N=12)
  5. vqe10-bris     (IBM FakeBrisbane 127q, vqe_real_amp N=10)

Usage:
  smoke:   uv run python benchmarks/benchmark_gamma.py --cells vqe50-grid --gammas 0.7,0.9,1.0 --out benchmarks/results/a6_gamma_smoke_raw.json
  full:    uv run python benchmarks/benchmark_gamma.py --gammas 0.5,0.6,0.7,0.8,0.85,0.9,0.95,0.98,1.0 --out benchmarks/results/a6_gamma_results.json
  slices:  add --slice K/N to run every Nth condition-slice in a separate process, then
           uv run python benchmarks/benchmark_gamma.py --merge N --out benchmarks/results/a6_gamma_results.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, List, Tuple

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
if _BENCH_DIR not in sys.path:
    sys.path.insert(0, _BENCH_DIR)

import numpy as np
from benchmark_eval import (
    SEEDS,
    get_hardware_topology,
    load_benchmark_circuit,
    load_holdout_circuit,
)
from pytket.architecture import Architecture
from pytket.extensions.qiskit import qiskit_to_tk, tk_to_qiskit
from pytket.passes import RoutingPass
from qiskit import QuantumCircuit, transpile
from qiskit.converters import circuit_to_dag
from qiskit.transpiler import CouplingMap

from qap_compiler.module_a_dag import DAGInteractionMatrixBuilder
from qap_compiler.module_b_hardware import HardwareMatrixBuilder
from qap_compiler.module_c_faq import AdaptiveFAQSolver

MAPPER = {"num_starts": 5, "start_mode": "random", "enable_2opt": True}

CELLS = {
    "grover10-bris": ("IBM_Eagle_127_Brisbane", "grover", "mqt", "Grover's Search", 10),
    "vqe50-grid": ("Rigetti_Grid_80", "vqe_real_amp", "mqt", "VQE (RealAmplitudes)", 50),
    "qram20-bris": ("IBM_Eagle_127_Brisbane", "qram_bucket_brigade", "holdout", "QRAM Decoder (Holdout)", 20),
    "grover12-bris": ("IBM_Eagle_127_Brisbane", "grover", "mqt", "Grover's Search", 12),
    "vqe10-bris": ("IBM_Eagle_127_Brisbane", "vqe_real_amp", "mqt", "VQE (RealAmplitudes)", 10),
}


def _load_circuit(bench_key: str, suite: str, n: int) -> QuantumCircuit:
    return load_benchmark_circuit(bench_key, n) if suite == "mqt" else load_holdout_circuit(bench_key, n)


def a_diagnostics(A: np.ndarray) -> Dict:
    nz = A[A > 0]
    return {
        "total_weight": float(np.sum(A)),
        "nonzero_interactions": int(np.count_nonzero(A)),
        "min_nonzero_weight": float(np.min(nz)) if nz.size else 0.0,
        "max_nonzero_weight": float(np.max(nz)) if nz.size else 0.0,
    }


def route(circuit: QuantumCircuit, M: int, coupling_list: List, mapping: Dict,
          router: str, seed: int) -> Tuple[int, int, int]:
    if router == "sabre":
        cm = CouplingMap(coupling_list)
        res = transpile(
            circuit, coupling_map=cm,
            initial_layout=[mapping.get(i, i) for i in range(circuit.num_qubits)],
            layout_method=None, routing_method="sabre",
            seed_transpiler=seed, optimization_level=1,
        )
    elif router == "tket":
        qi = {q: i for i, q in enumerate(circuit.qubits)}
        ci = {c: i for i, c in enumerate(circuit.clbits)}
        seeded = QuantumCircuit(M, circuit.num_clbits)
        for inst in circuit.data:
            qa = [seeded.qubits[mapping[qi[q]]] for q in inst.qubits]
            ca = [seeded.clbits[ci[c]] for c in inst.clbits]
            seeded.append(inst.operation, qa, ca)
        tk_circ = qiskit_to_tk(seeded)
        RoutingPass(Architecture(coupling_list)).apply(tk_circ)
        res = tk_to_qiskit(tk_circ)
    else:
        raise ValueError(router)
    n2q = sum(1 for i in res.data if len(i.qubits) == 2)
    return int(res.count_ops().get("swap", 0)), int(res.depth()), n2q


def run_condition(cell_id: str, gamma: float, router: str, seed: int) -> Dict:
    arch, bench_key, suite, label, n_q = CELLS[cell_id]
    M, coupling_list, errs = get_hardware_topology(arch)
    qc = _load_circuit(bench_key, suite, n_q)
    dag = circuit_to_dag(qc)
    n_layers = len(list(dag.layers()))

    builder = DAGInteractionMatrixBuilder(gamma=gamma)
    A = builder.build_matrix_from_dag(dag)
    adiag = a_diagnostics(A)
    B = HardwareMatrixBuilder(alpha=1.0).build_matrix(M, coupling_list, errs, is_directed=True)

    t0 = time.perf_counter()
    solver = AdaptiveFAQSolver(seed=seed, **MAPPER)
    mapping, cost = solver.solve(A, B)
    prep = time.perf_counter() - t0

    swaps, depth, n2q = route(qc, M, coupling_list, mapping, router, seed)
    return {
        "cell": cell_id, "benchmark": bench_key, "label": label, "qubits": n_q,
        "architecture": arch, "gamma": gamma, "router": router, "seed": seed,
        "swaps": swaps, "depth": depth, "n2q_ops": n2q,
        "prep_time_sec": prep, "qap_cost": float(cost),
        "n_layers": n_layers, "matrix_a": adiag,
        "mapper": MAPPER,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", default=",".join(CELLS))
    ap.add_argument("--gammas", default=None, help="comma list (ignored in --merge mode)")
    ap.add_argument("--routers", default="sabre,tket")
    ap.add_argument("--seeds", default=",".join(str(s) for s in SEEDS))
    ap.add_argument("--out", required=True)
    ap.add_argument("--slice", default=None, help="K/N : run slice K (0-based) of N equal chunks over conditions")
    ap.add_argument("--merge", type=int, default=None,
                    help="N : merge <out>_slice0..N-1.json into <out> instead of running")
    args = ap.parse_args()

    if args.merge is not None:
        base, ext = os.path.splitext(args.out)
        rows, conditions = [], None
        for k in range(args.merge):
            p = f"{base}_slice{k}{ext}"
            with open(p) as f:
                data = json.load(f)
            if conditions is None:
                conditions = data["conditions"]
            rows.extend(data["rows"])
        with open(args.out, "w") as f:
            json.dump({"conditions": conditions, "rows": rows}, f, indent=2)
        print(f"Merged {len(rows)} rows from {args.merge} slices -> {args.out}")
        return

    if not args.gammas:
        ap.error("--gammas is required unless --merge is used")
    cells = [c for c in args.cells.split(",") if c]
    gammas = [float(g) for g in args.gammas.split(",")]
    routers = args.routers.split(",")
    seeds = [int(s) for s in args.seeds.split(",")]

    conds = [(c, g, r, s) for c in cells for g in gammas for r in routers for s in seeds]
    if args.slice:
        k, n = (int(x) for x in args.slice.split("/"))
        conds = conds[k::n]

    rows, t_start = [], time.time()
    for i, (c, g, r, s) in enumerate(conds):
        try:
            row = run_condition(c, g, r, s)
        except Exception as e:  # noqa: BLE001
            row = {"cell": c, "gamma": g, "router": r, "seed": s, "status": "failed",
                   "error": str(e)}
        rows.append(row)
        print(f"[{i + 1}/{len(conds)}] {c} g={g} {r} seed={s} swaps={row.get('swaps')} "
              f"({time.time() - t_start:.0f}s)", flush=True)
    out = args.out
    if args.slice:
        base, ext = os.path.splitext(out)
        out = f"{base}_slice{k}{ext}"
    with open(out, "w") as f:
        json.dump({"conditions": {"cells": cells, "gammas": gammas, "routers": routers,
                                  "seeds": seeds, "mapper": MAPPER},
                   "rows": rows}, f, indent=2)
    print(f"\nSaved {len(rows)} rows -> {out} ({time.time() - t_start:.0f}s)")


if __name__ == "__main__":
    main()
