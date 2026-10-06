# -*- coding: utf-8 -*-
"""이득 > 0 증명용 off 단독 실행 (z 엔진, ADAPTIVE_MODE=off).

이득 하한 = off bound - joint 해. 그래서 off 최적을 증명할 필요 없이
"off 에 joint 해보다 좋은(같은) 해가 없다"만 보이면 이득 > 0 이 증명된다.
  - Cutoff = joint 해 + 0.5 : 그보다 나쁜 해는 무시 -> 그 이하 노드를 전부 가지치기
  - MIPFocus = 3            : 해 찾기보다 bound 올리기에 집중
결과 해석:
  status CUTOFF(6)  -> off 최적 >= cutoff  -> 이득 > 0 증명
  해를 찾음          -> off 에 joint 만큼 좋은 정적 해가 있음 -> 600초 이득은 탐색 부족이었음
  TIME_LIMIT(해 없음) -> 이득 하한 = max(0, bound - joint 해)

사용법: python scratchpad/off_cutoff_run.py CELL_ID TIME_LIMIT
  셀 데이터는 Result/adaptive_campaign/<CELL_ID>/data, joint 해는 campaign_results.json 에서 읽는다.
  결과는 Result/adaptive_campaign/off_cutoff_results.json 에 누적.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

CELL = sys.argv[1]
TIME_LIMIT = int(sys.argv[2])
OUT_ROOT = REPO / "Result" / "adaptive_campaign"
RESULTS = OUT_ROOT / "off_cutoff_results.json"

# campaign_run 은 import 시 sys.argv 를 읽으므로 형식만 맞춰 둔다
sys.argv = ["campaign_run.py", "unused.json", str(TIME_LIMIT)]
from scratchpad import campaign_run  # noqa: E402
from scratchpad import milp_adaptive_flat as engine_z  # noqa: E402
from Src.data import load_instance  # noqa: E402


def bound_trajectory(log_path: Path) -> list[list[float]]:
    """Gurobi 로그의 B&B 진행 줄에서 (시간, BestBd) 를 뽑는다."""
    out = []
    for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        tok = line.split()
        if len(tok) < 5 or not re.fullmatch(r"\d+s", tok[-1]):
            continue
        try:
            out.append([float(tok[-1][:-1]), float(tok[-4])])
        except ValueError:
            continue
    return out


def main():
    prev = {r["id"]: r for r in json.loads((OUT_ROOT / "campaign_results.json").read_text(encoding="utf-8"))}[CELL]
    joint_obj = float(prev["joint"]["obj"])
    cutoff = joint_obj + 0.5
    data_dir = OUT_ROOT / CELL / "data"
    log = OUT_ROOT / CELL / "gurobi_off_cutoff.log"
    if log.exists():
        log.unlink()

    shim = campaign_run.make_shim(data_dir, "off", log)
    shim.TIME_LIMIT = TIME_LIMIT
    shim.MIP_FOCUS = 3
    shim.USE_OBJECTIVE_CUTOFF = True
    shim.OBJECTIVE_CUTOFF = cutoff
    shim.COMPUTE_LP_RELAXATION_BOUND = False   # LP 는 이미 기록돼 있음

    inst = load_instance(shim)
    t0 = time.time()
    sol = engine_z.solve_milp(inst, shim)
    s = sol.summary
    status = int(s["status"])
    bound = s.get("best_bound")
    found = s.get("objective")

    if status == 6:
        verdict = "PROVEN: off 최적 >= %.1f > joint %.1f -> 이득 > 0" % (cutoff, joint_obj)
        gain_lb = cutoff - joint_obj
    elif found is not None:
        verdict = "off 에 %.1f 짜리 정적 해 존재 -> 600초 이득(%.1f)은 탐색 부족" % (found, prev["gain_point"])
        gain_lb = 0.0
    else:
        gain_lb = max(0.0, (bound or 0.0) - joint_obj)
        verdict = "미결: bound %.1f, joint %.1f 까지 %.1f 남음" % (bound or float("nan"), joint_obj, joint_obj - (bound or 0.0))

    row = {
        "id": CELL, "time_limit": TIME_LIMIT, "cutoff": cutoff, "joint_obj": joint_obj,
        "prev_off_obj": prev["off"]["obj"], "prev_off_bound": prev["off"]["bound"],
        "status": status, "status_name": s.get("status_name"), "found_obj": found, "bound": bound,
        "runtime": round(float(s.get("runtime_seconds", 0)), 1), "wall": round(time.time() - t0, 1),
        "nodes": s.get("node_count"), "gain_lb": round(gain_lb, 1),
        "gain_lb_pct": round(100.0 * gain_lb / float(prev["off"]["obj"]), 2), "verdict": verdict,
        "trajectory": bound_trajectory(log) if log.exists() else [],
    }
    done = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else []
    done = [r for r in done if not (r["id"] == CELL and r["time_limit"] == TIME_LIMIT)]
    done.append(row)
    RESULTS.write_text(json.dumps(done, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(">>> %s: %s (bound %s, %ss)" % (CELL, verdict, bound, row["runtime"]), flush=True)


if __name__ == "__main__":
    main()
