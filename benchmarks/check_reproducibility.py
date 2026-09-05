"""CI reproducibility check for derived benchmark artifacts.

Re-runs the deterministic analysis steps that are cheap enough for CI and diffs their output
against the committed JSON, failing the build if they drift. Covers:

  * QAP-cost ablation (`benchmark_ablations.py`) -> benchmark_ablation_results.json
  * Paired significance + BH FDR (`analyze_significance.py`) -> significance_results.json

Both are deterministic given pinned dependencies (uv.lock) and the committed canonical
per-seed log, so an exact/tolerance-matched diff is the intended contract. The heavy routing
re-run (`benchmark_fidelity.py`) is *not* run here — it takes tens of minutes and belongs in a
manual `workflow_dispatch` job (see .github/workflows/ci.yml).

The comparison is structural with a numeric tolerance (default 1e-9) so it is robust to
platform-level floating-point jitter while still catching real result drift.

Usage (from repo root):
    uv run python benchmarks/check_reproducibility.py --baseline /tmp/x.json --output benchmarks/results/x.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

TOL = 1e-9


def _as_float_or_none(v: Any):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def diff_nodes(base: Any, out: Any, path: str, tol: float) -> list:
    """Recursively compare two JSON structures; return a list of mismatch strings."""
    mism = []
    if isinstance(base, dict):
        if not isinstance(out, dict):
            return [f"{path}: dict vs {type(out).__name__}"]
        for k in base:
            mism += diff_nodes(base[k], out.get(k), f"{path}.{k}", tol)
        for k in out:
            if k not in base:
                mism.append(f"{path}.{k}: extra key not in baseline")
    elif isinstance(base, list):
        if not isinstance(out, list):
            return [f"{path}: list vs {type(out).__name__}"]
        if len(base) != len(out):
            mism.append(f"{path}: len {len(base)} vs {len(out)}")
        for i, (a, b) in enumerate(zip(base, out)):
            mism += diff_nodes(a, b, f"{path}[{i}]", tol)
    else:
        bf, of = _as_float_or_none(base), _as_float_or_none(out)
        if bf is not None and of is not None and base != out:
            if abs(bf - of) > tol * max(1.0, abs(bf)):
                mism.append(f"{path}: {base!r} vs {out!r}")
        elif base != out:
            mism.append(f"{path}: {base!r} vs {out!r}")
    return mism


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, help="committed/reference JSON path")
    parser.add_argument("--output", required=True, help="regenerated JSON path")
    parser.add_argument("--tol", type=float, default=TOL)
    args = parser.parse_args()

    with open(args.baseline) as f:
        base = json.load(f)
    with open(args.output) as f:
        out = json.load(f)

    mism = diff_nodes(base, out, "root", args.tol)
    if mism:
        print(f"REPRODUCIBILITY MISMATCH ({len(mism)} diffs) between {args.baseline} and {args.output}")
        for m in mism[:40]:
            print("  -", m)
        sys.exit(1)
    print(f"OK: {os.path.basename(args.output)} matches {os.path.basename(args.baseline)}")


if __name__ == "__main__":
    main()
