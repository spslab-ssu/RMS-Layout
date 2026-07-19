"""멀티파트 기준해와 shared-resource 1개 감소 민감도 분석을 실행한다.

1. 논문 Figure 4에서 역산한 shared-resource 최소용량을 고정한다.
2. 기준 문제를 최대 1시간, 0.1% MIP gap까지 푼다.
3. 양수 용량인 resource를 하나씩 1개 줄여 재최적화한다.
4. scenario lower bound가 기준 incumbent보다 커지면 비용 증가가 증명된
   것이므로 BestBdStop으로 조기 종료한다.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

from gurobipy import GRB

import config
from Src.data import load_instance
from Src.milp import solve_milp
from Src.output import save_solution
from Src.visualize import draw_layouts


RESULT_ROOT = config.BASE_DIR / "Result_resource_sensitivity"
INCREASE_TOLERANCE = 1e-4


def _config_copy(**overrides) -> SimpleNamespace:
    values = {
        name: getattr(config, name)
        for name in dir(config)
        if name.isupper()
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _classify(summary: dict, baseline_objective: float) -> str:
    if summary.get("status") == GRB.INFEASIBLE:
        return "INFEASIBLE_PROVEN"
    lower_bound = summary.get("lower_bound")
    if lower_bound is not None and lower_bound > baseline_objective + INCREASE_TOLERANCE:
        return "INCREASE_PROVEN"
    objective = summary.get("objective")
    if objective is not None and objective <= baseline_objective + INCREASE_TOLERANCE:
        return "NO_INCREASE_FOUND"
    return "UNRESOLVED"


def _write_table(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(rows: list[dict], path: Path) -> None:
    columns = [
        "resource",
        "capacity_change",
        "scenario_objective",
        "scenario_lower_bound",
        "proven_min_increase",
        "best_found_increase",
        "decision",
        "status_name",
        "runtime_seconds",
    ]
    header = "| " + " | ".join(columns) + " |"
    divider = "|" + "|".join("---" for _ in columns) + "|"
    lines = [header, divider]
    for row in rows:
        lines.append("| " + " | ".join(str(row[column]) for column in columns) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)

    baseline_config = _config_copy(
        PROBLEM_NAME="multi_part",
        TIME_LIMIT=3600,
        MIP_GAP=0.001,
        USE_SHARED_RESOURCES=True,
        OPTIMIZE_SHARED_RESOURCE_CAPACITY=False,
        OUTPUT_FLAG=1,
        RESULT_DIR=RESULT_ROOT / "baseline",
    )
    baseline_instance = load_instance(baseline_config)
    baseline_solution = solve_milp(baseline_instance, baseline_config)
    if "objective" not in baseline_solution.summary:
        raise RuntimeError(f"기준 문제에서 실행가능해를 찾지 못했습니다: {baseline_solution.summary}")

    save_solution(baseline_solution, baseline_config.RESULT_DIR)
    draw_layouts(baseline_config.RESULT_DIR, baseline_instance)
    baseline_objective = float(baseline_solution.summary["objective"])

    rows: list[dict] = []
    for resource, baseline_capacity in sorted(baseline_instance.shared_resource_capacity.items()):
        if baseline_capacity <= 0:
            continue

        tested_capacity = baseline_capacity - 1
        scenario_config = _config_copy(
            PROBLEM_NAME="multi_part",
            TIME_LIMIT=float(config.SENSITIVITY_TIME_LIMIT),
            MIP_GAP=0.0,
            USE_SHARED_RESOURCES=True,
            OPTIMIZE_SHARED_RESOURCE_CAPACITY=False,
            OUTPUT_FLAG=0,
            BEST_BOUND_STOP=baseline_objective + INCREASE_TOLERANCE,
            RESULT_DIR=RESULT_ROOT / f"resource_{resource}_minus_1",
        )
        scenario_instance = load_instance(scenario_config)
        scenario_instance.shared_resource_capacity[resource] = tested_capacity
        scenario_solution = solve_milp(scenario_instance, scenario_config)
        save_solution(scenario_solution, scenario_config.RESULT_DIR)

        summary = scenario_solution.summary
        objective = summary.get("objective")
        lower_bound = summary.get("lower_bound")
        decision = _classify(summary, baseline_objective)
        rows.append(
            {
                "resource": resource,
                "baseline_capacity": baseline_capacity,
                "tested_capacity": tested_capacity,
                "capacity_change": f"{baseline_capacity}->{tested_capacity}",
                "baseline_objective": baseline_objective,
                "scenario_objective": "" if objective is None else objective,
                "scenario_lower_bound": "" if lower_bound is None else lower_bound,
                "proven_min_increase": (
                    ""
                    if lower_bound is None
                    else round(float(lower_bound) - baseline_objective, 6)
                ),
                "best_found_increase": (
                    ""
                    if objective is None
                    else round(float(objective) - baseline_objective, 6)
                ),
                "decision": decision,
                "status_name": summary.get("status_name", ""),
                "mip_gap": summary.get("mip_gap", ""),
                "runtime_seconds": round(float(summary.get("runtime_seconds", 0.0)), 6),
            }
        )
        _write_table(rows, RESULT_ROOT / "resource_sensitivity_partial.csv")

    _write_table(rows, RESULT_ROOT / "resource_sensitivity.csv")
    _write_markdown(rows, RESULT_ROOT / "resource_sensitivity.md")
    metadata = {
        "baseline": baseline_solution.summary,
        "paper_based_capacities": baseline_instance.shared_resource_capacity,
        "sensitivity_time_limit_seconds": config.SENSITIVITY_TIME_LIMIT,
        "tested_resource_count": len(rows),
    }
    (RESULT_ROOT / "sensitivity_summary.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
