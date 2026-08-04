"""원 논문의 싱글파트 base MILP에서 모듈 중복률-재구성비용 관계를 분석한다."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from Src.data import load_instance
from Src.milp import solve_milp
from Src.module_overlap import (
    build_controlled_configurations,
    calculate_overlap_metrics,
    draw_sensitivity_chart,
    evaluate_reference_transitions,
    transition_cost_metrics,
)
from Src.output import save_solution


BASE_DIR = Path(__file__).resolve().parent
SINGLE_PART_DIR = BASE_DIR / "Data" / "single_part"


def experiment_config(configuration_file: Path, name: str, args) -> SimpleNamespace:
    return SimpleNamespace(
        PROBLEM_NAME=name,
        LOCATION_FILE=SINGLE_PART_DIR / "locations.csv",
        CONFIGURATION_FILE=configuration_file,
        PRODUCTION_RATE_FILE=SINGLE_PART_DIR / "production_rates.csv",
        DEMAND_FILE=SINGLE_PART_DIR / "demands.csv",
        PARAMETER_FILE=SINGLE_PART_DIR / "parameters.csv",
        SHARED_RESOURCE_FILE=SINGLE_PART_DIR / "shared_resources.csv",
        RESOURCE_REQUIREMENT_FILE=SINGLE_PART_DIR / "resource_requirements.csv",
        TIME_LIMIT=args.time_limit,
        MIP_GAP=args.mip_gap,
        OUTPUT_FLAG=args.solver_output,
        SAME_MACHINE_RECONFIG_ONLY=True,
        USE_SHARED_RESOURCES=False,
        OPTIMIZE_SHARED_RESOURCE_CAPACITY=False,
        COUNT_SHARED_RESOURCES_AFTER_SOLVE=False,
        START_OPERATION=0,
        END_OPERATION=999,
    )


def solve_scenario(label: str, scenario_type: str, target: float | None, config_file: Path, result_dir: Path, args):
    config = experiment_config(config_file, f"single_part_{label}", args)
    instance = load_instance(config)
    solution = solve_milp(instance, config)
    save_solution(solution, result_dir)
    if not solution.summary.get("solution_count"):
        raise RuntimeError(f"No feasible solution was found for {label}: {solution.summary}")

    metrics = calculate_overlap_metrics(pd.read_csv(config_file))
    row = {
        "scenario": label,
        "scenario_type": scenario_type,
        "target_overlap_fraction": target,
        "actual_overlap_coefficient": metrics["mean_overlap_coefficient"],
        "actual_jaccard_similarity": metrics["mean_jaccard_similarity"],
        "mean_auxiliary_symmetric_difference": metrics["mean_symmetric_difference"],
        **transition_cost_metrics(instance),
        "solver_status": solution.summary["status_name"],
        "runtime_seconds": solution.summary["runtime_seconds"],
        "optimized_reconfiguration_count": len(solution.reconfigurations),
        "optimized_reconfiguration_cost": solution.cost_breakdown["reconfiguration_cost"],
        "purchase_cost": solution.cost_breakdown["purchase_cost"],
        "material_handling_cost": solution.cost_breakdown["material_handling_cost"],
        "total_objective": solution.cost_breakdown["total_objective"],
    }
    return instance, solution, row


def reduction(value: float, reference: float) -> tuple[float, float]:
    amount = reference - value
    percent = amount / reference * 100 if reference else 0.0
    return amount, percent


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, rows: list[dict]) -> None:
    original = next(row for row in rows if row["scenario_type"] == "original")
    controlled = [row for row in rows if row["scenario_type"] == "controlled"]
    first, last = controlled[0], controlled[-1]
    fixed_drop, fixed_pct = reduction(
        last["fixed_reference_reconfiguration_cost"], first["fixed_reference_reconfiguration_cost"]
    )
    optimized_drop, optimized_pct = reduction(
        last["optimized_reconfiguration_cost"], first["optimized_reconfiguration_cost"]
    )
    lines = [
        "# 싱글파트 모듈 중복률 민감도 분석",
        "",
        "원 논문의 싱글파트 base MILP(`Src/milp.py`)를 그대로 사용하고, 보조 모듈 구성만 통제했습니다.",
        "생산률·수요·설비 구매비·공정 경로·위치는 모든 시나리오에서 같습니다.",
        "",
        "## 핵심 결과",
        "",
        f"- 통제된 0%→100% 중복에서 고정 기준계획 재구성비용: {first['fixed_reference_reconfiguration_cost']:,.1f} → {last['fixed_reference_reconfiguration_cost']:,.1f} (감소 {fixed_drop:,.1f}, {fixed_pct:.2f}%)",
        f"- 통제된 0%→100% 중복에서 재최적화 재구성비용: {first['optimized_reconfiguration_cost']:,.1f} → {last['optimized_reconfiguration_cost']:,.1f} (감소 {optimized_drop:,.1f}, {optimized_pct:.2f}%)",
        f"- 원본 데이터의 평균 overlap coefficient: {original['actual_overlap_coefficient'] * 100:.2f}%",
        "",
        "`fixed_reference_reconfiguration_cost`는 원본 최적해와 동일한 configuration 전이를 유지한 값이라 모듈 중복 자체의 비용 효과를 보여줍니다. `optimized_reconfiguration_cost`는 각 중복률에서 다시 최적화한 실제 결과이므로 전이 횟수와 선택 configuration 변화까지 포함합니다.",
        "",
        "## 시나리오별 결과",
        "",
        "| 시나리오 | 실제 중복률 | 고정계획 비용 | 재최적화 비용 | 전이 수 | 총 목적함수 | 상태 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['scenario']} | {row['actual_overlap_coefficient'] * 100:.2f}% | "
            f"{row['fixed_reference_reconfiguration_cost']:,.1f} | {row['optimized_reconfiguration_cost']:,.1f} | "
            f"{row['optimized_reconfiguration_count']} | {row['total_objective']:,.1f} | {row['solver_status']} |"
        )
    lines += [
        "",
        "## 해석 주의사항",
        "",
        "중복률은 같은 machine type 내 configuration 쌍의 `|A∩B| / min(|A|, |B|)` 평균입니다. 기본 모듈은 그대로 두고 보조 모듈만 바꾸며, 각 configuration이 가진 보조 모듈 개수도 보존합니다. 따라서 결과는 '모듈 종류의 공용화' 효과이고 모듈 수 감소 효과가 아닙니다.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--levels", nargs="+", type=float, default=[0, 0.25, 0.5, 0.75, 1])
    parser.add_argument("--time-limit", type=float, default=120.0)
    parser.add_argument("--mip-gap", type=float, default=0.0)
    parser.add_argument("--solver-output", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=BASE_DIR / "Result_module_overlap")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    levels = sorted(set(args.levels))
    if not levels or any(level < 0 or level > 1 for level in levels):
        raise ValueError("--levels values must be between 0 and 1")

    output_dir = args.output_dir.resolve()
    scenario_root = output_dir / "scenarios"
    scenario_root.mkdir(parents=True, exist_ok=True)
    original_file = SINGLE_PART_DIR / "configurations.csv"

    print("[1] Solving original single-part base model ...", flush=True)
    original_instance, original_solution, original_row = solve_scenario(
        "original", "original", None, original_file, scenario_root / "original", args
    )
    reference_transitions = original_solution.reconfigurations
    original_row["fixed_reference_reconfiguration_cost"] = evaluate_reference_transitions(
        reference_transitions, original_instance
    )

    source = pd.read_csv(original_file)
    rows = [original_row]
    for index, level in enumerate(levels, start=2):
        label = f"overlap_{round(level * 100):03d}"
        folder = scenario_root / label
        folder.mkdir(parents=True, exist_ok=True)
        scenario_file = folder / "configurations.csv"
        build_controlled_configurations(source, level).to_csv(scenario_file, index=False)
        print(f"[{index}] Solving controlled overlap {level:.0%} ...", flush=True)
        instance, _, row = solve_scenario(label, "controlled", level, scenario_file, folder, args)
        row["fixed_reference_reconfiguration_cost"] = evaluate_reference_transitions(
            reference_transitions, instance
        )
        rows.append(row)

    zero_reference = next((row for row in rows if row.get("target_overlap_fraction") == 0), None)
    for row in rows:
        if zero_reference is None:
            row["optimized_cost_reduction_vs_zero"] = None
            row["optimized_cost_reduction_percent_vs_zero"] = None
            row["fixed_plan_reduction_vs_zero"] = None
            row["fixed_plan_reduction_percent_vs_zero"] = None
            continue
        opt_amount, opt_pct = reduction(
            row["optimized_reconfiguration_cost"], zero_reference["optimized_reconfiguration_cost"]
        )
        fixed_amount, fixed_pct = reduction(
            row["fixed_reference_reconfiguration_cost"], zero_reference["fixed_reference_reconfiguration_cost"]
        )
        row["optimized_cost_reduction_vs_zero"] = opt_amount
        row["optimized_cost_reduction_percent_vs_zero"] = opt_pct
        row["fixed_plan_reduction_vs_zero"] = fixed_amount
        row["fixed_plan_reduction_percent_vs_zero"] = fixed_pct

    write_csv(output_dir / "module_overlap_sensitivity.csv", rows)
    (output_dir / "module_overlap_sensitivity.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_report(output_dir / "REPORT.md", rows)
    draw_sensitivity_chart(rows, output_dir / "module_overlap_sensitivity.png")
    print(f"Done. Results: {output_dir}")


if __name__ == "__main__":
    main()
