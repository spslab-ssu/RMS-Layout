"""Run the current yh relocation formulation under a fixed benchmark protocol."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import config
from Src.data import load_instance
from Src.milp import solve_milp
from Src.output import save_solution


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--problem", choices=("single_part", "multi_part"), default="multi_part")
    parser.add_argument("--time-limit", type=float, default=300.0)
    parser.add_argument("--secondary-seconds", type=float, default=0.0)
    parser.add_argument("--provisional-secondary", action="store_true")
    parser.add_argument("--relocation-cost", type=float, default=0.0)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    common = dict(
        problem_name=args.problem,
        profile="network_mir",
        ENABLE_RELOCATION=True,
        RELOCATION_DISTANCE_COST=args.relocation_cost,
        RELOCATION_FIXED_COST=0.0,
        RELOCATION_DOWNTIME_FRACTION=0.0,
        RELOCATION_CREW_CAPACITY=None,
        FORBID_REVERSE_SWAPS=False,
        RELOCATION_CONGESTION_COST_STEP=0.0,
        USE_SHARED_RESOURCES=False,
        TIME_LIMIT=args.time_limit,
        MIP_GAP=0.0,
        SEED=1,
        THREADS=0,
        OUTPUT_FLAG=0,
        STAGE_ONE_CONFIGURATION_LIMIT=1,
        RELOCATION_SECONDARY_RESERVED_SECONDS=args.secondary_seconds,
        ALLOW_PROVISIONAL_RELOCATION_AFTER_TIME_LIMIT=args.provisional_secondary,
    )

    lp_settings = config.build_config(
        **common,
        LP_RELAXATION=True,
        MINIMIZE_RELOCATIONS_SECONDARY=False,
        result_dir=args.output_dir / "lp",
    )
    lp_solution = solve_milp(load_instance(lp_settings), lp_settings)

    mip_settings = config.build_config(
        **common,
        LP_RELAXATION=False,
        MINIMIZE_RELOCATIONS_SECONDARY=True,
        result_dir=args.output_dir / "mip",
    )
    instance = load_instance(mip_settings)
    mip_solution = solve_milp(instance, mip_settings)
    save_solution(mip_solution, args.output_dir / "mip")

    primary = mip_solution.summary.get("primary_stage") or {}
    result = {
        "branch": "yh_worktree",
        "problem": args.problem,
        "model": "network_mir_relocation_lexicographic",
        "time_limit_seconds": args.time_limit,
        "secondary_reserved_seconds": args.secondary_seconds,
        "provisional_secondary_enabled": args.provisional_secondary,
        "relocation_distance_cost": args.relocation_cost,
        "pure_lp_status": lp_solution.summary.get("status_name"),
        "pure_lp_bound": lp_solution.summary.get("objective"),
        "pure_lp_runtime_seconds": lp_solution.summary.get("runtime_seconds"),
        "mip_status": mip_solution.summary.get("status_name"),
        "primary_status": primary.get("status_name"),
        "primary_objective": primary.get("objective"),
        "mip_best_bound": primary.get("best_bound"),
        "mip_gap": primary.get("mip_gap"),
        "primary_runtime_seconds": primary.get("runtime_seconds"),
        "relocation_stage": mip_solution.summary.get("relocation_stage"),
        "provisional_relocation_stage": mip_solution.summary.get(
            "provisional_relocation_stage"
        ),
        "lexicographic_optimal": mip_solution.summary.get("lexicographic_optimal"),
        "total_runtime_seconds": mip_solution.summary.get("runtime_seconds"),
        "relocation_count": mip_solution.summary.get("relocation_count"),
        "best_relocation_count": mip_solution.summary.get("best_relocation_count"),
        "minimum_relocation_count": mip_solution.summary.get("minimum_relocation_count"),
        "total_relocation_distance": sum(float(row["distance"]) for row in mip_solution.relocations),
        "reconfiguration_count": len(mip_solution.reconfigurations),
        "binary_variables": mip_solution.summary["model_size"]["binary_variables"],
        "total_variables": mip_solution.summary["model_size"]["variables"],
        "constraints": mip_solution.summary["model_size"]["constraints"],
        "cost_breakdown": mip_solution.cost_breakdown,
    }
    if result["primary_objective"] is not None and result["pure_lp_bound"] is not None:
        result["lp_gap_vs_incumbent_percent"] = 100.0 * (
            float(result["primary_objective"]) - float(result["pure_lp_bound"])
        ) / float(result["primary_objective"])
    (args.output_dir / "benchmark_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
