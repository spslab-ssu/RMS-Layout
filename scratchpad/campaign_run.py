# -*- coding: utf-8 -*-
"""adaptive 이득 탐색 캠페인 — 순차 실행기.

큐(JSON 리스트)의 시나리오마다:
  1) 인스턴스 생성 (campaign_gen)
  2) MHC 해석적 하한 계산 (솔버 없음): 라우트별 최단 도크→슬롯들→도크 경로(재방문 허용 DP) × 수요 × c_mh
  3) off  (dk_w, ADAPTIVE_MODE=off)     TIME_LIMIT초
  4) joint(dk_w, ADAPTIVE_MODE=joint, 이동비 0)  TIME_LIMIT초
  5) 이득 구간 [LB_off - UB_adp, UB_off - LB_adp] 기록, 누적 JSON/CSV 갱신
한 번에 solve 하나만 돈다 (Gurobi 16스레드 독점). 이미 결과가 있는 id는 건너뛴다(재개 가능).

사용법: python scratchpad/campaign_run.py QUEUE.json [TIME_LIMIT=300] [ONLY_IDS=a,b,c]
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import config  # noqa: E402
from Src.data import load_instance  # noqa: E402
from scratchpad import campaign_gen  # noqa: E402
from scratchpad import saffar_w_adaptive as engine_w  # noqa: E402
from scratchpad import milp_adaptive_flat as engine_z  # noqa: E402
engine = engine_w  # 기본 엔진 (spec["engine"]="z"로 시나리오별 교체)
from Src.output import save_solution  # noqa: E402

QUEUE = Path(sys.argv[1])
TIME_LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 300
ONLY = set(sys.argv[3].split(",")) if len(sys.argv) > 3 and sys.argv[3] else None
OUT_ROOT = campaign_gen.OUT_ROOT
RESULTS = OUT_ROOT / "campaign_results.json"


def make_shim(data_dir: Path, mode: str, logfile: Path) -> SimpleNamespace:
    s = SimpleNamespace(**{k: getattr(config, k) for k in dir(config) if k.isupper()})
    s.PROBLEM_NAME = data_dir.parent.name
    for key, fn in [("LOCATION_FILE", "locations.csv"), ("CONFIGURATION_FILE", "configurations.csv"),
                    ("PRODUCTION_RATE_FILE", "production_rates.csv"), ("DEMAND_FILE", "demands.csv"),
                    ("PARAMETER_FILE", "parameters.csv"), ("SHARED_RESOURCE_FILE", "shared_resources.csv"),
                    ("RESOURCE_REQUIREMENT_FILE", "resource_requirements.csv"), ("MODULE_COST_FILE", "module_costs.csv")]:
        setattr(s, key, data_dir / fn)
    s.SHARED_RESOURCE_MODE = "off"
    s.ALLOW_RECONFIGURATION = True
    s.USE_WARM_START = False
    s.USE_OBJECTIVE_CUTOFF = False
    s.USE_MIN_MACHINE_CUTS = False
    s.MINIMIZE_SIZING = False
    s.FIXED_PURCHASES = None
    s.COMPUTE_LP_RELAXATION_BOUND = True
    s.OUTPUT_FLAG = 1
    s.TIME_LIMIT = TIME_LIMIT
    s.MIP_GAP = 0.0
    s.MIP_FOCUS = None
    s.ADAPTIVE_MODE = mode
    s.ALPHA = 0.0
    s.BETA = 0.0
    s.MOVE_COST_FLAT = 0.0          # 이동비 0 = 이득의 상한 (spec.move_cost_flat로 덮어씀)
    s.SAFFAR_BALANCE_EQ = True
    s.SAFFAR_W_BINARY = True
    s.GUROBI_PARAMS = {"Seed": 0, "LogFile": str(logfile)}
    return s


def mhc_lower_bound(inst) -> dict:
    """라우트별 도크→(op 수만큼 슬롯)→도크 최단 경로(슬롯 재방문 허용 DP) × 수요 × c_mh. 유효 하한."""
    P = inst.install_locations
    D = inst.distance
    c = float(inst.parameters["material_handling_cost"])
    out = {"total": 0.0, "by_part": {}}
    for part, routes in inst.part_routes.items():
        route = routes[0]
        k = len(route) - 2  # 실제 op 수
        # dp[p] = start->...->p 최단 (p에 i번째 op 배치)
        dp = {p: D[inst.start_location, p] for p in P}
        for _ in range(k - 1):
            dp = {q: min(dp[p] + D[p, q] for p in P if p != q) for q in P}
        best = min(dp[p] + D[p, inst.end_location] for p in P)
        dem = sum(inst.part_demand.get((part, t), 0.0) for t in inst.periods)
        out["by_part"][part] = {"min_path": best, "total_demand": dem, "mhc_lb": best * dem * c}
        out["total"] += best * dem * c
    return out


def run_one(spec: dict) -> dict:
    sid = spec["id"]
    data_dir = campaign_gen.generate(spec)
    row = {"id": sid, "base": spec.get("base"), "hypothesis": spec.get("hypothesis", ""), "time_limit": TIME_LIMIT}
    off_dir = None
    for mode in ("off", "joint"):
        shim = make_shim(data_dir, mode, OUT_ROOT / sid / ("gurobi_%s.log" % mode))
        # 이동비 정의 두 가지. spec에 alpha/beta가 있으면 논문식 C_j(alpha + beta*D),
        # 없으면 기존대로 flat 단가 x 거리 (MOVE_COST_FLAT이 None이 아니면 엔진이 flat 분기를 탄다).
        if "alpha" in spec or "beta" in spec:
            shim.MOVE_COST_FLAT = None
            shim.ALPHA = float(spec.get("alpha", 0.0))
            shim.BETA = float(spec.get("beta", 0.0))
        else:
            shim.MOVE_COST_FLAT = float(spec.get("move_cost_flat", 0.0))   # 손익분기 스윕용
        if mode == "joint" and off_dir is not None:      # off 해를 joint의 MIP start로
            shim.USE_WARM_START = True
            shim.WARM_START_DIR = off_dir
        inst = load_instance(shim)
        if mode == "off":
            lb = mhc_lower_bound(inst)
            row["mhc_lb"] = round(lb["total"], 1)
            row["mhc_lb_detail"] = lb["by_part"]
            row["P"] = len(inst.install_locations); row["F"] = len(inst.feasible_pairs); row["T"] = len(inst.periods)
            row["ops"] = inst.operations
        t0 = time.time()
        eng = engine_z if spec.get("engine") == "z" else engine_w
        sol = eng.solve_milp(inst, shim)
        wall = time.time() - t0
        s, cb = sol.summary, sol.cost_breakdown
        row[mode] = {
            "status": s.get("status_name"), "obj": s.get("objective"), "bound": s.get("best_bound"),
            "gap": s.get("mip_gap"), "lp": s.get("lp_relaxation_bound"), "runtime": round(float(s.get("runtime_seconds", 0)), 1),
            "wall": round(wall, 1), "vars": s.get("num_vars"), "binary": s.get("num_binary_vars"),
            "purchase": cb.get("purchase_cost"), "reconfig": cb.get("reconfiguration_cost"),
            "mhc": cb.get("material_handling_cost"), "move": cb.get("relocation_cost"),
            "machines": len(sol.purchased_machines), "reconfigs": len(sol.reconfigurations),
            "relocations": len(getattr(sol, "relocations", []) or []),
            "move_distance": round(sum(float(r.get("distance", 0)) for r in (getattr(sol, "relocations", []) or [])), 1),
        }
        row["move_cost_flat"] = float(spec.get("move_cost_flat", 0.0))
        print("    [%s] %s obj=%s bound=%s gap=%s (%ss)" % (mode, row[mode]["status"], row[mode]["obj"],
              row[mode]["bound"], row[mode]["gap"], row[mode]["runtime"]), flush=True)
        if mode == "off" and sol.purchased_machines:      # joint warm start용으로 저장
            off_dir = OUT_ROOT / sid / "off_solution"
            off_dir.mkdir(parents=True, exist_ok=True)
            try:
                save_solution(sol, off_dir)
                # 내용 없는 CSV(BOM만 있는 3바이트짜리)는 warm_start의 pandas 파서를 깨뜨린다 -> 삭제
                for fp in off_dir.glob("*.csv"):
                    if fp.stat().st_size < 10:
                        fp.unlink()
            except Exception as e:
                print("    (off 해 저장 실패, warm start 생략: %r)" % e, flush=True)
                off_dir = None
    o, a = row["off"], row["joint"]
    if o["obj"] is not None and a["obj"] is not None:
        gain_lb = max(0.0, (o["bound"] or 0) - a["obj"])
        gain_ub = o["obj"] - (a["bound"] or 0)
        row["gain_interval"] = [round(gain_lb, 1), round(gain_ub, 1)]
        row["gain_point"] = round(o["obj"] - a["obj"], 1)
        row["gain_pct_point"] = round(100.0 * (o["obj"] - a["obj"]) / o["obj"], 2)
        row["gain_pct_lb"] = round(100.0 * gain_lb / o["obj"], 2)
        row["mhc_slack_off"] = round(o["mhc"] - row["mhc_lb"], 1) if o.get("mhc") is not None else None
        row["delta"] = {k: round((o.get(k) or 0) - (a.get(k) or 0), 1) for k in ("purchase", "reconfig", "mhc")}
    return row


def main():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    done = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else []
    done_ids = {r["id"] for r in done}
    print("캠페인: %d 시나리오, TIME_LIMIT=%ds, 이미 완료 %d" % (len(queue), TIME_LIMIT, len(done_ids)), flush=True)
    for i, spec in enumerate(queue, 1):
        if spec["id"] in done_ids or (ONLY and spec["id"] not in ONLY):
            continue
        print("\n=== [%d/%d] %s (%s) ===" % (i, len(queue), spec["id"], spec.get("hypothesis", "")[:60]), flush=True)
        t0 = time.time()
        try:
            row = run_one(spec)
        except Exception as e:  # 한 시나리오 실패가 캠페인을 멈추지 않게
            row = {"id": spec["id"], "error": repr(e)}
            print("    !! 실패:", repr(e), flush=True)
        row["elapsed"] = round(time.time() - t0, 1)
        done.append(row)
        RESULTS.write_text(json.dumps(done, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        _write_csv(done)
        if "gain_interval" in row:
            print("    >>> 이득 %s (%.2f%%)  구간 %s  MHC여유(off) %s  Δ구매 %s Δ재구성 %s ΔMHC %s" % (
                row["gain_point"], row["gain_pct_point"], row["gain_interval"], row.get("mhc_slack_off"),
                row["delta"]["purchase"], row["delta"]["reconfig"], row["delta"]["mhc"]), flush=True)
    print("\n캠페인 끝. 결과:", RESULTS, flush=True)


def _write_csv(rows):
    cols = ["id", "base", "P", "F", "T", "off_status", "off_obj", "off_bound", "off_gap", "joint_status", "joint_obj",
            "joint_bound", "joint_gap", "gain_point", "gain_pct_point", "gain_lb", "gain_ub", "gain_pct_lb",
            "mhc_lb", "mhc_slack_off", "d_purchase", "d_reconfig", "d_mhc", "off_machines", "joint_machines",
            "joint_relocations", "off_runtime", "joint_runtime", "error"]
    with open(OUT_ROOT / "campaign_results.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
        for r in rows:
            o, a = r.get("off", {}), r.get("joint", {})
            gi = r.get("gain_interval", [None, None]); d = r.get("delta", {})
            w.writerow({
                "id": r["id"], "base": r.get("base"), "P": r.get("P"), "F": r.get("F"), "T": r.get("T"),
                "off_status": o.get("status"), "off_obj": o.get("obj"), "off_bound": o.get("bound"), "off_gap": o.get("gap"),
                "joint_status": a.get("status"), "joint_obj": a.get("obj"), "joint_bound": a.get("bound"), "joint_gap": a.get("gap"),
                "gain_point": r.get("gain_point"), "gain_pct_point": r.get("gain_pct_point"), "gain_lb": gi[0], "gain_ub": gi[1],
                "gain_pct_lb": r.get("gain_pct_lb"), "mhc_lb": r.get("mhc_lb"), "mhc_slack_off": r.get("mhc_slack_off"),
                "d_purchase": d.get("purchase"), "d_reconfig": d.get("reconfig"), "d_mhc": d.get("mhc"),
                "off_machines": o.get("machines"), "joint_machines": a.get("machines"), "joint_relocations": a.get("relocations"),
                "off_runtime": o.get("runtime"), "joint_runtime": a.get("runtime"), "error": r.get("error"),
            })


if __name__ == "__main__":
    main()
