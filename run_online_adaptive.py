from __future__ import annotations

import argparse
from pathlib import Path

import config
from run_adaptive import build_settings
from Src.data import load_instance
from Src.online_adaptive import solve_online_adaptive
from Src.output import save_solution
from Src.visualize import draw_layouts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reveal single-part demand period by period and run the online adaptive policy."
    )
    parser.add_argument("--problem", choices=("single_part",), default="single_part")
    parser.add_argument("--time-limit", type=float, default=120.0, help="Time limit for each period solve.")
    parser.add_argument("--mip-gap", type=float, default=0.0)
    parser.add_argument("--relocation-cost-per-distance", type=float, default=1.0)
    parser.add_argument("--relocation-fixed-cost", type=float, default=0.0)
    parser.add_argument("--shared-resources", action="store_true")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument(
        "--no-capacity-tie-break",
        action="store_false",
        dest="capacity_tie_break",
        help="Disable the equal-cost secondary objective that maximizes installed capacity.",
    )
    parser.set_defaults(capacity_tie_break=True)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--result-dir", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result_dir = args.result_dir or config.BASE_DIR / "Result_online_adaptive" / args.problem
    settings = build_settings(args.problem, result_dir, args)
    instance = load_instance(settings)

    solution = solve_online_adaptive(
        instance,
        settings,
        on_reveal=lambda period, demand: print(
            f"Period {period} demand revealed: {demand:g}"
        ),
    )
    save_solution(solution, result_dir)
    draw_layouts(result_dir, instance)
    print(solution.summary)
    print(solution.cost_breakdown)
    print(f"Result saved to: {result_dir}")


if __name__ == "__main__":
    main()
