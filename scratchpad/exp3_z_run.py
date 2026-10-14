# -*- coding: utf-8 -*-
"""팀 Exp3 인스턴스를 dk z 모델(off → joint)로 푼다. 2026-10-13.

Exp3(main 브랜치)와 같게 맞춘 것
  - 데이터: main Data/rmt_tables/table_1 (= dk Data/multi_part 의 configurations/production_rates, 바이트 동일),
            Data/locations/<layout>.csv, Data/demands/exp_3/p5/<id>.csv, Data/parameters/exp_3/period_<T>.csv
            + 입구/출구 위치(location type start/end)를 dk 형식대로 parameters 에 명시
  - 이동비: 거리당 1.0 (MOVE_COST_FLAT = 1.0, 고정비 0, 거리 제한 없음) — Exp3 의 RELOCATION_COST_PER_DISTANCE = 1.0
  - 재구성: 같은 machine type 안에서만, 50/25. 공유자원 off.
검증: z joint 의 LP relaxation 이 network_adaptive 의 루트 LP(26,760.99)와 같으면 같은 문제로 옮긴 것.

사용법: python scratchpad/exp3_z_run.py EXP_ID LAYOUT OFF_TIME JOINT_TIME
결과: Result/exp3_z/<EXP_ID>_<LAYOUT>/ (data, off_solution, joint_solution, gurobi_*.log), results.json
"""
from __future__ import annotations

import csv
import json
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MAIN = REPO.parent / "RMS-Layout-main"
sys.path.insert(0, str(REPO))

EXP_ID, LAYOUT = sys.argv[1], sys.argv[2]
OFF_TIME, JOINT_TIME = float(sys.argv[3]), float(sys.argv[4])
# 이어 풀기: 5번째 인자로 저장된 해 폴더를 주면 off 를 건너뛰고 그 해로 warm start 한 joint 만 푼다 (6번째 인자 = 결과 이름표)
RESUME_DIR = Path(sys.argv[5]) if len(sys.argv) > 5 else None
TAG = sys.argv[6] if len(sys.argv) > 6 else "joint2"

sys.argv = ["campaign_run.py", "unused.json", "600"]   # campaign_run 은 import 시 argv 를 읽는다
from scratchpad import campaign_run  # noqa: E402
from scratchpad import milp_adaptive_flat as engine_z  # noqa: E402
from Src.data import load_instance  # noqa: E402
from Src.output import save_solution  # noqa: E402
import Src.warm_start as _ws  # noqa: E402

# warm start 에는 구매(x)·상태(s)만 넣는다. 저장된 흐름(v, f)은 소수점 6자리 반올림이라
# 흐름이 쪼개진 해에서는 등식 제약이 1e-6 넘게 어긋나 Gurobi 가 시작해를 버린다 (2026-10-13 재현).
_ws._apply_material_flows = lambda path, f: 0
_orig_states = _ws._apply_machine_states


class _NoKeys(dict):
    def __contains__(self, key):
        return False


_ws._apply_machine_states = lambda path, s, v: _orig_states(path, s, _NoKeys())

OUT = REPO / "Result" / "exp3_z" / ("%s_%s" % (EXP_ID, LAYOUT))
RESULTS = REPO / "Result" / "exp3_z" / "results.json"
# network(main) 결과: 같은 off 문제이므로 그대로 비교 기준으로 쓴다 (p5_low_t4_s01, layout_27, 62.7시간)
NETWORK_REF = {"p5_low_t4_s01|layout_27": {"obj": 29765.0, "bound": 29591.3759, "lp": 26787.9766,
                                           "adaptive_root_lp": 26760.99}}


