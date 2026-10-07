# -*- coding: utf-8 -*-
"""이동비 손익분기: off(이미 최적 증명된 정적 해)를 기준으로 두고, joint 만 이동비 단가 u 별로 다시 푼다.

이동비 = u x 이동 거리 (기계 1대 1칸 이동에 u, 서훈 모델·기존 캠페인 손익분기와 같은 정의, MOVE_COST_FLAT).
joint 는 off 해로 warm start (off 해는 어떤 u 에서도 joint 의 실행가능해 -> joint <= off 보장).
off 가 OPTIMAL 이면 이득 하한 = off - joint 해 가 증명된 값이다.

사용법: python scratchpad/move_cost_sweep.py CELL_ID TIME_LIMIT u1,u2,...
결과: Result/adaptive_campaign/move_cost_sweep.json 에 누적
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

CELL = sys.argv[1]
TIME_LIMIT = int(sys.argv[2])
UNITS = [float(u) for u in sys.argv[3].split(",")]

sys.argv = ["campaign_run.py", "unused.json", str(TIME_LIMIT)]  # campaign_run 은 import 시 argv 를 읽는다
from scratchpad import campaign_run  # noqa: E402
from scratchpad import milp_adaptive_flat as engine_z  # noqa: E402
from Src.data import load_instance  # noqa: E402

OUT = REPO / "Result" / "adaptive_campaign"
RESULTS = OUT / "move_cost_sweep.json"


def main():
    prev = {r["id"]: r for r in json.loads((OUT / "campaign_results.json").read_text(encoding="utf-8"))}[CELL]
    off_obj = float(prev["off"]["obj"])
    off_proven = prev["off"]["status"] == "OPTIMAL"
    data_dir = OUT / CELL / "data"
    warm = OUT / CELL / "off_solution"
    for u in UNITS:
        log = OUT / CELL / ("gurobi_joint_u%g.log" % u)
        shim = campaign_run.make_shim(data_dir, "joint", log)
        shim.TIME_LIMIT = TIME_LIMIT
        shim.MOVE_COST_FLAT = u
        shim.USE_WARM_START = True
        shim.WARM_START_DIR = warm
        shim.COMPUTE_LP_RELAXATION_BOUND = False
        inst = load_instance(shim)
        t0 = time.time()
        sol = engine_z.solve_milp(inst, shim)
        s, cb = sol.summary, sol.cost_breakdown
        obj, bound = s.get("objective"), s.get("best_bound")
        rel = getattr(sol, "relocations", []) or []
        row = {
            "id": CELL, "u": u, "time_limit": TIME_LIMIT, "status": s.get("status_name"),
            "obj": obj, "bound": bound, "gap": s.get("mip_gap"), "runtime": round(float(s.get("runtime_seconds", 0)), 1),
            "wall": round(time.time() - t0, 1), "off_obj": off_obj, "off_proven": off_proven,
            "purchase": cb.get("purchase_cost"), "reconfig": cb.get("reconfiguration_cost"),
            "mhc": cb.get("material_handling_cost"), "move": cb.get("relocation_cost"),
            "relocations": len(rel), "move_distance": round(sum(float(r.get("distance", 0)) for r in rel), 1),
            "gain_lb": round(off_obj - obj, 1) if (off_proven and obj is not None) else 0.0,
            "gain_ub": round(off_obj - bound, 1) if bound is not None else None,
        }
        row["gain_lb_pct"] = round(100.0 * row["gain_lb"] / off_obj, 2)
        done = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else []
        done = [r for r in done if not (r["id"] == CELL and r["u"] == u and r["time_limit"] == TIME_LIMIT)]
        done.append(row)
        RESULTS.write_text(json.dumps(done, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(">>> u=%g: %s obj=%s bound=%s | 이득 [%s, %s] (%.2f%%~) | 이동 %d회 %s칸, 이동비 %s" % (
            u, row["status"], obj, bound, row["gain_lb"], row["gain_ub"], row["gain_lb_pct"],
            row["relocations"], row["move_distance"], row["move"]), flush=True)


if __name__ == "__main__":
    main()
