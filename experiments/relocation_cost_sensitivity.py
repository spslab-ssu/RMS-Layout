from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import config as base_config
from Src.data.loader import load_instance
from Src.models.milp_network import solve_milp as solve_network
from Src.models.network_adaptive import solve_milp


DEFAULT_LEVELS = "0,1,2,3,4,5,6,7,8,9,10,12,14,16,18,20,25,30,50,100"
DEFAULT_LOCATION_BY_PROBLEM = {
    "single_part": "layout_18",
    "multi_part": "layout_22",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run relocation cost sensitivity analysis for the adaptive network model."
    )
    parser.add_argument("--problems", nargs="+", default=["single_part", "multi_part"])
    parser.add_argument("--levels", default=DEFAULT_LEVELS, help="Comma-separated relocation distance costs.")
    parser.add_argument("--fixed-cost", type=float, default=0.0)
    parser.add_argument("--location-name", default="auto", help="'auto' uses layout_18 for single and layout_22 for multi.")
    parser.add_argument("--rmt-table-name", default="table_1")
    parser.add_argument("--demand-name", default="demand_1")
    parser.add_argument("--time-limit", type=float, default=60.0)
    parser.add_argument("--mip-gap", type=float, default=0.05)
    parser.add_argument("--output-flag", type=int, default=0, choices=[0, 1])
    parser.add_argument("--binary-arcs", action="store_true", default=True)
    parser.add_argument("--continuous-arcs", action="store_false", dest="binary_arcs")
    parser.add_argument("--compute-lp-bound", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("Result/sensitivity/relocation_cost_sensitivity.csv"),
    )
    args = parser.parse_args()

    levels = _parse_levels(args.levels)
    rows: list[dict[str, object]] = []
    for problem_name in args.problems:
        baseline = run_baseline(problem_name=problem_name, args=args)
        rows.append(baseline)
        _write_rows(args.output, rows)
        print(
            f"{problem_name} baseline_network "
            f"status={baseline.get('status_name')} obj={baseline.get('objective')}",
            flush=True,
        )
        for level in levels:
            row = run_case(
                problem_name=problem_name,
                relocation_distance_cost=level,
                args=args,
                baseline=baseline,
            )
            rows.append(row)
            _write_rows(args.output, rows)
            print(
                f"{problem_name} gamma={_clean_number(level)} "
                f"status={row.get('status_name')} obj={row.get('objective')} "
                f"relocations={row.get('relocation_count')} "
                f"improvement={row.get('objective_improvement')}",
                flush=True,
            )

    print(f"Wrote {len(rows)} sensitivity rows to {args.output}")


def run_baseline(problem_name: str, args) -> dict[str, object]:
    cfg = _make_config(problem_name, relocation_distance_cost=0.0, args=args)
    row: dict[str, object] = {
        "model_type": "network",
        "problem_name": problem_name,
        "location_name": cfg.LOCATION_NAME,
        "rmt_table_name": cfg.RMT_TABLE_NAME,
        "demand_name": cfg.DEMAND_NAME,
        "relocation_cost_per_distance": None,
        "relocation_fixed_cost": None,
        "time_limit": args.time_limit,
        "mip_gap_target": args.mip_gap,
        "network_binary_arcs": bool(args.binary_arcs),
        "is_baseline": True,
    }

    try:
        instance = load_instance(cfg)
        solution = solve_network(instance, cfg)
    except Exception as exc:
        row.update({"status_name": "ERROR", "error": str(exc)})
        return row

    _add_solution_metrics(row, solution)
    row.update(
        {
            "baseline_objective": row.get("objective"),
            "baseline_material_handling_cost": row.get("material_handling_cost"),
            "baseline_purchase_cost": row.get("purchase_cost"),
            "baseline_reconfiguration_cost": row.get("reconfiguration_cost"),
            "objective_improvement": 0.0,
            "objective_improvement_pct": 0.0,
            "mhc_improvement": 0.0,
            "mhc_improvement_pct": 0.0,
            "net_saving_after_relocation": 0.0,
        }
    )
    return row