def build_data() -> Path:
    row = next(r for r in csv.DictReader(open(MAIN / "exp_3" / "manifest.csv", encoding="utf-8-sig"))
               if r["experiment_id"] == EXP_ID and r["layout_name"] == LAYOUT)
    d = OUT / "data"
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy(MAIN / "Data" / "locations" / ("%s.csv" % LAYOUT), d / "locations.csv")
    for f in ("configurations.csv", "production_rates.csv"):
        shutil.copy(MAIN / "Data" / "rmt_tables" / row["rmt_table"] / f, d / f)
    shutil.copy(MAIN / row["demand_file"], d / "demands.csv")
    for f in ("shared_resources.csv", "resource_requirements.csv", "resource_capacities.csv"):
        if (REPO / "Data" / "multi_part" / f).exists():
            shutil.copy(REPO / "Data" / "multi_part" / f, d / f)
    locs = list(csv.DictReader(open(d / "locations.csv", encoding="utf-8-sig")))
    start = next(l["location"] for l in locs if l["type"] == "start")
    end = next(l["location"] for l in locs if l["type"] == "end")
    params = list(csv.DictReader(open(MAIN / row["parameter_file"], encoding="utf-8-sig")))
    with open(d / "parameters.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["parameter", "value"])
        for p in params:
            w.writerow([p["parameter"], p["value"]])
        w.writerow(["start_location", start])
        w.writerow(["end_location", end])
    return d


def shim_for(data_dir, mode, limit, warm=None, tag=None):
    s = campaign_run.make_shim(data_dir, mode, OUT / ("gurobi_%s.log" % (tag or mode)))
    if tag:   # 해가 좋아질 때마다 .sol 파일로 저장 (중간에 꺼져도 최선해가 남음)
        (OUT / ("%s_inc" % tag)).mkdir(parents=True, exist_ok=True)
        s.GUROBI_PARAMS["SolFiles"] = str(OUT / ("%s_inc" % tag) / "inc")
    s.TIME_LIMIT = limit
    s.MIP_GAP = 0.0001                 # Exp3 와 같은 기준
    s.MOVE_COST_FLAT = 1.0             # Exp3: 거리당 1.0
    s.ALLOW_RECONFIGURATION = True
    s.COMPUTE_LP_RELAXATION_BOUND = True
    if mode == "joint":
        s.MIP_FOCUS = 1                # warm start 해 주변에서 더 좋은 해 찾기에 집중
    if warm is not None:
        s.USE_WARM_START = True
        s.WARM_START_DIR = warm
    return s


def record(mode, sol, wall):
    s, cb = sol.summary, sol.cost_breakdown or {}
    rel = getattr(sol, "relocations", []) or []
    return {"status": s.get("status_name"), "obj": s.get("objective"), "bound": s.get("best_bound"),
            "gap": s.get("mip_gap"), "lp": s.get("lp_relaxation_bound"), "runtime": round(float(s.get("runtime_seconds", 0)), 1),
            "wall": round(wall, 1), "vars": s.get("num_vars"), "binary": s.get("num_binary_vars"), "rows": s.get("num_constraints"),
            "nodes": s.get("node_count"), "purchase": cb.get("purchase_cost"), "reconfig": cb.get("reconfiguration_cost"),
            "mhc": cb.get("material_handling_cost"), "move": cb.get("relocation_cost"),
            "machines": len(sol.purchased_machines or []), "relocations": len(rel),
            "move_distance": round(sum(float(r.get("distance", 0)) for r in rel), 1)}


def save_results(res):
    allr = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    allr["%s|%s" % (EXP_ID, LAYOUT)] = res
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(allr, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def resume_joint():
    """저장된 해(RESUME_DIR)로 warm start 해서 joint 만 다시 푼다."""
    data_dir = OUT / "data"
    allr = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    res = allr.get("%s|%s" % (EXP_ID, LAYOUT), {"exp_id": EXP_ID, "layout": LAYOUT,
                                                "network_ref": NETWORK_REF.get("%s|%s" % (EXP_ID, LAYOUT))})
    res.setdefault("resumes", []).append({"tag": TAG, "from": str(RESUME_DIR), "started": time.strftime("%Y-%m-%d %H:%M:%S")})
    save_results(res)
    t0 = time.time()
    sh = shim_for(data_dir, "joint", JOINT_TIME, RESUME_DIR, tag=TAG)
    sh.COMPUTE_LP_RELAXATION_BOUND = False     # 이미 계산함 (25,565.43)
    sol = engine_z.solve_milp(load_instance(sh), sh)
    res[TAG] = record(TAG, sol, time.time() - t0)
    if sol.purchased_machines:
        jd = OUT / ("%s_solution" % TAG)
        jd.mkdir(exist_ok=True)
        save_solution(sol, jd)
    # 이득 구간: joint 실행들 중 가장 좋은 해와 가장 높은 하한을 함께 쓴다
    ref = res.get("network_ref") or {}
    off = res.get("off", {})
    off_lb = max(x for x in (ref.get("bound"), off.get("bound")) if x is not None)
    off_ub = min(x for x in (ref.get("obj"), off.get("obj")) if x is not None)
    runs = [res[k] for k in res if (k == "joint" or k.startswith("joint")) and isinstance(res[k], dict) and res[k].get("obj") is not None]
    j_obj = min(r["obj"] for r in runs)
    j_bnd = max(r["bound"] or 0 for r in runs)
    res["gain_interval"] = [round(max(0.0, off_lb - j_obj), 1), round(off_ub - j_bnd, 1)]
    res["gain_pct_interval"] = [round(100 * res["gain_interval"][0] / off_ub, 3), round(100 * res["gain_interval"][1] / off_ub, 3)]
    save_results(res)
    print(">>> %s:" % TAG, res[TAG], "gain", res.get("gain_interval"), flush=True)


def main():
    if RESUME_DIR is not None:
        resume_joint()
        return
    data_dir = build_data()
    res = {"exp_id": EXP_ID, "layout": LAYOUT, "network_ref": NETWORK_REF.get("%s|%s" % (EXP_ID, LAYOUT))}
    # off
    t0 = time.time()
    sh = shim_for(data_dir, "off", OFF_TIME)
    sol = engine_z.solve_milp(load_instance(sh), sh)
    res["off"] = record("off", sol, time.time() - t0)
    warm = None
    if sol.purchased_machines:
        warm = OUT / "off_solution"
        warm.mkdir(exist_ok=True)
        save_solution(sol, warm)
        for fp in warm.glob("*.csv"):          # 빈 표(BOM만 있는 파일)는 warm start 파서를 깨뜨린다
            if fp.stat().st_size < 10:
                fp.unlink()
    save_results(res)
    print(">>> off:", res["off"], flush=True)
    # joint (off 해로 warm start)
    t0 = time.time()
    sh = shim_for(data_dir, "joint", JOINT_TIME, warm)
    sol = engine_z.solve_milp(load_instance(sh), sh)
    res["joint"] = record("joint", sol, time.time() - t0)
    if sol.purchased_machines:
        jd = OUT / "joint_solution"
        jd.mkdir(exist_ok=True)
        save_solution(sol, jd)
    # 이득 구간: off 최적값은 network 증명 하한과 z off 하한 중 큰 값 이상, 찾은 해 중 작은 값 이하
    ref = res["network_ref"] or {}
    off_lb = max(x for x in (ref.get("bound"), res["off"]["bound"]) if x is not None)
    off_ub = min(x for x in (ref.get("obj"), res["off"]["obj"]) if x is not None)
    j = res["joint"]
    if j["obj"] is not None:
        res["gain_interval"] = [round(max(0.0, off_lb - j["obj"]), 1), round(off_ub - (j["bound"] or 0), 1)]
        res["gain_pct_interval"] = [round(100 * res["gain_interval"][0] / off_ub, 3), round(100 * res["gain_interval"][1] / off_ub, 3)]
    save_results(res)
    print(">>> joint:", res["joint"], "gain", res.get("gain_interval"), flush=True)


if __name__ == "__main__":
    main()
