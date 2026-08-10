from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import config
from Src.adaptive_milp import solve_adaptive_milp
from Src.data import load_instance
from Src.output import save_solution
from Src.visualize import draw_layouts


def build_settings(problem: str, result_dir: Path, args) -> SimpleNamespace:
    values = {name: value for name, value in vars(config).items() if name.isupper()}
    problem_dir = config.DATA_DIR / problem
    values.update(
        {
            "PROBLEM_NAME": problem,
            "PROBLEM_DIR": problem_dir,
            "LOCATION_FILE": problem_dir / "locations.csv",
            "CONFIGURATION_FILE": problem_dir / "configurations.csv",
            "PRODUCTION_RATE_FILE": problem_dir / "production_rates.csv",
            "DEMAND_FILE": problem_dir / "demands.csv",
            "PARAMETER_FILE": problem_dir / "parameters.csv",
            "SHARED_RESOURCE_FILE": problem_dir / "shared_resources.csv",
            "RESOURCE_REQUIREMENT_FILE": problem_dir / "resource_requirements.csv",
            "RESULT_DIR": result_dir,
            "TIME_LIMIT": args.time_limit,
            "MIP_GAP": args.mip_gap,
            "OUTPUT_FLAG": 0 if args.quiet else 1,
            "USE_SHARED_RESOURCES": args.shared_resources,
            "OPTIMIZE_SHARED_RESOURCE_CAPACITY": False,
            "RELOCATION_COST_PER_DISTANCE": args.relocation_cost_per_distance,
            "RELOCATION_FIXED_COST": args.relocation_fixed_cost,
            "SEED": args.seed,
            "THREADS": args.threads,
            "ONLINE_CAPACITY_TIE_BREAK": getattr(args, "capacity_tie_break", True),
        }
    )
    return SimpleNamespace(**values)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Solve the paper implication MILP with adaptive RMT locations.")
    parser.add_argument("--problem", choices=("single_part", "multi_part"), default="single_part")
    parser.add_argument("--time-limit", type=float, default=300.0)
    parser.add_argument("--mip-gap", type=float, default=0.0)
    parser.add_argument("--relocation-cost-per-distance", type=float, default=1.0)
    parser.add_argument("--relocation-fixed-cost", type=float, default=0.0)
    parser.add_argument("--shared-resources", action="store_true")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--result-dir", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result_dir = args.result_dir or config.BASE_DIR / "Result_adaptive" / args.problem / "paper_adaptive"
    settings = build_settings(args.problem, result_dir, args)
    instance = load_instance(settings)
    solution = solve_adaptive_milp(instance, settings)
    save_solution(solution, result_dir)
    draw_layouts(result_dir, instance)
    print(solution.summary)
    print(solution.cost_breakdown)
    print(f"Result saved to: {result_dir}")


if __name__ == "__main__":
    main()
