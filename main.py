from __future__ import annotations

import argparse
from pathlib import Path

import config
from Src.data import load_instance
from Src.milp import solve_milp
from Src.output import save_solution
from Src.strengthening import PROFILE_FAMILIES
from Src.visualize import draw_layouts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Solve the RMS lifecycle-network model.")
    parser.add_argument("--problem", choices=("single_part", "multi_part"), default=config.PROBLEM_NAME)
    parser.add_argument("--profile", choices=tuple(PROFILE_FAMILIES), default=config.STRENGTHENING_PROFILE)
    parser.add_argument("--time-limit", type=float, default=float(config.TIME_LIMIT))
    parser.add_argument("--mip-gap", type=float, default=float(config.MIP_GAP))
    parser.add_argument("--shared-resources", action="store_true")
    parser.add_argument("--relocation", action="store_true")
    parser.add_argument("--relocation-distance-cost", type=float, default=config.RELOCATION_DISTANCE_COST)
    parser.add_argument("--relocation-fixed-cost", type=float, default=config.RELOCATION_FIXED_COST)
    parser.add_argument("--relocation-downtime", type=float, default=config.RELOCATION_DOWNTIME_FRACTION)
    parser.add_argument("--relocation-crew-capacity", type=int)
    parser.add_argument("--forbid-reverse-swaps", action="store_true")
    parser.add_argument(
        "--no-secondary-relocation",
        action="store_true",
        help="Skip stage 2 that minimizes moves at the stage-1 system cost.",
    )
    parser.add_argument("--relocation-congestion-step", type=float, default=config.RELOCATION_CONGESTION_COST_STEP)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--result-dir", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = config.build_config(
        problem_name=args.problem,
        profile=args.profile,
        result_dir=args.result_dir,
        TIME_LIMIT=args.time_limit,
        MIP_GAP=args.mip_gap,
        USE_SHARED_RESOURCES=args.shared_resources,
        ENABLE_RELOCATION=args.relocation,
        RELOCATION_DISTANCE_COST=args.relocation_distance_cost,
        RELOCATION_FIXED_COST=args.relocation_fixed_cost,
        RELOCATION_DOWNTIME_FRACTION=args.relocation_downtime,
        RELOCATION_CREW_CAPACITY=args.relocation_crew_capacity,
        FORBID_REVERSE_SWAPS=args.forbid_reverse_swaps,
        MINIMIZE_RELOCATIONS_SECONDARY=not args.no_secondary_relocation,
        RELOCATION_CONGESTION_COST_STEP=args.relocation_congestion_step,
        OUTPUT_FLAG=0 if args.quiet else 1,
    )
    instance = load_instance(settings)
    solution = solve_milp(instance, settings)
    save_solution(solution, settings.RESULT_DIR)
    if not solution.summary.get("lp_relaxation", False):
        draw_layouts(settings.RESULT_DIR, instance)
    print(solution.summary)
    print(solution.cost_breakdown)
    print(f"Result saved to: {settings.RESULT_DIR}")


if __name__ == "__main__":
    main()
