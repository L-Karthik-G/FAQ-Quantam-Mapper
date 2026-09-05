"""Runs a strided slice of the paired-seed benchmark tasks as a standalone process.

Tasks are indexed 0..19 in BENCHMARK_TASKS order. This process runs every task whose
index satisfies  idx % workers == remainder , so launching `workers` such processes
(with remainders 0..workers-1) covers all 20 tasks once, in parallel on the CPU.

Each process writes its own partial outputs into <repo>/benchmarks/results/:
  partial_results_<remainder>.json
  partial_raw_<remainder>.json
and prints one line per finished task (progress can be tailed).

Usage (launch <workers> processes, one per remainder 0..workers-1):
  uv run python benchmarks/benchmark_eval_strided.py <workers> <remainder>
  # e.g. workers=6 -> launch remainders 0,1,2,3,4,5, then merge the
  # partial_results_<r>.json / partial_raw_<r>.json files in task order.

This is an alternative to benchmark_eval_parallel.py (a multiprocessing Pool) that is more
robust in sandboxed environments that restrict subprocess creation from within a Pool.
"""
import json
import os
import sys
import time

from benchmark_eval import BENCHMARK_TASKS, run_one_task


def main() -> None:
    workers = int(sys.argv[1])
    remainder = int(sys.argv[2])
    t0 = time.time()
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out_dir, exist_ok=True)

    results = []
    logs = []
    for idx in range(remainder, len(BENCHMARK_TASKS), workers):
        task = BENCHMARK_TASKS[idx]
        record, task_logs = run_one_task(task)
        if record is not None:
            results.append((idx, record))
        logs.extend(task_logs)
        label = task[2]
        n = task[3]
        print(
            f"[slice {workers}/{remainder}] task {idx} {label} N={n} done "
            f"({time.time() - t0:.0f}s elapsed, {len(logs)} raw rows so far)",
            flush=True,
        )

    res_path = os.path.join(out_dir, f"partial_results_{remainder}.json")
    raw_path = os.path.join(out_dir, f"partial_raw_{remainder}.json")
    with open(res_path, "w") as f:
        json.dump(results, f, indent=2)
    with open(raw_path, "w") as f:
        json.dump(logs, f, indent=2)
    print(
        f"[slice {workers}/{remainder}] COMPLETE in {time.time() - t0:.0f}s -> "
        f"{res_path}, {raw_path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
