from __future__ import annotations

import csv
import json
from pathlib import Path


def save_solution(solution, result_dir: Path) -> None:
    """MILP 해를 Result/ 아래 표준 CSV/JSON 파일로 저장한다."""
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "solution_summary.json").write_text(json.dumps(solution.summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_rows(result_dir / "purchased_machines.csv", solution.purchased_machines)
    _write_rows(result_dir / "machine_states.csv", solution.machine_states)
    _write_rows(result_dir / "reconfigurations.csv", solution.reconfigurations)
    _write_rows(result_dir / "relocations.csv", solution.relocations)
    _write_rows(result_dir / "material_flows.csv", solution.material_flows)
    if solution.resource_usage:
        _write_rows(result_dir / "resource_usage.csv", solution.resource_usage)
    if solution.shared_resource_capacities:
        if solution.summary.get("resource_counting_mode") == "optimized_decision_variable":
            _write_rows(result_dir / "optimal_shared_resources.csv", solution.shared_resource_capacities)
        else:
            _write_rows(result_dir / "posthoc_shared_resource_counts.csv", solution.shared_resource_capacities)
    _write_rows(result_dir / "cost_breakdown.csv", [solution.cost_breakdown] if solution.cost_breakdown else [])

    if solution.stage_one_machine_states:
        stage_one_dir = result_dir / "stage_1_system_cost"
        stage_one_summary = {
            **solution.summary.get("primary_stage", {}),
            "stage": 1,
            "objective_name": "system_cost",
            "relocation_count": len(solution.stage_one_relocations),
        }
        _write_stage(
            stage_one_dir,
            stage_one_summary,
            solution.stage_one_purchased_machines,
            solution.stage_one_machine_states,
            solution.stage_one_reconfigurations,
            solution.stage_one_relocations,
            solution.stage_one_material_flows,
            _stage_cost_breakdown(
                solution.stage_one_purchased_machines,
                solution.stage_one_reconfigurations,
                solution.stage_one_relocations,
                solution.stage_one_material_flows,
            ),
        )
        candidates_dir = stage_one_dir / "candidates"
        candidate_index = []
        for candidate in solution.stage_one_candidates:
            candidate_id = int(candidate["candidate_id"])
            candidate_dir = candidates_dir / f"configuration_{candidate_id:02d}"
            candidate_summary = {
                "candidate_id": candidate_id,
                "system_cost": candidate["system_cost"],
                "relocation_count": candidate["relocation_count"],
            }
            candidate_index.append(candidate_summary)
            _write_stage(
                candidate_dir,
                candidate_summary,
                candidate["purchased_machines"],
                candidate["machine_states"],
                candidate["reconfigurations"],
                candidate["relocations"],
                candidate["material_flows"],
                _stage_cost_breakdown(
                    candidate["purchased_machines"],
                    candidate["reconfigurations"],
                    candidate["relocations"],
                    candidate["material_flows"],
                ),
            )
        if candidate_index:
            (candidates_dir / "index.json").write_text(
                json.dumps(candidate_index, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        if solution.summary.get("relocation_stage"):
            stage_two_dir = result_dir / "stage_2_min_relocation"
            stage_two_summary = {
                **solution.summary["relocation_stage"],
                "stage": 2,
                "objective_name": "relocation_count",
                "system_cost": solution.summary.get("objective"),
                "relocation_count": solution.summary.get("relocation_count"),
                "relocation_count_by_period": solution.summary.get("relocation_count_by_period"),
            }
            _write_stage(
                stage_two_dir,
                stage_two_summary,
                solution.purchased_machines,
                solution.machine_states,
                solution.reconfigurations,
                solution.relocations,
                solution.material_flows,
                solution.cost_breakdown,
            )


def _write_stage(
    stage_dir: Path,
    summary: dict,
    purchased: list[dict],
    states: list[dict],
    reconfigurations: list[dict],
    relocations: list[dict],
    flows: list[dict],
    cost_breakdown: dict,
) -> None:
    stage_dir.mkdir(parents=True, exist_ok=True)
    (stage_dir / "solution_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_rows(stage_dir / "purchased_machines.csv", purchased)
    _write_rows(stage_dir / "machine_states.csv", states)
    _write_rows(stage_dir / "reconfigurations.csv", reconfigurations)
    _write_rows(stage_dir / "relocations.csv", relocations)
    _write_rows(stage_dir / "material_flows.csv", flows)
    _write_rows(stage_dir / "cost_breakdown.csv", [cost_breakdown] if cost_breakdown else [])


def _stage_cost_breakdown(
    purchased: list[dict],
    reconfigurations: list[dict],
    relocations: list[dict],
    flows: list[dict],
) -> dict[str, float]:
    purchase = sum(float(row.get("purchase_cost", 0.0)) for row in purchased)
    reconfiguration = sum(
        float(row.get("reconfiguration_cost", 0.0)) for row in reconfigurations
    )
    relocation = sum(
        float(row.get("direct_relocation_cost", 0.0)) for row in relocations
    )
    handling = sum(float(row.get("flow_cost", 0.0)) for row in flows)
    return {
        "purchase_cost": purchase,
        "reconfiguration_cost": reconfiguration,
        "relocation_cost": relocation,
        "material_handling_cost": handling,
        "total_objective": purchase + reconfiguration + relocation + handling,
    }


def _write_rows(path: Path, rows: list[dict]) -> None:
    """dict row list를 CSV로 저장한다. 빈 결과도 빈 파일로 남긴다."""
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
