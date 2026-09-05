"""
Parallel runner for the paired-seed FAQ-Layout benchmark.

Splits the 20 benchmark tasks across worker processes on the available CPU cores
(Python multiprocessing, 'fork' start method so workers inherit the already-imported
libraries instead of re-importing them). Each task is deterministic given its fixed
seeds, so the aggregated result is identical to running the serial
`benchmark_eval.py` -- it just finishes faster by routing several tasks at once.

Output is written next to this file (same filenames as the serial runner):
  benchmark_eval_results.json
  benchmark_eval_raw_seeds.json

Note: this work is CPU-bound (quantum routing + SciPy FAQ); a GPU provides no
speedup and is not used.

Usage:
  uv run python benchmark_eval_parallel.py [workers]
"""
import json
import os
import sys
import time
from multiprocessing import get_context

from benchmark_eval import BENCHMARK_TASKS, SEEDS, run_one_task


def _work(item):
    """Runs one task in a worker process. Must be a module-level function so the
    multiprocessing start method can pickle it."""
    idx, task = item
    record, logs = run_one_task(task)
    return idx, record, logs


def main(workers: int) -> None:
    t0 = time.time()
    print(
        f"=== PARALLEL BENCHMARK ({len(BENCHMARK_TASKS)} tasks, "
        f"K={len(SEEDS)} seeds, workers={workers}) ===",
        flush=True,
    )

    results = [None] * len(BENCHMARK_TASKS)  # slot per original task index
    raw_logs: list = []
    done = 0

    ctx = get_context("fork")
    with ctx.Pool(processes=workers) as pool:
        for idx, record, logs in pool.imap_unordered(
            _work, enumerate(BENCHMARK_TASKS), chunksize=1
        ):
            done += 1
            results[idx] = record
            raw_logs.extend(logs)
            label = BENCHMARK_TASKS[idx][2]
            n = BENCHMARK_TASKS[idx][3]
            print(
                f"[{done}/{len(BENCHMARK_TASKS)}] done {label} N={n} "
                f"({time.time() - t0:.0f}s elapsed)",
                flush=True,
            )

    all_results = [r for r in results if r is not None]

    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(out_dir, "benchmark_eval_results.json")
    raw_path = os.path.join(out_dir, "benchmark_eval_raw_seeds.json")

    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)
    with open(raw_path, "w") as f:
        json.dump(raw_logs, f, indent=2)

    print(
        f"=== COMPLETE in {time.time() - t0:.0f}s -> {out_path} and {raw_path} "
        f"({len(all_results)} records, {len(raw_logs)} raw rows) ===",
        flush=True,
    )


if __name__ == "__main__":
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    main(workers)