def run_case(problem_name: str, relocation_distance_cost: float, args, baseline: dict[str, object]) -> dict[str, object]:
    cfg = _make_config(problem_name, relocation_distance_cost, args)
    row: dict[str, object] = {
        "model_type": "network_adaptive",
        "problem_name": problem_name,
        "location_name": cfg.LOCATION_NAME,
        "rmt_table_name": cfg.RMT_TABLE_NAME,
        "demand_name": cfg.DEMAND_NAME,
        "relocation_cost_per_distance": _clean_number(relocation_distance_cost),
        "relocation_fixed_cost": _clean_number(args.fixed_cost),
        "time_limit": args.time_limit,
        "mip_gap_target": args.mip_gap,
        "network_binary_arcs": bool(args.binary_arcs),
        "is_baseline": False,
    }

    try:
        instance = load_instance(cfg)
        solution = solve_milp(instance, cfg)
    except Exception as exc:
        row.update({"status_name": "ERROR", "error": str(exc)})
        return row

    _add_solution_metrics(row, solution)
    _add_baseline_comparison(row, baseline)
    return row


def _add_solution_metrics(row: dict[str, object], solution) -> None:
    summary = solution.summary
    costs = solution.cost_breakdown
    relocation_metrics = _relocation_metrics(solution.reconfigurations)
    row.update(
        {
            "status": summary.get("status"),
            "status_name": summary.get("status_name"),
            "objective": summary.get("objective"),
            "best_bound": summary.get("best_bound"),
            "best_bound_c": summary.get("best_bound_c"),
            "lp_relaxation_bound": summary.get("lp_relaxation_bound"),
            "mip_gap": _round_or_none(summary.get("mip_gap")),
            "runtime_seconds": _round_or_none(summary.get("runtime_seconds")),
            "num_vars": summary.get("num_vars"),
            "num_constraints": summary.get("num_constraints"),
            "node_count": summary.get("node_count"),
            "purchase_cost": costs.get("purchase_cost"),
            "reconfiguration_cost": costs.get("reconfiguration_cost"),
            "relocation_cost": costs.get("relocation_cost"),
            "material_handling_cost": costs.get("material_handling_cost"),
            "total_objective": costs.get("total_objective"),
            "active_machine_count": len(solution.purchased_machines),
            "state_count": len(solution.machine_states),
            "material_flow_count": len(solution.material_flows),
            **relocation_metrics,
        }
    )


def _add_baseline_comparison(row: dict[str, object], baseline: dict[str, object]) -> None:
    baseline_objective = _as_float_or_none(baseline.get("objective"))
    adaptive_objective = _as_float_or_none(row.get("objective"))
    baseline_mhc = _as_float_or_none(baseline.get("material_handling_cost"))
    adaptive_mhc = _as_float_or_none(row.get("material_handling_cost"))
    relocation_cost = _as_float_or_none(row.get("relocation_cost")) or 0.0

    row["baseline_objective"] = baseline_objective
    row["baseline_material_handling_cost"] = baseline_mhc
    row["baseline_purchase_cost"] = baseline.get("purchase_cost")
    row["baseline_reconfiguration_cost"] = baseline.get("reconfiguration_cost")

    if baseline_objective is not None and adaptive_objective is not None:
        improvement = baseline_objective - adaptive_objective
        row["objective_improvement"] = round(improvement, 6)
        row["objective_improvement_pct"] = round(improvement / baseline_objective * 100, 6) if baseline_objective else None
    else:
        row["objective_improvement"] = None
        row["objective_improvement_pct"] = None

    if baseline_mhc is not None and adaptive_mhc is not None:
        mhc_improvement = baseline_mhc - adaptive_mhc
        row["mhc_improvement"] = round(mhc_improvement, 6)
        row["mhc_improvement_pct"] = round(mhc_improvement / baseline_mhc * 100, 6) if baseline_mhc else None
        row["net_saving_after_relocation"] = round(mhc_improvement - relocation_cost, 6)
    else:
        row["mhc_improvement"] = None
        row["mhc_improvement_pct"] = None
        row["net_saving_after_relocation"] = None


