"""모듈별 한계 점검 (marginal scan): 각 모듈 capa를 peak-1로 낮춰 여유분을 판별한다.

판정 논리:
  capa 축소는 해공간을 줄일 뿐이므로 최적값은 기준선(BASELINE_OBJ)보다 좋아질 수 없다.
  - 기준선과 같은 objective를 찾으면 => FREE (여유 있음, 증명됨)
  - 증명된 하한(bound)이 기준선을 초과하면 => INCREASE_PROVEN (빡빡함, 증명됨)
  - 둘 다 아니면 => AMBIGUOUS (시간 부족, 더 긴 실행 필요)

사용법 (프로젝트 루트에서):
    python experiments/capacity_margin_scan.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from types import SimpleNamespace

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from Src.data.loader import load_instance
from Src.models.milp import solve_milp

# ---------------- 실험 설정 ----------------
PROBLEM_TYPE = "single_part"
LOCATION_NAME = "layout_18"
RMT_TABLE_NAME = "table_1"
DEMAND_NAME = "demand_1"
PARAMETER_NAME = PROBLEM_TYPE
SHARED_RESOURCE_NAME = "shared_resources_1"
PROBLEM = PROBLEM_TYPE
BASELINE_OBJ = 22910.0                # capa=peak 기준선 최적값
SKIP_MODULES = {20}                   # 이미 스윕 완료 (적정 capa=12 확정)
REDUCE_BY = 1                         # peak - 1 테스트
TIME_LIMIT = 300
MIP_GAP = 0.0                         # 여유/증가를 증명 수준으로 판별하기 위해 0
TOL = 1e-6
# -------------------------------------------


def make_config(problem: str) -> SimpleNamespace:
    location_dir = BASE_DIR / "Data" / "locations"
    rmt = BASE_DIR / "Data" / "rmt_tables" / RMT_TABLE_NAME
    demand_dir = BASE_DIR / "Data" / "demands" / problem
    parameter_dir = BASE_DIR / "Data" / "parameters"
    shared_dir = BASE_DIR / "Data" / "shared_resources"
    return SimpleNamespace(
        PROBLEM_TYPE=problem,
        PROBLEM_NAME=problem,
        LOCATION_FILE=location_dir / f"{LOCATION_NAME}.csv",
        CONFIGURATION_FILE=rmt / "configurations.csv",
        PRODUCTION_RATE_FILE=rmt / "production_rates.csv",
        DEMAND_FILE=demand_dir / f"{DEMAND_NAME}.csv",
        PARAMETER_FILE=parameter_dir / f"{PARAMETER_NAME}.csv",
        USE_SHARED_RESOURCES=True,
        SHARED_RESOURCE_FILE=shared_dir / f"{SHARED_RESOURCE_NAME}.csv",
        RESOURCE_REQUIREMENT_FILE=rmt / "resource_requirements.csv",
        TIME_LIMIT=TIME_LIMIT,
        MIP_GAP=MIP_GAP,
        SAME_MACHINE_RECONFIG_ONLY=True,
        START_OPERATION=0,
        END_OPERATION=999,
    )


FIELDS = [
    "module", "peak", "tested_capacity", "status", "objective", "bound",
    "verdict", "runtime_s",
]


def verdict_of(status: str, objective, bound) -> str:
    if status == "INFEASIBLE":
        return "INFEASIBLE"
    if objective is not None and objective <= BASELINE_OBJ + TOL:
        return "FREE"                       # 기준선 해와 같은 비용 달성 → 여유 증명
    if bound is not None and bound > BASELINE_OBJ + TOL:
        return "INCREASE_PROVEN"            # 하한이 기준선 초과 → 증가 증명
    return "AMBIGUOUS"


def run() -> None:
    cfg = make_config(PROBLEM)
    base_instance = load_instance(cfg)
    peaks = dict(sorted(base_instance.shared_resource_capacity.items()))
    targets = [m for m in peaks if m not in SKIP_MODULES]

    out_path = BASE_DIR / "Result" / PROBLEM / RMT_TABLE_NAME / DEMAND_NAME / "capacity_margin_scan.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        f.flush()

        for m in targets:
            peak = peaks[m]
            tested = peak - REDUCE_BY
            if tested < 0:
                continue

            instance = load_instance(cfg)
            instance.shared_resource_capacity[m] = tested

            print(f"\n===== module {m}: capa {peak} -> {tested} =====", flush=True)
            solution = solve_milp(instance, cfg)

            summary = solution.summary
            objective = summary.get("objective")
            gap = summary.get("mip_gap")
            bound = objective * (1 - gap) if objective is not None and gap is not None else None
            status = summary["status_name"]

            row = {
                "module": m,
                "peak": peak,
                "tested_capacity": tested,
                "status": status,
                "objective": objective,
                "bound": round(bound, 2) if bound is not None else None,
                "verdict": verdict_of(status, objective, bound),
                "runtime_s": round(summary.get("runtime_seconds", 0.0), 1),
            }
            writer.writerow(row)
            f.flush()
            print(f"----- module {m}: {row['verdict']} (obj={objective}) -----", flush=True)

    print(f"\n스캔 완료 → {out_path}")


if __name__ == "__main__":
    run()
