from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path


def save_solution(solution, result_dir: Path) -> None:
    """MILP 해를 Result/ 아래 표준 CSV/JSON 파일로 저장한다."""
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "solution_summary.json").write_text(json.dumps(solution.summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_rows(result_dir / "purchased_machines.csv", solution.purchased_machines)
    _write_rows(result_dir / "machine_states.csv", solution.machine_states)
    _write_rows(result_dir / "reconfigurations.csv", solution.reconfigurations)
    _write_rows(result_dir / "material_flows.csv", solution.material_flows)
    _write_rows(result_dir / "cost_breakdown.csv", [solution.cost_breakdown] if solution.cost_breakdown else [])
    _write_rows(result_dir / "cost_by_period.csv", _cost_by_period(solution))
    _write_rows(result_dir / "cost_detail.csv", _cost_detail(solution))


def _cost_by_period(solution) -> list[dict]:
    """period별 구매/재구성/자재취급 비용 요약표를 만든다 (논문 Table 6 형태).

    구매는 이 모델에서 x에 period 인덱스가 없어 전부 첫 period에 발생한다.
    """
    if not solution.cost_breakdown:
        return []

    periods = list(solution.summary.get("periods", []))
    first_period = min(periods) if periods else 1

    purchase: dict[int, float] = defaultdict(float)
    reconfig: dict[int, float] = defaultdict(float)
    handling: dict[int, float] = defaultdict(float)

    for row in solution.purchased_machines:
        purchase[first_period] += float(row["purchase_cost"])
    for row in solution.reconfigurations:
        reconfig[int(row["period"])] += float(row["reconfiguration_cost"])
    for row in solution.material_flows:
        handling[int(row["period"])] += float(row["flow_cost"])

    rows: list[dict] = []
    for t in periods:
        p, r, h = purchase.get(t, 0.0), reconfig.get(t, 0.0), handling.get(t, 0.0)
        rows.append(_cost_row(t, p, r, h))
    rows.append(_cost_row("total", sum(purchase.values()), sum(reconfig.values()), sum(handling.values())))
    return rows


def _cost_row(period, purchase: float, reconfig: float, handling: float) -> dict:
    return {
        "period": period,
        "purchase_cost": round(purchase, 6),
        "reconfiguration_cost": round(reconfig, 6),
        "material_handling_cost": round(handling, 6),
        "period_total": round(purchase + reconfig + handling, 6),
    }


def _cost_detail(solution) -> list[dict]:
    """각 비용이 어디서(위치) 어떤 이유로 나왔는지 항목별로 풀어쓴다."""
    if not solution.cost_breakdown:
        return []

    periods = list(solution.summary.get("periods", []))
    first_period = min(periods) if periods else 1
    rows: list[dict] = []

    for row in solution.purchased_machines:
        rows.append({
            "period": first_period,
            "cost_type": "purchase",
            "location": row["location"],
            "amount": round(float(row["purchase_cost"]), 6),
            "detail": f"위치 {row['location']}에 {row['machine']}({row['configuration']}) 구매, 초기 op{row['initial_operation']}",
        })
    for row in solution.reconfigurations:
        rows.append({
            "period": int(row["period"]),
            "cost_type": "reconfiguration",
            "location": row["location"],
            "amount": round(float(row["reconfiguration_cost"]), 6),
            "detail": f"위치 {row['location']}: {row['from_configuration']}→{row['to_configuration']} 재구성 (op{row['operation']})",
        })
    for row in solution.material_flows:
        rows.append({
            "period": int(row["period"]),
            "cost_type": "material_handling",
            "location": f"{row['from_location']}->{row['to_location']}",
            "amount": round(float(row["flow_cost"]), 6),
            "detail": f"위치 {row['from_location']}(op{row['from_operation']})→{row['to_location']}(op{row['to_operation']}), flow {row['flow']} × 거리 {row['distance']} × MHC {row['mhc']}",
        })

    rows.sort(key=lambda r: (r["period"], r["cost_type"]))
    return rows


def _write_rows(path: Path, rows: list[dict]) -> None:
    """dict row list를 CSV로 저장한다. 빈 결과도 빈 파일로 남긴다."""
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
