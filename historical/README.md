# Historical (superseded) experiments

These files are archived from earlier experiment rounds of the FAQ-Layout project. They are
**not** part of the canonical, reproducible paired-seed dataset reported in the README, and
they are mutually inconsistent with it and with each other (they used different seeds,
topologies, and `optimization_level` settings — e.g. K=5 with `optimization_level=3`, a
115-qubit Heavy-Hex profile, MQT-QMAP/FGEA/paper-method comparisons).

## The canonical dataset (kept in the repo root)

| File | Produced by | Contents |
|:---|:---|:---|
| `../benchmark_eval_results.json` | `../benchmark_eval.py` | Per-task/method mean SWAPs, 95% CI, success (K=20 paired seeds) |
| `../benchmark_eval_raw_seeds.json` | `../benchmark_eval.py` | Raw per-seed logs (all 20 seeds × all methods) |
| `../benchmark_ablation_results.json` | `../benchmark_ablations.py` | QAP-cost ablation table |

Always report numbers from those files (as shown in the README Tables 1–2 and the ablation
table). Files in this directory are kept only for provenance/history.

## What each archived file was

| File | Was |
|:---|:---|
| `benchmark_suite.py`, `benchmark_fgea_results.json`, `benchmark_fgea_summary.md` | 10-method round (Defaults / FAQ / FAQ+FGEA / IEEE-QCE-2023 paper method), K=5 |
| `run_benchmark_2.py`, `benchmark_2_results.json` | Round-2 benchmark (K=5, 95% CI) |
| `benchmark_rigorous.py`, `benchmark_rigorous_results.json` | "Rigorous" round (115q Heavy-Hex profile) |
| `benchmark_new_circuits.py`, `benchmark_new_circuits_results.json` | New-circuit holdout round |
| `benchmark_tket_all.py`, `benchmark_tket_all_results.json` | TKET-focused sweep |
| `benchmark_results.json`, `benchmark_statistical_results.json`, `benchmark_summary.md` | Earlier statistical rounds (K=5, `optimization_level=3`) |
| `qft_scaling_study.py`, `qft_scaling_results.json` | QFT depth-scaling mini-study |

To reproduce the canonical results run `../benchmark_ablations.py` and `../benchmark_eval.py`
from the repository root (see the README).
