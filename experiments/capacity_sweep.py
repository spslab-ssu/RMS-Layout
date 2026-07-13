"""Capa 민감도 스윕 (방식 B: 병목 모듈 단위 축소).

병목 모듈의 capa를 peak에서 1씩 줄여가며 solve를 반복하고,
시나리오별 비용 변화를 Result/<problem>/capacity_sweep.csv로 집계한다.

사용법 (프로젝트 루트에서):
    python experiments/capacity_sweep.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from types import SimpleNamespace

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from Src.data import load_instance
from Src.milp import solve_milp

# ---------------- 실험 설정 ----------------
PROBLEM = "single_part"
TARGET_MODULE = 20                    # 병목 모듈 (mc51/mc52/mc54/mc32 공통)
CAPA_VALUES = [12, 11, 10, 9, 8]      # 12 = peak(기준선)
TIME_LIMIT = 300                      # capa를 조이면 어려워지므로 시나리오당 5분
MIP_GAP = 0.01                        # 민감도 분석용 1% gap
# -------------------------------------------


def make_config(problem: str) -> SimpleNamespace:
    d = BASE_DIR / "Data" / problem
    return SimpleNamespace(
        PROBLEM_NAME=problem,
        LOCATION_FILE=d / "locations.csv",
        CONFIGURATION_FILE=d / "configurations.csv",
        PRODUCTION_RATE_FILE=d / "production_rates.csv",
        DEMAND_FILE=d / "demands.csv",
        PARAMETER_FILE=d / "parameters.csv",
        RESOURCE_CAPACITY_FILE=d / "resource_capacities.csv",
        TIME_LIMIT=TIME_LIMIT,
        MIP_GAP=MIP_GAP,
        SAME_MACHINE_RECONFIG_ONLY=True,
        START_OPERATION=0,
        END_OPERATION=999,
    )


FIELDS = [
    "scenario", "module", "capacity", "status", "objective", "mip_gap", "bound",
    "purchase_cost", "reconfiguration_cost", "material_handling_cost",
    "n_machines", "n_reconfigs", "runtime_s",
]


def run() -> None:
    cfg = make_config(PROBLEM)
    out_path = BASE_DIR / "Result" / PROBLEM / "capacity_sweep.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        f.flush()

        for capa in CAPA_VALUES:
            instance = load_instance(cfg)              # 매 시나리오 새로 로드 (CSV는 그대로)
            instance.resource_capacity[TARGET_MODULE] = capa

            print(f"\n===== scenario: module {TARGET_MODULE} capa={capa} =====", flush=True)
            solution = solve_milp(instance, cfg)

            summary = solution.summary
            objective = summary.get("objective")
            gap = summary.get("mip_gap")
            row = {
                "scenario": f"m{TARGET_MODULE}_capa{capa}",
                "module": TARGET_MODULE,
                "capacity": capa,
                "status": summary["status_name"],
                "objective": objective,
                "mip_gap": round(gap, 6) if gap is not None else None,
                # bound = 증명된 하한. TIME_LIMIT 종료여도 "최소 이만큼은 든다"는 근거.
                "bound": round(objective * (1 - gap), 2) if objective is not None and gap is not None else None,
                "purchase_cost": solution.cost_breakdown.get("purchase_cost"),
                "reconfiguration_cost": solution.cost_breakdown.get("reconfiguration_cost"),
                "material_handling_cost": solution.cost_breakdown.get("material_handling_cost"),
                "n_machines": len(solution.purchased_machines),
                "n_reconfigs": len(solution.reconfigurations),
                "runtime_s": round(summary.get("runtime_seconds", 0.0), 1),
            }
            writer.writerow(row)
            f.flush()                                   # 시나리오마다 즉시 저장
            print(f"----- 기록됨: {row['scenario']} obj={objective} -----", flush=True)

    print(f"\n스윕 완료 → {out_path}")


if __name__ == "__main__":
    run()
