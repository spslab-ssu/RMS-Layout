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
SCENARIOS = ("off", "fixed", "variable")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run shared resource experiments (mode comparison or capacity sweep) for RMS layout."
    )
    parser.add_argument("--problems", nargs="+", default=["single_part", "multi_part"])
    parser.add_argument(
        "--compare-modes",
        action="store_true",
        help="off/fixed/variable 세 시나리오를 problem마다 한 번씩 실행해 비교표를 만든다.",
    )
    parser.add_argument(
        "--resource-mode",
        choices=SCENARIOS,
        default="fixed",
        help="capacity sweep에 사용할 shared resource 모드 (compare-modes가 아닐 때만 의미 있음).",
    )
    parser.add_argument(
        "--mode",
        choices=["uniform", "scale"],
        default="uniform",
        help="capacity level 생성 방식 (fixed sweep 전용).",
    )
    parser.add_argument("--levels", default=None, help="Comma-separated capacity levels or scale factors.")
    parser.add_argument("--time-limit", type=float, default=60.0)
    parser.add_argument("--mip-gap", type=float, default=0.0)
    parser.add_argument("--output-flag", type=int, default=1, choices=[0, 1],
                        help="1이면 Gurobi 진행 로그를 콘솔에 표시(기본), 0이면 끔.")
    parser.add_argument("--use-warm-start", action="store_true", help="Apply warm start when problem is multi_part.")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    if args.compare_modes:
        output = args.output or Path("Result/sensitivity/shared_resource_modes.csv")
        rows: list[dict[str, object]] = []
        for problem_name in args.problems:
            for scenario in SCENARIOS:
                rows.append(run_scenario(problem_name=problem_name, resource_mode=scenario, args=args))
                _write_rows(output, rows)
        print(f"Wrote {len(rows)} scenario rows to {output}")
        return

    output = args.output or Path("Result/sensitivity/shared_resource_sensitivity.csv")
    levels = _parse_levels(args.levels or _default_levels(args.mode))
    rows = []
    for problem_name in args.problems:
        for level in levels:
            rows.append(run_case(problem_name=problem_name, level_mode=args.mode, level=level, args=args))
            _write_rows(output, rows)
    print(f"Wrote {len(rows)} sensitivity rows to {output}")


def run_scenario(problem_name: str, resource_mode: str, args) -> dict[str, object]:
    """off/fixed/variable 한 시나리오를 CSV 기본 capacity 그대로 한 번 실행한다."""
    cfg = _make_config(problem_name, resource_mode, args)
    instance = load_instance(cfg)

    row: dict[str, object] = {
        "problem_name": problem_name,
        "scenario": resource_mode,
        "resource_count": len(instance.shared_resource_capacity),
        "input_total_capacity": sum(instance.shared_resource_capacity.values()),
        "time_limit": args.time_limit,
        "mip_gap_target": args.mip_gap,
    }
    try:
        solution = solve_milp(instance, cfg)
    except Exception as exc:  # noqa: BLE001
        row.update({"status_name": "ERROR", "error": str(exc)})
        return row
    row.update(_result_metrics(solution))
    return row


def run_case(problem_name: str, level_mode: str, level: float, args) -> dict[str, object]:
    """fixed 모드에서 capacity level을 바꿔가며 실행하는 기존 민감도 스윕."""
    cfg = _make_config(problem_name, "fixed", args)
    instance = load_instance(cfg)
    base_capacity = dict(instance.shared_resource_capacity)
    instance.shared_resource_capacity = _build_capacity(base_capacity, level_mode, level)

    row: dict[str, object] = {
        "problem_name": problem_name,
        "scenario": "fixed",
        "level_mode": level_mode,
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
    except Exception as exc:  # noqa: BLE001
        row.update({"status_name": "ERROR", "error": str(exc)})
        return row

    row.update(_result_metrics(solution))
    row.update(_resource_usage_metrics(solution.resource_usage))
    return row


def _make_config(problem_name: str, resource_mode: str, args) -> SimpleNamespace:
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
    cfg.SHARED_RESOURCE_MODE = resource_mode
    cfg.USE_SHARED_RESOURCES = resource_mode != "off"
    cfg.COMPUTE_LP_RELAXATION_BOUND = True
    cfg.USE_WARM_START = bool(args.use_warm_start and problem_name == "multi_part")
    cfg.WARM_START_DIR = cfg.PROBLEM_DIR / "warm_start_paper"
    return cfg


def _result_metrics(solution) -> dict[str, object]:
    """세 시나리오 공통 지표(비용/LP bound/gap/시간/변수 수/사이징)를 뽑는다."""
    summary = solution.summary
    costs = solution.cost_breakdown
    objective = summary.get("objective")
    lp_bound = summary.get("lp_relaxation_bound")
    gap_to_lp = None
    if isinstance(objective, (int, float)) and isinstance(lp_bound, (int, float)) and objective:
        gap_to_lp = round((objective - lp_bound) / objective, 6)
    mip_gap = summary.get("mip_gap")
    runtime = summary.get("runtime_seconds")
    return {
        "status": summary.get("status"),
        "status_name": summary.get("status_name"),
        "objective": objective,
        "lp_relaxation_bound": lp_bound,
        "gap_to_lp": gap_to_lp,
        "mip_gap": round(float(mip_gap), 6) if mip_gap is not None else None,
        "runtime_seconds": round(float(runtime), 6) if runtime is not None else None,
        "lp_relaxation_seconds": summary.get("lp_relaxation_seconds"),
        "num_vars": summary.get("num_vars"),
        "num_constraints": summary.get("num_constraints"),
        "num_binary_vars": summary.get("num_binary_vars"),
        "num_integer_vars": summary.get("num_integer_vars"),
        "num_cap_vars": summary.get("num_cap_vars", 0),
        "purchase_cost": costs.get("purchase_cost"),
        "reconfiguration_cost": costs.get("reconfiguration_cost"),
        "material_handling_cost": costs.get("material_handling_cost"),
        "total_sizing": summary.get("total_sizing"),
        "active_machine_count": len(solution.purchased_machines),
    }


def _build_capacity(base_capacity: dict[int, int], mode: str, level: float) -> dict[int, int]:
    if mode == "uniform":
        capacity = max(0, int(round(level)))
        return {resource: capacity for resource in sorted(base_capacity)}
    if mode == "scale":
        return {
            resource: max(0, int(math.ceil(capacity * level)))
            for resource, capacity in sorted(base_capacity.items())
        }
    raise ValueError(f"Unknown level mode: {mode}")


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
