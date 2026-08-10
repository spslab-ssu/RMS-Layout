from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import config
from run_adaptive import build_settings
from Src.adaptive_milp import solve_adaptive_milp
from Src.data import load_instance
from Src.network_adaptive import solve_network_adaptive_milp
from Src.output import save_solution
from Src.visualize import draw_layouts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare paper+adaptive and network+adaptive formulations.")
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
    root = args.result_dir or config.BASE_DIR / "Result_adaptive_comparison" / args.problem
    settings = build_settings(args.problem, root, args)
    instance = load_instance(settings)

    formulations = (
        ("paper_adaptive", solve_adaptive_milp),
        ("network_adaptive", solve_network_adaptive_milp),
    )
    rows = []
    for name, solver in formulations:
        solution = solver(instance, settings)
        result_dir = root / name
        save_solution(solution, result_dir)
        draw_layouts(result_dir, instance)
        size = solution.summary.get("model_size", {})
        costs = solution.cost_breakdown
        rows.append(
            {
                "formulation": name,
                "status": solution.summary.get("status_name"),
                "objective": solution.summary.get("objective"),
                "best_bound": solution.summary.get("lower_bound"),
                "mip_gap": solution.summary.get("mip_gap"),
                "runtime_seconds": solution.summary.get("runtime_seconds"),
                "nodes": solution.summary.get("node_count"),
                "variables": size.get("variables"),
                "binary_variables": size.get("binary_variables"),
                "constraints": size.get("constraints"),
                "purchase_cost": costs.get("purchase_cost"),
                "reconfiguration_cost": costs.get("reconfiguration_cost"),
                "relocation_cost": costs.get("relocation_cost"),
                "material_handling_cost": costs.get("material_handling_cost"),
                "relocation_count": solution.summary.get("relocation_count"),
                "reconfiguration_count": solution.summary.get("reconfiguration_count"),
            }
        )

    root.mkdir(parents=True, exist_ok=True)
    (root / "adaptive_formulation_comparison.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (root / "adaptive_formulation_comparison.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    print(f"Comparison saved to: {root}")


if __name__ == "__main__":
    main()
