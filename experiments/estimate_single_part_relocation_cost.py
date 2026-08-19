"""Estimate single-part relocation-cost breakpoints from exact Pareto solves."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import config
from Src.data import load_instance
from Src.milp import solve_milp


OUTPUT_DIR = Path("results/single_part_relocation_cost_estimation")
COUNT_CAPS = [0, 1, 2, 3, 4, 6, None]
FIXED_COSTS = [0, 4, 8, 12, 15, 15.9, 16, 16.1, 17, 20, 25, 40]
DISTANCE_COSTS = [0, 1, 2, 3, 3.9, 4, 4.1, 5, 8, 10]


def solve_case(*, cap: int | None, fixed_cost: float, distance_cost: float) -> dict:
    settings = config.build_config(
        problem_name="single_part",
        profile="network_mir",
        TIME_LIMIT=300,
        MIP_GAP=0.0,
        OUTPUT_FLAG=0,
        SEED=1,
        THREADS=0,
        USE_SHARED_RESOURCES=False,
        ENABLE_RELOCATION=True,
        MAX_TOTAL_RELOCATIONS=cap,
        RELOCATION_FIXED_COST=fixed_cost,
        RELOCATION_DISTANCE_COST=distance_cost,
        RELOCATION_DOWNTIME_FRACTION=0.0,
        RELOCATION_CREW_CAPACITY=None,
        RELOCATION_CONGESTION_COST_STEP=0.0,
        MINIMIZE_RELOCATIONS_SECONDARY=True,
        ALLOW_PROVISIONAL_RELOCATION_AFTER_TIME_LIMIT=False,
        RELOCATION_SECONDARY_RESERVED_SECONDS=60,
        STAGE_ONE_CONFIGURATION_LIMIT=1,
    )
    solution = solve_milp(load_instance(settings), settings)
    costs = solution.cost_breakdown
    base_cost = sum(
        float(costs.get(name, 0.0))
        for name in ("purchase_cost", "reconfiguration_cost", "material_handling_cost")
    )
    distance = sum(float(row["distance"]) for row in solution.relocations)
    row = {
        "cap": "unbounded" if cap is None else cap,
        "fixed_cost": fixed_cost,
        "distance_cost": distance_cost,
        "status": solution.summary.get("status_name"),
        "lexicographic_optimal": solution.summary.get("lexicographic_optimal"),
        "base_system_cost": base_cost,
        "relocation_cost": float(costs.get("relocation_cost", 0.0)),
        "total_objective": float(costs.get("total_objective", 0.0)),
        "relocation_count": solution.summary.get("relocation_count"),
        "relocation_distance": distance,
        "primary_runtime_seconds": (solution.summary.get("primary_stage") or {}).get(
            "runtime_seconds"
        ),
        "total_runtime_seconds": solution.summary.get("runtime_seconds"),
    }
    print(json.dumps(row, ensure_ascii=False), flush=True)
    return row


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    count_rows = [solve_case(cap=cap, fixed_cost=0.0, distance_cost=0.0) for cap in COUNT_CAPS]
    unconstrained_cost = count_rows[-1]["base_system_cost"]
    saturated = [
        row
        for row in count_rows[:-1]
        if row["status"] == "OPTIMAL"
        and abs(row["base_system_cost"] - unconstrained_cost) <= 1e-6
    ]
    if not saturated:
        raise RuntimeError("No finite relocation cap reached the unconstrained optimum")
    saturation_cap = min(int(row["cap"]) for row in saturated)

    fixed_rows = [
        solve_case(cap=saturation_cap, fixed_cost=value, distance_cost=0.0)
        for value in FIXED_COSTS
    ]
    distance_rows = [
        solve_case(cap=saturation_cap, fixed_cost=0.0, distance_cost=value)
        for value in DISTANCE_COSTS
    ]
    write_csv(OUTPUT_DIR / "count_cap_frontier.csv", count_rows)
    write_csv(OUTPUT_DIR / "fixed_cost_sensitivity.csv", fixed_rows)
    write_csv(OUTPUT_DIR / "distance_cost_sensitivity.csv", distance_rows)
    summary = {
        "problem": "single_part/layout_18/table_1/demand_1",
        "saturation_cap": saturation_cap,
        "unconstrained_base_system_cost": unconstrained_cost,
        "count_cap_frontier": count_rows,
        "fixed_cost_sensitivity": fixed_rows,
        "distance_cost_sensitivity": distance_rows,
    }
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
