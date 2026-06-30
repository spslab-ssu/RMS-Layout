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
    _write_rows(result_dir / "material_flows.csv", solution.material_flows)
    _write_rows(result_dir / "cost_breakdown.csv", [solution.cost_breakdown] if solution.cost_breakdown else [])


def _write_rows(path: Path, rows: list[dict]) -> None:
    """dict row list를 CSV로 저장한다. 빈 결과도 빈 파일로 남긴다."""
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
