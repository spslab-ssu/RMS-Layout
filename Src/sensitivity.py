"""Sensitivity experiments for relocation, reconfiguration, and grid geometry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pandas as pd

import config
from Src.data import load_instance
from Src.milp import solve_milp
from Src.output import save_solution
from Src.scenario import build_grid_locations, prepare_scenario_directory
from Src.visualize import draw_layouts


def parse_numeric_levels(text: str) -> list[float]:
    """Parse a comma-separated, unique, ascending list of nonnegative levels."""
    try:
        values = sorted({float(token.strip()) for token in text.split(",") if token.strip()})
    except ValueError as exc:
        raise ValueError("비용 후보는 쉼표로 구분한 숫자여야 합니다.") from exc
    if not values:
        raise ValueError("하나 이상의 비용 후보가 필요합니다.")
    if any(value < 0 for value in values):
        raise ValueError("비용 후보는 0 이상이어야 합니다.")
    if len(values) > 12:
        raise ValueError("한 번에 비교할 후보는 12개 이하로 제한해 주세요.")
    return values


def build_cost_cases(
    analysis_type: str,
    levels: list[float],
    *,
    rows: int,
    columns: int,
    spacing: float,
    relocation_distance_cost: float,
    base_add_module_cost: float,
    base_remove_module_cost: float,
) -> list[dict[str, Any]]:
    cases = []
    for level in levels:
        if analysis_type == "relocation_cost":
            case = {
                "case": f"move_cost_{level:g}",
                "analysis_value": level,
                "rows": rows,
                "columns": columns,
                "spacing": spacing,
                "relocation_distance_cost": level,
                "reconfiguration_multiplier": 1.0,
                "add_module_cost": base_add_module_cost,
                "remove_module_cost": base_remove_module_cost,
            }
        elif analysis_type == "reconfiguration_cost":
            multiplier = level / base_add_module_cost if base_add_module_cost > 0 else 0.0
            case = {
                "case": f"add_module_cost_{level:g}",
                "analysis_value": level,
                "rows": rows,
                "columns": columns,
                "spacing": spacing,
                "relocation_distance_cost": relocation_distance_cost,
                "reconfiguration_multiplier": multiplier,
                "add_module_cost": level,
                "remove_module_cost": base_remove_module_cost * multiplier,
            }
        else:
            raise ValueError(f"Unknown cost sensitivity type: {analysis_type}")
        cases.append(case)
    return cases


def build_grid_cases(
    table: pd.DataFrame,
    *,
    relocation_distance_cost: float,
) -> list[dict[str, Any]]:
    required = {"m", "n", "coordinate_distance"}
    missing = required - set(table.columns)
    if missing:
        raise ValueError(f"격자 후보 표에 필요한 열이 없습니다: {sorted(missing)}")
    cases = []
    for index, row in table.reset_index(drop=True).iterrows():
        m = int(row["m"])
        n = int(row["n"])
        spacing = float(row["coordinate_distance"])
        if m < 1 or n < 1 or spacing <= 0:
            raise ValueError("m과 n은 1 이상, 좌표 간 거리는 0보다 커야 합니다.")
        cases.append(
            {
                "case": f"grid_{index + 1:02d}_{m}x{n}_d{spacing:g}",
                "analysis_value": index + 1,
                "rows": m,
                "columns": n,
                "spacing": spacing,
                "relocation_distance_cost": relocation_distance_cost,
                "reconfiguration_multiplier": 1.0,
                "add_module_cost": None,
                "remove_module_cost": None,
            }
        )
    if not cases:
        raise ValueError("하나 이상의 격자 후보가 필요합니다.")
    if len(cases) > 12:
        raise ValueError("한 번에 비교할 격자는 12개 이하로 제한해 주세요.")
    return cases


def run_sensitivity(
    *,
    problem: str,
    demands: pd.DataFrame,
    cases: list[dict[str, Any]],
    result_dir: Path,
    time_limit_per_case: float,
    relocation_fixed_cost: float = 0.0,
    progress: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> pd.DataFrame:
    """Solve independent cases sequentially and preserve every case input/result."""
    result_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, case in enumerate(cases, start=1):
        if progress:
            progress(index, len(cases), case)
        case_dir = result_dir / case["case"]
        try:
            locations = build_grid_locations(
                int(case["rows"]),
                int(case["columns"]),
                spacing_x=float(case["spacing"]),
                spacing_y=float(case["spacing"]),
            )
            paths = prepare_scenario_directory(
                config.DATA_DIR / problem,
                case_dir / "input",
                locations,
                demands,
            )
            settings = config.build_config(
                problem_name=problem,
                profile="network_mir",
                result_dir=case_dir,
                PROBLEM_NAME=case["case"],
                PROBLEM_DIR=case_dir / "input",
                ENABLE_RELOCATION=True,
                MINIMIZE_RELOCATIONS_SECONDARY=True,
                RELOCATION_DISTANCE_COST=float(case["relocation_distance_cost"]),
                RELOCATION_FIXED_COST=float(relocation_fixed_cost),
                RELOCATION_DOWNTIME_FRACTION=0.0,
                RELOCATION_CREW_CAPACITY=None,
                FORBID_REVERSE_SWAPS=False,
                RELOCATION_CONGESTION_COST_STEP=0.0,
                TIME_LIMIT=float(time_limit_per_case),
                MIP_GAP=0.0,
                STAGE_ONE_CONFIGURATION_LIMIT=1,
                OUTPUT_FLAG=0,
                **paths,
            )
            instance = load_instance(settings)
            multiplier = float(case["reconfiguration_multiplier"])
            instance.reconfiguration_cost = {
                key: value * multiplier
                for key, value in instance.reconfiguration_cost.items()
            }
            solution = solve_milp(instance, settings)
            save_solution(solution, case_dir)
            if solution.machine_states:
                draw_layouts(case_dir, instance)
            rows.append(_result_row(case, solution))
        except Exception as exc:  # Keep the remaining experimental cases running.
            rows.append({**_case_columns(case), "status": "ERROR", "error": str(exc)})

    frame = pd.DataFrame(rows)
    frame.to_csv(result_dir / "sensitivity_summary.csv", index=False)
    (result_dir / "sensitivity_cases.json").write_text(
        json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return frame


def recommend_case(frame: pd.DataFrame, analysis_type: str) -> dict[str, Any]:
    """Return a transparent heuristic, never an unsupported 'true' cost claim."""
    valid = frame[frame["status"] == "OPTIMAL"].copy()
    if valid.empty:
        return {"case": None, "reason": "최적성이 증명된 실험이 없습니다."}
    if analysis_type == "grid":
        chosen = valid.sort_values(
            ["system_cost", "relocation_count", "grid_area", "coordinate_distance"]
        ).iloc[0]
        return {
            "case": chosen["case"],
            "value": f"{int(chosen['m'])} × {int(chosen['n'])}, 거리 {chosen['coordinate_distance']:g}",
            "reason": "비교한 후보 중 시스템 비용이 가장 낮고, 동률이면 relocation이 적은 격자입니다.",
        }

    count_column = (
        "relocation_count" if analysis_type == "relocation_cost" else "reconfiguration_count"
    )
    valid = valid.sort_values("analysis_value").reset_index(drop=True)
    for index in range(len(valid) - 1):
        tail = valid.iloc[index:]
        if tail[count_column].nunique(dropna=False) == 1:
            chosen = valid.iloc[index]
            return {
                "case": chosen["case"],
                "value": float(chosen["analysis_value"]),
                "reason": f"이 값부터 더 큰 후보까지 {count_column}가 변하지 않는 최초 안정 구간입니다.",
            }
    return {
        "case": None,
        "reason": "현재 범위에서 안정 구간이 나타나지 않았습니다. 비용 후보 범위를 늘려야 합니다.",
    }


def _case_columns(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "case": case["case"],
        "analysis_value": case["analysis_value"],
        "m": int(case["rows"]),
        "n": int(case["columns"]),
        "grid_area": int(case["rows"]) * int(case["columns"]),
        "coordinate_distance": float(case["spacing"]),
        "relocation_distance_cost": float(case["relocation_distance_cost"]),
        "reconfiguration_multiplier": float(case["reconfiguration_multiplier"]),
        "add_module_cost": case.get("add_module_cost"),
        "remove_module_cost": case.get("remove_module_cost"),
    }


def _result_row(case: dict[str, Any], solution) -> dict[str, Any]:
    summary = solution.summary
    costs = solution.cost_breakdown
    return {
        **_case_columns(case),
        "status": summary.get("status_name"),
        "system_cost": summary.get("objective"),
        "purchase_cost": costs.get("purchase_cost"),
        "reconfiguration_cost": costs.get("reconfiguration_cost"),
        "material_handling_cost": costs.get("material_handling_cost"),
        "relocation_cost": costs.get("relocation_cost"),
        "reconfiguration_count": len(solution.reconfigurations),
        "relocation_count": summary.get("relocation_count"),
        "total_relocation_distance": sum(
            float(row.get("distance", 0.0)) for row in solution.relocations
        ),
        "lexicographic_optimal": summary.get("lexicographic_optimal"),
        "runtime_seconds": summary.get("runtime_seconds"),
        "error": None,
    }