def _make_config(problem_name: str, relocation_distance_cost: float, args) -> SimpleNamespace:
    cfg = SimpleNamespace(
        **{name: getattr(base_config, name) for name in dir(base_config) if name.isupper()}
    )
    cfg.PROBLEM_TYPE = problem_name
    cfg.PROBLEM_NAME = problem_name
    cfg.LOCATION_NAME = _location_name(problem_name, args.location_name)
    cfg.RMT_TABLE_NAME = args.rmt_table_name
    cfg.DEMAND_NAME = args.demand_name
    cfg.PARAMETER_NAME = problem_name

    cfg.LOCATION_FILE = cfg.LOCATION_DIR / f"{cfg.LOCATION_NAME}.csv"
    cfg.CONFIGURATION_FILE = cfg.RMT_TABLE_DIR / cfg.RMT_TABLE_NAME / "configurations.csv"
    cfg.PRODUCTION_RATE_FILE = cfg.RMT_TABLE_DIR / cfg.RMT_TABLE_NAME / "production_rates.csv"
    cfg.DEMAND_FILE = cfg.DEMAND_DIR / problem_name / f"{cfg.DEMAND_NAME}.csv"
    cfg.PARAMETER_FILE = cfg.PARAMETER_DIR / f"{cfg.PARAMETER_NAME}.csv"
    cfg.RESOURCE_REQUIREMENT_FILE = cfg.RMT_TABLE_DIR / cfg.RMT_TABLE_NAME / "resource_requirements.csv"
    cfg.RESULT_DIR = cfg.BASE_DIR / "Result" / problem_name / cfg.RMT_TABLE_NAME / cfg.DEMAND_NAME

    cfg.TIME_LIMIT = args.time_limit
    cfg.MIP_GAP = args.mip_gap
    cfg.OUTPUT_FLAG = args.output_flag
    cfg.USE_WARM_START = False
    cfg.COMPUTE_LP_RELAXATION_BOUND = bool(args.compute_lp_bound)
    cfg.NETWORK_BINARY_ARCS = bool(args.binary_arcs)
    cfg.RELOCATION_COST_PER_DISTANCE = relocation_distance_cost
    cfg.RELOCATION_FIXED_COST = args.fixed_cost
    return cfg


def _location_name(problem_name: str, location_name: str) -> str:
    if location_name != "auto":
        return location_name
    try:
        return DEFAULT_LOCATION_BY_PROBLEM[problem_name]
    except KeyError as exc:
        raise ValueError(f"No default location is defined for problem {problem_name!r}") from exc


def _relocation_metrics(reconfigurations: list[dict]) -> dict[str, object]:
    relocation_rows = [
        row for row in reconfigurations if float(row.get("relocation_cost", 0.0)) > 1e-6
    ]
    relocation_distances = [float(row.get("relocation_distance", 0.0)) for row in relocation_rows]
    reconfiguration_only_rows = [
        row for row in reconfigurations if float(row.get("reconfiguration_cost", 0.0)) > 1e-6
    ]
    relocation_costs = [float(row.get("relocation_cost", 0.0)) for row in relocation_rows]
    return {
        "relocation_count": len(relocation_rows),
        "reconfiguration_event_count": len(reconfiguration_only_rows),
        "layout_change_event_count": len(reconfigurations),
        "total_relocation_distance": round(sum(relocation_distances), 6),
        "avg_relocation_distance": round(sum(relocation_distances) / len(relocation_distances), 6)
        if relocation_distances
        else 0.0,
        "max_relocation_distance": round(max(relocation_distances), 6) if relocation_distances else 0.0,
        "row_relocation_cost": round(sum(relocation_costs), 6),
    }


def _parse_levels(text: str) -> list[float]:
    return [float(token.strip()) for token in text.split(",") if token.strip()]


def _clean_number(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value


def _round_or_none(value) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def _as_float_or_none(value) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


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
