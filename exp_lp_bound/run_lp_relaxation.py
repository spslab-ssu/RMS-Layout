"""Run only the initial LP relaxation for generated RMS instances.

Unlike exp/run_experiments.py, this runner never solves the MIP and never
creates visualization files. Results are appended to one summary.csv so the
four formulations can be compared on exactly the same instances.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config as default_config
from Src.data.loader import load_instance
from Src.models import base, base_adaptive, network, network_adaptive
from exp.run_experiments import _config_for

MODELS = {
    "base": base.solve_milp,
    "base_adaptive": base_adaptive.solve_milp,
    "network": network.solve_milp,
    "network_adaptive": network_adaptive.solve_milp,
}


def append_row(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row), extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run initial LP relaxation only")
    parser.add_argument("--manifest", type=Path, default=ROOT / "Data/demands/exp/manifest.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "Result/lp_relaxation")
    parser.add_argument("--part", action="append", type=int, choices=(1, 3, 5, 7), dest="parts")
    parser.add_argument("--layout", action="append", choices=("layout_18", "layout_22", "layout_27", "layout_32", "layout_37"))
    parser.add_argument("--overlap", action="append", choices=("high", "low", "random"))
    parser.add_argument("--utilization", action="append", choices=("0.5", "0.75", "1.0", "1.25"))
    parser.add_argument("--period-count", action="append", type=int, choices=(2, 4, 6))
    parser.add_argument("--seed", action="append", type=int, choices=(1, 2, 3, 4, 5))
    parser.add_argument("--model", action="append", choices=tuple(MODELS))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--time-limit", type=float, default=300.0,
                        help="LP relaxation time limit per run")
    parser.add_argument("--output-flag", type=int, default=0)
    args = parser.parse_args()
    args.network_warm_start = False
    args.mip_gap = 0.0

    manifest = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    rows = list(csv.DictReader(manifest.open(newline="", encoding="utf-8-sig")))
    rows = [r for r in rows if not args.parts or int(r["part_count"]) in args.parts]
    rows = [r for r in rows if not args.layout or r["layout_name"] in args.layout]
    rows = [r for r in rows if not args.overlap or r.get("overlap") in args.overlap]
    rows = [r for r in rows if not args.utilization or r.get("utilization") in args.utilization]
    rows = [r for r in rows if not args.period_count or int(r.get("period_count", 0)) in args.period_count]
    rows = [r for r in rows if not args.seed or int(r["seed"]) in args.seed]
    if args.limit is not None:
        rows = rows[:args.limit]
    selected = tuple(args.model or MODELS)
    print(f"LP-only instances={len(rows)} models={','.join(selected)}", flush=True)

    out = args.output if args.output.is_absolute() else ROOT / args.output
    summary_path = out / "summary.csv"
    for row in rows:
        for model_name in selected:
            result_dir = out / f"p{row['part_count']}" / row["experiment_id"] / row["layout_name"] / model_name
            result_dir.mkdir(parents=True, exist_ok=True)
            cfg = _config_for(row, model_name, result_dir, args)
            cfg.COMPUTE_LP_RELAXATION_BOUND = True
            cfg.LP_ONLY = True
            started = time.perf_counter()
            try:
                instance = load_instance(cfg)
                solution = MODELS[model_name](instance, cfg)
                record = dict(solution.summary)
                record["error"] = ""
            except Exception as exc:  # keep the batch moving and make failures inspectable
                record = {
                    "status": "ERROR",
                    "status_name": "ERROR",
                    "lp_relaxation_bound": None,
                    "error": repr(exc),
                }
            record.update({
                "experiment_id": row["experiment_id"],
                "part_count": row["part_count"],
                "overlap": row["overlap"],
                "utilization": row["utilization"],
                "seed": row["seed"],
                "layout_name": row["layout_name"],
                "model": model_name,
                "lp_run_wall_seconds": round(time.perf_counter() - started, 6),
            })
            append_row(summary_path, record)
            print(
                f"DONE {row['experiment_id']} {row['layout_name']} {model_name} "
                f"lp_bound={record.get('lp_relaxation_bound')} "
                f"wall={record.get('lp_run_wall_seconds')}s",
                flush=True,
            )


if __name__ == "__main__":
    main()
