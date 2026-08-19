"""Run one controlled multi-part relocation sensitivity case."""

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
    parser.add_argument("--cap", default="unbounded")
    parser.add_argument("--fixed-cost", type=float, default=0.0)
    parser.add_argument("--distance-cost", type=float, default=0.0)
    parser.add_argument("--time-limit", type=float, default=300.0)
    parser.add_argument("--secondary-seconds", type=float, default=0.0)
    parser.add_argument("--provisional-secondary", action="store_true")
    parser.add_argument("--mip-start-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cap = None if args.cap == "unbounded" else int(args.cap)
    settings = config.build_config(
        problem_name="multi_part",
        profile="network_mir",
        TIME_LIMIT=args.time_limit,
        MIP_GAP=0.0,
        OUTPUT_FLAG=0,
        SEED=1,
        THREADS=0,
        USE_SHARED_RESOURCES=False,
        ENABLE_RELOCATION=True,
        MAX_TOTAL_RELOCATIONS=cap,
        RELOCATION_FIXED_COST=args.fixed_cost,
        RELOCATION_DISTANCE_COST=args.distance_cost,
        RELOCATION_DOWNTIME_FRACTION=0.0,
        RELOCATION_CREW_CAPACITY=None,
        RELOCATION_CONGESTION_COST_STEP=0.0,
        MINIMIZE_RELOCATIONS_SECONDARY=args.secondary_seconds > 0,
        ALLOW_PROVISIONAL_RELOCATION_AFTER_TIME_LIMIT=args.provisional_secondary,
        RELOCATION_SECONDARY_RESERVED_SECONDS=args.secondary_seconds,
        STAGE_ONE_CONFIGURATION_LIMIT=1,
        MIP_START_DIR=args.mip_start_dir,
        result_dir=args.output_dir,
    )
    solution = solve_milp(load_instance(settings), settings)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    save_solution(solution, args.output_dir / "solution")
    costs = solution.cost_breakdown
    base_cost = sum(
        float(costs.get(name, 0.0))
        for name in ("purchase_cost", "reconfiguration_cost", "material_handling_cost")
    )
    primary = solution.summary.get("primary_stage") or {}
    distance = sum(float(row["distance"]) for row in solution.relocations)
    result = {
        "problem": "multi_part/layout_22/table_1/demand_1",
        "cap": "unbounded" if cap is None else cap,
        "fixed_cost": args.fixed_cost,
        "distance_cost": args.distance_cost,
        "time_limit_seconds": args.time_limit,
        "status": solution.summary.get("status_name"),
        "primary_status": primary.get("status_name"),
        "lexicographic_optimal": solution.summary.get("lexicographic_optimal"),
        "base_system_cost": base_cost,
        "relocation_cost": float(costs.get("relocation_cost", 0.0)),
        "total_objective": float(costs.get("total_objective", 0.0)),
        "best_bound": primary.get("best_bound"),
        "mip_gap": primary.get("mip_gap"),
        "relocation_count": solution.summary.get("relocation_count"),
        "relocation_distance": distance,
        "primary_runtime_seconds": primary.get("runtime_seconds"),
        "total_runtime_seconds": solution.summary.get("runtime_seconds"),
    }
    (args.output_dir / "case_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
