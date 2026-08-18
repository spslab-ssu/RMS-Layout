from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import config
from Src.data import load_instance
from Src.milp import solve_milp
from Src.strengthening import PROFILE_FAMILIES


REFERENCE = {
    "single_part": {"paper_reported": 23082.0, "best_known": 22910.0},
    "multi_part": {"paper_reported": 36006.0, "best_known": 35775.0},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reproduce network-reformulation bounds.")
    parser.add_argument(
        "--problem",
        action="append",
        choices=tuple(REFERENCE),
        help="Repeat to select multiple problems; default: both.",
    )
    parser.add_argument("--run-mip", action="store_true", help="Also solve each integer model.")
    parser.add_argument("--time-limit", type=float, default=100.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=config.BASE_DIR / "results" / "benchmarks" / "paper_reformulation.csv",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    problems = args.problem or list(REFERENCE)
    rows = []
    for problem in problems:
        reference = REFERENCE[problem]
        for profile in PROFILE_FAMILIES:
            lp = _solve(problem, profile, args.time_limit, lp_relaxation=True)
            lp_bound = float(lp.summary["objective"])
            row = {
                "problem": problem,
                "profile": profile,
                "paper_reported_objective": reference["paper_reported"],
                "best_known_objective": reference["best_known"],
                "pure_lp_bound": round(lp_bound, 6),
                "pure_lp_gap_percent": round(
                    100.0 * (reference["best_known"] - lp_bound) / reference["best_known"],
                    6,
                ),
                "cuts_generated": lp.summary["strengthening"]["generated"],
                "cuts_added": lp.summary["strengthening"]["added"],
                "cuts_pruned": lp.summary["strengthening"]["pruned"],
                "lp_runtime_seconds": round(float(lp.summary["runtime_seconds"]), 6),
                "mip_objective": "",
                "mip_bound": "",
                "mip_gap": "",
                "mip_status": "",
                "mip_runtime_seconds": "",
            }
            if args.run_mip:
                mip = _solve(problem, profile, args.time_limit, lp_relaxation=False)
                row.update(
                    {
                        "mip_objective": mip.summary.get("objective", ""),
                        "mip_bound": mip.summary.get("lower_bound", ""),
                        "mip_gap": mip.summary.get("mip_gap", ""),
                        "mip_status": mip.summary["status_name"],
                        "mip_runtime_seconds": round(
                            float(mip.summary["runtime_seconds"]), 6
                        ),
                    }
                )
            rows.append(row)
            print(row)

    _write_results(rows, args.output)
    print(f"Benchmark saved to: {args.output}")


def _solve(problem: str, profile: str, time_limit: float, lp_relaxation: bool):
    settings = config.build_config(
        problem_name=problem,
        profile=profile,
        TIME_LIMIT=time_limit,
        MIP_GAP=0.0,
        OUTPUT_FLAG=0,
        LP_RELAXATION=lp_relaxation,
        USE_SHARED_RESOURCES=False,
        OPTIMIZE_SHARED_RESOURCE_CAPACITY=False,
    )
    return solve_milp(load_instance(settings), settings)


def _write_results(rows: list[dict], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    output.with_suffix(".json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
