from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import config as base_config
from Src.data import load_instance
from Src.milp import solve_milp


DEFAULT_UNIFORM_LEVELS = "3,4,5,6,7,8,9,10,11,12,13,15,20"
DEFAULT_SCALE_LEVELS = "0.25,0.5,0.75,1.0,1.25,1.5,2.0"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run shared resource capacity sensitivity analysis for RMS layout problems."
    )
    parser.add_argument("--problems", nargs="+", default=["single_part", "multi_part"])
    parser.add_argument("--mode", choices=["uniform", "scale"], default="uniform")
    parser.add_argument("--levels", default=None, help="Comma-separated capacity levels or scale factors.")
    parser.add_argument("--time-limit", type=float, default=60.0)
    parser.add_argument("--mip-gap", type=float, default=0.05)
    parser.add_argument("--output-flag", type=int, default=0, choices=[0, 1])
    parser.add_argument("--use-warm-start", action="store_true", help="Apply warm start when problem is multi_part.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("Result/sensitivity/shared_resource_sensitivity.csv"),
    )
    args = parser.parse_args()

    levels = _parse_levels(args.levels or _default_levels(args.mode))
    rows: list[dict[str, object]] = []
    for problem_name in args.problems:
        for level in levels:
            rows.append(run_case(problem_name=problem_name, mode=args.mode, level=level, args=args))
            _write_rows(args.output, rows)

    print(f"Wrote {len(rows)} sensitivity rows to {args.output}")


def run_case(problem_name: str, mode: str, level: float, args) -> dict[str, object]:
    cfg = _make_config(problem_name, args)
    instance = load_instance(cfg)
    base_capacity = dict(instance.shared_resource_capacity)
    instance.shared_resource_capacity = _build_capacity(base_capacity, mode, level)

    row: dict[str, object] = {
        "problem_name": problem_name,
        "mode": mode,
        "level": _clean_number(level),
        "resource_count": len(instance.shared_resource_capacity),
        "total_capacity": sum(instance.shared_resource_capacity.values()),
        "min_capacity": min(instance.shared_resource_capacity.values(), default=0),
        "max_capacity": max(instance.shared_resource_capacity.values(), default=0),
        "time_limit": args.time_limit,
        "mip_gap_target": args.mip_gap,
    }

    try:
        solution = solve_milp(instance, cfg)
    except Exception as exc:
        row.update({"status_name": "ERROR", "error": str(exc)})
        return row

    summary = solution.summary
    costs = solution.cost_breakdown
    usage_metrics = _resource_usage_metrics(solution.resource_usage)
    row.update(
        {
            "status": summary.get("status"),
            "status_name": summary.get("status_name"),
            "objective": summary.get("objective"),
            "runtime_seconds": round(float(summary.get("runtime_seconds", 0.0)), 6)
            if "runtime_seconds" in summary
            else None,
            "mip_gap": round(float(summary.get("mip_gap", 0.0)), 6) if "mip_gap" in summary else None,
            "purchase_cost": costs.get("purchase_cost"),
            "reconfiguration_cost": costs.get("reconfiguration_cost"),
            "material_handling_cost": costs.get("material_handling_cost"),
            "active_machine_count": len(solution.purchased_machines),
            **usage_metrics,
        }
    )
    return row


def _make_config(problem_name: str, args) -> SimpleNamespace:
    cfg = SimpleNamespace(
        **{name: getattr(base_config, name) for name in dir(base_config) if name.isupper()}
    )
    cfg.PROBLEM_NAME = problem_name
    cfg.PROBLEM_DIR = cfg.DATA_DIR / problem_name
    cfg.LOCATION_FILE = cfg.PROBLEM_DIR / "locations.csv"
    cfg.CONFIGURATION_FILE = cfg.PROBLEM_DIR / "configurations.csv"
    cfg.PRODUCTION_RATE_FILE = cfg.PROBLEM_DIR / "production_rates.csv"
    cfg.DEMAND_FILE = cfg.PROBLEM_DIR / "demands.csv"
    cfg.PARAMETER_FILE = cfg.PROBLEM_DIR / "parameters.csv"
    cfg.SHARED_RESOURCE_FILE = cfg.PROBLEM_DIR / "shared_resources.csv"
    cfg.RESOURCE_REQUIREMENT_FILE = cfg.PROBLEM_DIR / "resource_requirements.csv"
    cfg.TIME_LIMIT = args.time_limit
    cfg.MIP_GAP = args.mip_gap
    cfg.OUTPUT_FLAG = args.output_flag
    cfg.USE_SHARED_RESOURCES = True
    cfg.USE_WARM_START = bool(args.use_warm_start and problem_name == "multi_part")
    cfg.WARM_START_DIR = cfg.PROBLEM_DIR / "warm_start_paper"
    return cfg


def _build_capacity(base_capacity: dict[int, int], mode: str, level: float) -> dict[int, int]:
    if mode == "uniform":
        capacity = max(0, int(round(level)))
        return {resource: capacity for resource in sorted(base_capacity)}
    if mode == "scale":
        return {
            resource: max(0, int(math.ceil(capacity * level)))
            for resource, capacity in sorted(base_capacity.items())
        }
    raise ValueError(f"Unknown mode: {mode}")


def _resource_usage_metrics(resource_usage: list[dict]) -> dict[str, object]:
    if not resource_usage:
        return {
            "max_utilization": None,
            "binding_resource_period_count": 0,
            "avg_slack": None,
            "min_slack": None,
        }

    utilizations = []
    slacks = []
    binding_count = 0
    for row in resource_usage:
        capacity = float(row["capacity"])
        usage = float(row["usage"])
        slack = float(row["slack"])
        slacks.append(slack)
        if capacity > 0:
            utilizations.append(usage / capacity)
        if abs(slack) <= 1e-6:
            binding_count += 1

    return {
        "max_utilization": round(max(utilizations), 6) if utilizations else None,
        "binding_resource_period_count": binding_count,
        "avg_slack": round(sum(slacks) / len(slacks), 6),
        "min_slack": round(min(slacks), 6),
    }


def _parse_levels(text: str) -> list[float]:
    return [float(token.strip()) for token in text.split(",") if token.strip()]


def _default_levels(mode: str) -> str:
    return DEFAULT_UNIFORM_LEVELS if mode == "uniform" else DEFAULT_SCALE_LEVELS


def _clean_number(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value


def _write_rows(path: Path, rows: Iterable[dict[str, object]]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
