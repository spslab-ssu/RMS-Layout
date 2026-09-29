# -*- coding: utf-8 -*-
"""adaptive layout 정식화 3종 동일조건 비교.

  1) sh_network   : 서훈 network adaptive (main 브랜치 Src/models/network_adaptive.py)
                    전이 arc z[p_prev, p_next, t, j_prev, l_prev, j_next, l_next]
  2) dk_z         : 우리 z 집계 (Src/milp_adaptive.py, ADAPTIVE_MODE=joint)
                    전이 arc z[k, p, j', j, l, t]
  3) dk_w         : 우리 Saffar식 w (scratchpad/saffar_w_adaptive.py, joint)
                    논문 x,s,y + 이동 이진변수 w[k, p, j, t]

공정성 조건: 같은 인스턴스, 이동비 0, 같은 시간제한, seed 0, warm start 없음,
            MIPGap 0, LP relaxation bound 계산, **반드시 순차 실행**(Gurobi 16스레드 독점).

사용법: python scratchpad/compare_three_adaptive.py [DATASET] [TIME_LIMIT] [TAG]
결과:   Result/<DATASET>_three_way/summary_<TAG>.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import config  # noqa: E402
from Src.data import load_instance  # noqa: E402
from scratchpad import milp_adaptive_flat as milp_adaptive  # noqa: E402  (Src/milp_adaptive.py 사본 + 거리단가 옵션)
from scratchpad import saffar_w_adaptive  # noqa: E402
from scratchpad import network_adaptive_sh  # noqa: E402

DATASET = sys.argv[1] if len(sys.argv) > 1 else "multi_part"
TIME_LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 600
TAG = sys.argv[3] if len(sys.argv) > 3 else "run"

DATA = REPO / "Data" / DATASET
OUT = REPO / "Result" / (DATASET + "_three_way")

# (표시이름, solve 함수, 이 모델에만 주는 설정)
# 이동비는 서훈 모델 정의로 통일한다: 이동 1건 비용 = UNIT x 거리 (기계 종류 무관).
UNIT = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0

MODELS = [
    ("sh_network", network_adaptive_sh.solve_milp, {
        "RELOCATION_COST_PER_DISTANCE": UNIT,
        "RELOCATION_FIXED_COST": 0.0,
        "MAX_RELOCATION_DISTANCE": None,       # 거리 제한 없음
        "NETWORK_BINARY_ARCS": False,          # 전이 arc 연속 — 우리 z와 맞춤(유리한 쪽)
    }),
    ("dk_z", milp_adaptive.solve_milp, {
        "ADAPTIVE_MODE": "joint", "MOVE_COST_FLAT": UNIT,
    }),
    ("dk_w", saffar_w_adaptive.solve_milp, {
        "ADAPTIVE_MODE": "joint", "MOVE_COST_FLAT": UNIT,
        "SAFFAR_BALANCE_EQ": True, "SAFFAR_W_BINARY": True,
    }),
]


def _count_events(sol):
    """세 모델의 이동/재구성 건수를 같은 기준으로 센다.

    sh 모델은 reconfigurations 리스트 안에 이동까지 섞어 넣고 from_location 키를 갖는다.
    dk 모델들은 relocations / reconfigurations를 따로 갖는다.
    반환: (이동 건수, 재구성 건수, 이동+재구성 동시 건수)
    """
    reconf_rows = list(sol.reconfigurations or [])
    reloc_rows = list(getattr(sol, "relocations", None) or [])
    mixed = [r for r in reconf_rows if "from_location" in r]
    if mixed:   # sh 모델
        moved = [r for r in mixed if r["from_location"] != r["to_location"]]
        changed = [r for r in mixed if r["from_configuration"] != r["to_configuration"]]
        both = [r for r in moved if r["from_configuration"] != r["to_configuration"]]
        return len(moved), len(changed), len(both)
    n_both = sol.summary.get("n_move_and_reconfig")
    if n_both is None and reloc_rows:   # z 모델: 같은 (도착위치, 기간)에 이동과 재구성이 함께면 동시
        arrivals = {(r.get("to_location", r.get("location")), r["period"]) for r in reloc_rows}
        n_both = sum(1 for r in reconf_rows if (r.get("location"), r["period"]) in arrivals)
    return len(reloc_rows), len(reconf_rows), n_both


def make_shim(**over) -> SimpleNamespace:
    s = SimpleNamespace(**{k: getattr(config, k) for k in dir(config) if k.isupper()})
    s.PROBLEM_NAME = DATASET
    for key, fn in [
        ("LOCATION_FILE", "locations.csv"), ("CONFIGURATION_FILE", "configurations.csv"),
        ("PRODUCTION_RATE_FILE", "production_rates.csv"), ("DEMAND_FILE", "demands.csv"),
        ("PARAMETER_FILE", "parameters.csv"), ("SHARED_RESOURCE_FILE", "shared_resources.csv"),
        ("RESOURCE_REQUIREMENT_FILE", "resource_requirements.csv"), ("MODULE_COST_FILE", "module_costs.csv"),
    ]:
        setattr(s, key, DATA / fn)
    # 공통 조건
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
    s.ALPHA = 0.0
    s.BETA = 0.0
    s.MOVE_COST_FLAT = None
    s.GUROBI_PARAMS = None          # sh 모델은 GUROBI_PARAMS를 안 읽으므로 세 모델 모두 미사용(Seed 기본 0)
    for k, v in over.items():
        setattr(s, k, v)
    return s


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("=" * 70, flush=True)
    print("adaptive 정식화 3종 비교  dataset=%s  TIME_LIMIT=%ds  이동비=거리당 %s (서훈 정의로 통일)  순차실행" % (DATASET, TIME_LIMIT, UNIT), flush=True)
    print("=" * 70, flush=True)
    rows = []
    for name, solver, over in MODELS:
        shim = make_shim(**over)
        inst = load_instance(shim)
        print("\n\n##### [%s] 시작 (P=%d |F|=%d T=%d) #####"
              % (name, len(inst.install_locations), len(inst.feasible_pairs), len(inst.periods)), flush=True)
        t0 = time.time()
        sol = solver(inst, shim)
        wall = time.time() - t0
        s = sol.summary
        cb = sol.cost_breakdown
        n_reloc, n_reconf, n_both = _count_events(sol)
        n_bin = s.get("num_binary_vars")
        if n_bin is None:   # sh 모델은 이진 수를 기록하지 않는다 -> s + x 로 계산
            n_bin = len(inst.install_locations) * len(inst.feasible_pairs) * (len(inst.periods) + 1)
        row = {
            "model": name,
            "status": s.get("status_name"),
            "objective": s.get("objective"),
            "best_bound": s.get("best_bound"),
            "gap": s.get("mip_gap"),
            "lp_bound": s.get("lp_relaxation_bound"),
            "runtime_s": round(float(s.get("runtime_seconds", 0)), 1),
            "wall_s": round(wall, 1),
            "build_s": round(wall - float(s.get("runtime_seconds", 0)), 1),
            "num_vars": s.get("num_vars"),
            "num_binary": n_bin,
            "num_binary_measured": s.get("num_binary_vars") is not None,
            "num_constraints": s.get("num_constraints"),
            "nodes": s.get("node_count"),
            "purchase": cb.get("purchase_cost"),
            "reconfig": cb.get("reconfiguration_cost"),
            "relocation": cb.get("relocation_cost"),
            "mhc": cb.get("material_handling_cost"),
            "n_machines": len(sol.purchased_machines),
            "n_reconfigurations": n_reconf,
            "n_relocations": n_reloc,
            "n_move_and_reconfig": n_both,
        }
        rows.append(row)
        print("\n----- [%s] 결과 -----" % name, flush=True)
        print("  %s  obj=%s  bound=%s  gap=%s  LP=%s" % (
            row["status"], row["objective"], row["best_bound"], row["gap"], row["lp_bound"]), flush=True)
        print("  시간: solve %ss / 모델생성+LP %ss / 전체 %ss" % (
            row["runtime_s"], row["build_s"], row["wall_s"]), flush=True)
        print("  크기: 변수 %s / 이진 %s / 제약 %s / 노드 %s" % (
            row["num_vars"], row["num_binary"], row["num_constraints"], row["nodes"]), flush=True)
        print("  비용: 구매 %s / 재구성 %s / 이동 %s / MHC %s" % (
            row["purchase"], row["reconfig"], row["relocation"], row["mhc"]), flush=True)
        print("  해  : 기계 %s대 / 재구성 %s회 / 이동 %s회 / 동시 %s회" % (
            row["n_machines"], row["n_reconfigurations"], row["n_relocations"],
            row["n_move_and_reconfig"]), flush=True)
        (OUT / ("summary_%s.json" % TAG)).write_text(
            json.dumps(rows, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    print("\n\n" + "=" * 96, flush=True)
    print("==== adaptive 정식화 3종 비교 (%s, 이동비 거리당 %s, 제한 %ds, 순차) ====" % (DATASET, UNIT, TIME_LIMIT))
    print("%-12s %-11s %10s %10s %8s %12s %8s %9s %8s %7s" % (
        "model", "status", "obj", "bound", "gap", "LP", "solve", "변수", "이진", "이동"))
    print("-" * 96)
    for r in rows:
        g = r["gap"]
        print("%-12s %-11s %10s %10s %8s %12s %8s %9s %8s %7s" % (
            r["model"], r["status"], r["objective"], r["best_bound"],
            ("%.2f%%" % (g * 100)) if g is not None else "-",
            r["lp_bound"], r["runtime_s"], r["num_vars"], r["num_binary"], r["n_relocations"]))
    print("-" * 96)
    print("기준선: multi_part off(위치고정) 최적값 35,775 — base 모델로 48.1시간 걸려 증명된 값")


if __name__ == "__main__":
    main()
