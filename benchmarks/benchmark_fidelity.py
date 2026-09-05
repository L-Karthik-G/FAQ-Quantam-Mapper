"""Fidelity-aware re-run of the paired-seed FAQ-Layout benchmark.

Re-implements the routing in `benchmark_eval.py` but, instead of discarding the routed
circuit, **captures it** so that an estimated fidelity-loss proxy can be computed for every
(seed, method) compilation. This is needed because the committed
`benchmark_eval_raw_seeds.json` stores only SWAP counts/times, not the routed circuits; a
faithful fidelity proxy (multiplying real per-edge 2Q error rates from the calibration
snapshot through the final routed circuit) therefore requires a deterministic re-transpile.

Fidelity proxy
--------------
For the final routed circuit on the physical device, each 2-qubit gate that executes on a
physical link contributes its measured CNOT error rate from the same calibration snapshot used
to build the QAP matrix B (`FakeBrisbane` for IBM; the recorded synthetic profile for the
synthetic grid topology).
A routed `swap` is not native to the basis and is counted as 3 CNOT-equivalent error terms on
its physical link (standard SWAP=3-CX decomposition). We report:

  * `infidelity_sum`   = sum over 2Q interactions of -ln(1 - error)   (additive loss proxy)
  * `failure_prob`     = 1 - product(1 - error) over 2Q interactions  (single-circuit failure proxy)

Everything is deterministic for a fixed seed, so re-running reproduces the exact same SWAP
counts as the committed canonical dataset. Every produced SWAP value is cross-checked against
`benchmark_eval_raw_seeds.json`; any mismatch is reported (it would indicate the re-run diverged
and its fidelity numbers are unreliable).

Strided execution
-----------------
This file is a strided driver like `benchmark_eval_strided.py`: launch several processes, each
handling tasks whose index satisfies `idx % workers == remainder`:

    uv run python benchmarks/benchmark_fidelity.py <workers> <remainder>

Each process writes <repo>/benchmarks/results/fidelity_partial_<remainder>.json. Then run
`uv run python benchmarks/benchmark_fidelity.py --merge <workers>` to combine the partial
slices (in task order) into `benchmark_fidelity_raw.json` + `benchmark_fidelity_results.json`.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

# Ensure the repository root is importable regardless of the working directory.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from pytket.architecture import Architecture
from pytket.extensions.qiskit import qiskit_to_tk, tk_to_qiskit
from pytket.passes import PlacementPass, RoutingPass
from pytket.placement import GraphPlacement
from qiskit import QuantumCircuit, transpile
from qiskit.transpiler import CouplingMap

from benchmarks.benchmark_eval import (
    BENCHMARK_TASKS,
    SEEDS,
    get_hardware_topology,
    load_benchmark_circuit,
    load_holdout_circuit,
)
from qap_compiler.module_a_dag import DAGInteractionMatrixBuilder
from qap_compiler.module_b_hardware import HardwareMatrixBuilder
from qap_compiler.module_c_faq import AdaptiveFAQSolver

DEFAULT_ERR = 0.012  # fallback per-edge 2Q error if not present in snapshot


# --- Routed-circuit producers (mirror benchmark_eval's compile logic, but keep `res`) ------
def _route_sabre(qc: QuantumCircuit, M: int, edges: List, seed: int,
                 initial_layout: Optional[List[int]] = None):
    cm = CouplingMap(edges)
    kwargs = {}
    if initial_layout is not None:
        kwargs = {"initial_layout": initial_layout, "layout_method": None}
    else:
        kwargs = {"layout_method": "sabre"}
    res = transpile(qc, coupling_map=cm, routing_method="sabre",
                    seed_transpiler=seed, optimization_level=1, **kwargs)
    return res


def _route_tket(qc: QuantumCircuit, M: int, edges: List,
                layout: Optional[Dict[int, int]] = None):
    arc = Architecture(edges)
    if layout is None:
        tk_circ = qiskit_to_tk(qc)
        PlacementPass(GraphPlacement(arc)).apply(tk_circ)
    else:
        qi = {q: i for i, q in enumerate(qc.qubits)}
        ci = {c: i for i, c in enumerate(qc.clbits)}
        seeded = QuantumCircuit(M, qc.num_clbits)
        for inst in qc.data:
            qa = [seeded.qubits[layout[qi[q]]] for q in inst.qubits]
            ca = [seeded.clbits[ci[c]] for c in inst.clbits]
            seeded.append(inst.operation, qa, ca)
        tk_circ = qiskit_to_tk(seeded)
    RoutingPass(arc).apply(tk_circ)
    return tk_to_qiskit(tk_circ)


def _faq_layout(qc: QuantumCircuit, M: int, edges: List, errs: Dict, seed: int):
    dag = DAGInteractionMatrixBuilder(gamma=0.9)
    hw = HardwareMatrixBuilder(alpha=1.0)
    faq = AdaptiveFAQSolver(num_starts=5, start_mode="gaussian", enable_2opt=True, seed=seed)
    A = dag.build_matrix(qc)
    B = hw.build_matrix(M, edges, errs, is_directed=True)
    mapping, cost = faq.solve(A, B)
    return mapping, cost


def compute_fidelity_proxy(res: QuantumCircuit, errs: Dict,
                           default: float = DEFAULT_ERR) -> Dict:
    """Walk the final routed circuit; return additive-infidelity and failure-prob proxies."""
    inf_sum = 0.0
    failure_prob = 1.0
    n_2q = 0
    n_default = 0
    for inst in res.data:
        if len(inst.qubits) != 2:
            continue
        name = inst.operation.name
        if name not in ("cx", "swap"):
            continue
        idx = [res.find_bit(q).index for q in inst.qubits]
        e = errs.get((idx[0], idx[1]), errs.get((idx[1], idx[0])))
        if e is None:
            e = default
            n_default += 1
        mult = 3 if name == "swap" else 1
        n_2q += 1
        for _ in range(mult):
            inf_sum += -math.log1p(-e)
            failure_prob *= (1.0 - e)
    return {
        "infidelity_sum": float(inf_sum),
        "failure_prob": float(1.0 - failure_prob),
        "n_2q_ops": n_2q,
        "n_2q_default_error": n_default,
    }


def run_one_task(task: Tuple) -> Optional[Tuple[int, Dict, List[Dict]]]:
    """Runs one task across all seeds/methods capturing routed circuits + fidelity proxy.

    Mirrors benchmark_eval.run_one_task in the arms it exercises (no QMAP), so the SWAP
    numbers must equal the committed canonical dataset exactly.
    """
    idx, arch_name, bench_key, bench_label, n_q, suite_type = task
    M, edges, errs = get_hardware_topology(arch_name)

    try:
        if suite_type == "mqt":
            qc = load_benchmark_circuit(bench_key, n_q)
        else:
            qc = load_holdout_circuit(bench_key, n_q)
    except Exception as e:  # pragma: no cover - mirrors serial runner skip behaviour
        print(f"[SKIP] {bench_key} N={n_q}: {e}", flush=True)
        return None

    arms = ["sabre_def", "faq_sabre", "tket_def", "faq_tket"]
    per_seed = []

    for seed in SEEDS:
        row = {"task": bench_label, "qubits": n_q, "arch": arch_name,
               "seed": seed, "num_physical_qubits": M}
        # SABRE default
        res = _route_sabre(qc, M, edges, seed)
        row["sabre_def"] = {"swaps": res.count_ops().get("swap", 0),
                            **compute_fidelity_proxy(res, errs)}
        # FAQ + SABRE
        mapping, cost = _faq_layout(qc, M, edges, errs, seed)
        res = _route_sabre(qc, M, edges, seed, initial_layout=[mapping.get(i, i) for i in range(qc.num_qubits)])
        row["faq_sabre"] = {"swaps": res.count_ops().get("swap", 0),
                            **compute_fidelity_proxy(res, errs), "qap_cost": float(cost)}
        # PyTKET default
        res = _route_tket(qc, M, edges)
        row["tket_def"] = {"swaps": res.count_ops().get("swap", 0),
                           **compute_fidelity_proxy(res, errs)}
        # FAQ + PyTKET
        res = _route_tket(qc, M, edges, layout=mapping)
        row["faq_tket"] = {"swaps": res.count_ops().get("swap", 0),
                           **compute_fidelity_proxy(res, errs)}
        per_seed.append(row)

    return idx, {"task": bench_label, "qubits": n_q, "architecture": arch_name,
                 "benchmark": bench_key, "suite_type": suite_type,
                 "num_physical_qubits": M, "seeds": per_seed}, arms


def cross_check(records: List[Dict], canonical_path: str) -> Dict:
    """Compare every captured SWAP against the committed raw-seed dataset."""
    if not os.path.exists(canonical_path):
        return {"checked": False, "reason": "canonical raw file not found"}
    with open(canonical_path) as f:
        raw = json.load(f)
    exp = {(r["task"], r["qubits"], r["arch"], r["seed"], r["method"]): r["swaps"]
           for r in raw}
    mism = 0
    total = 0
    samples = []
    for rec in records:
        for sr in rec["seeds"]:
            for meth in ("sabre_def", "faq_sabre", "tket_def", "faq_tket"):
                total += 1
                got = sr[meth]["swaps"]
                want = exp.get((sr["task"], sr["qubits"], sr["arch"], sr["seed"], meth))
                if want is None or got != want:
                    mism += 1
                    if len(samples) < 10:
                        samples.append({"task": sr["task"], "qubits": sr["qubits"],
                                        "arch": sr["arch"], "seed": sr["seed"],
                                        "method": meth, "got": got, "expected": want})
    return {"checked": True, "n_checked": total, "n_divergent": mism, "samples": samples}


def _merge_partials(workers: int, out_dir: str):
    """Merge fidelity_partial_<r>.json slices (workers of them) in task order."""
    recs_by_idx = {}
    for r in range(workers):
        p = os.path.join(out_dir, f"fidelity_partial_{r}.json")
        if not os.path.exists(p):
            print(f"[merge] missing {p}")
            continue
        with open(p) as f:
            for item in json.load(f):
                recs_by_idx[item[0]] = item[1]
    records = [recs_by_idx[i] for i in sorted(recs_by_idx)]
    return records


def main_slice() -> None:
    workers = int(sys.argv[1])
    remainder = int(sys.argv[2])
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()
    results = []
    for idx in range(remainder, len(BENCHMARK_TASKS), workers):
        task = (idx,) + BENCHMARK_TASKS[idx]
        out = run_one_task(task)
        if out is not None:
            results.append((out[0], out[1]))
            print(f"[{workers}/{remainder}] task {idx} {out[1]['task']} N={out[1]['qubits']} "
                  f"done ({time.time()-t0:.0f}s)", flush=True)
    out_p = os.path.join(out_dir, f"fidelity_partial_{remainder}.json")
    with open(out_p, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[slice {workers}/{remainder}] COMPLETE -> {out_p}", flush=True)


def main_merge(workers: int) -> None:
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    records = _merge_partials(workers, out_dir)
    canonical = os.path.join(out_dir, "benchmark_eval_raw_seeds.json")
    check = cross_check(records, canonical)

    all_per_seed = []
    for rec in records:
        all_per_seed.extend(rec["seeds"])
    raw_path = os.path.join(out_dir, "benchmark_fidelity_raw.json")
    with open(raw_path, "w") as f:
        json.dump(all_per_seed, f, indent=2)

    with open(os.path.join(out_dir, "benchmark_fidelity_crosscheck.json"), "w") as f:
        json.dump(check, f, indent=2)

    # summary
    summary = []
    for rec in records:
        s = {"task": rec["task"], "qubits": rec["qubits"], "architecture": rec["architecture"]}
        for meth in ("sabre_def", "faq_sabre", "tket_def", "faq_tket"):
            swaps = np.array([sr[meth]["swaps"] for sr in rec["seeds"]])
            inf = np.array([sr[meth]["infidelity_sum"] for sr in rec["seeds"]])
            fp = np.array([sr[meth]["failure_prob"] for sr in rec["seeds"]])
            s[meth] = {
                "mean_swaps": float(np.mean(swaps)),
                "mean_infidelity_sum": float(np.mean(inf)),
                "mean_failure_prob": float(np.mean(fp)),
            }
        summary.append(s)
    with open(os.path.join(out_dir, "benchmark_fidelity_results.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(check))
    print(f"\nMerged {len(records)} records -> {raw_path}, "
          f"{os.path.join(out_dir, 'benchmark_fidelity_results.json')}")
    if check.get("checked"):
        print(f"Cross-check: {check['n_divergent']}/{check['n_checked']} SWAP values diverged "
              f"from canonical dataset.")


if __name__ == "__main__":
    if sys.argv[1] == "--merge":
        main_merge(int(sys.argv[2]))
    else:
        main_slice()
