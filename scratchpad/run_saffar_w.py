# -*- coding: utf-8 -*-
"""Saffar식 w 정식화 실행기 — config.py를 건드리지 않고 shim으로 돌린다.

사용법:
  python scratchpad/run_saffar_w.py DATASET TIME_LIMIT MODES [S_FLAG] [BETA] [TAG]
예:
  python scratchpad/run_saffar_w.py single_part 120 off,separate,joint 1 0 sanity
  python scratchpad/run_saffar_w.py multi_part  600 off,separate,joint 1 0 main
결과: Result/<DATASET>_saffar_w/summary_<TAG>.json + gurobi_<mode>_<TAG>.log
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
from scratchpad import saffar_w_adaptive  # noqa: E402

DATASET = sys.argv[1] if len(sys.argv) > 1 else "multi_part"
TIME_LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 600
MODES = (sys.argv[3] if len(sys.argv) > 3 else "off,separate,joint").split(",")
USE_S = bool(int(sys.argv[4])) if len(sys.argv) > 4 else True
BETA = float(sys.argv[5]) if len(sys.argv) > 5 else 0.0
TAG = sys.argv[6] if len(sys.argv) > 6 else "run"

DATA = REPO / "Data" / DATASET
OUT = REPO / "Result" / (DATASET + "_saffar_w")


def make_shim(mode: str, logfile: Path) -> SimpleNamespace:
    shim = SimpleNamespace(**{k: getattr(config, k) for k in dir(config) if k.isupper()})
    shim.PROBLEM_NAME = DATASET
    for key, fn in [
        ("LOCATION_FILE", "locations.csv"),
        ("CONFIGURATION_FILE", "configurations.csv"),
        ("PRODUCTION_RATE_FILE", "production_rates.csv"),
        ("DEMAND_FILE", "demands.csv"),
        ("PARAMETER_FILE", "parameters.csv"),
        ("SHARED_RESOURCE_FILE", "shared_resources.csv"),
        ("RESOURCE_REQUIREMENT_FILE", "resource_requirements.csv"),
        ("MODULE_COST_FILE", "module_costs.csv"),
    ]:
        setattr(shim, key, DATA / fn)
    shim.SHARED_RESOURCE_MODE = "off"          # 공유자원 실험은 중단 — 항상 off
    shim.USE_WARM_START = False
    shim.USE_OBJECTIVE_CUTOFF = False
    shim.ALLOW_RECONFIGURATION = True
    shim.COMPUTE_LP_RELAXATION_BOUND = True
    shim.OUTPUT_FLAG = 1
    shim.TIME_LIMIT = TIME_LIMIT
    shim.MIP_GAP = 0.0
    shim.MIP_FOCUS = None
    shim.ADAPTIVE_MODE = mode
    shim.ALPHA = 0.0
    shim.BETA = BETA
    shim.SAFFAR_BALANCE_EQ = USE_S
    shim.SAFFAR_W_BINARY = True
    shim.GUROBI_PARAMS = {"Seed": 0, "LogFile": str(logfile)}
    return shim


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("dataset=%s  TIME_LIMIT=%ds  modes=%s  (S)=%s  beta=%s" % (DATASET, TIME_LIMIT, MODES, USE_S, BETA), flush=True)
    rows = []
    for mode in MODES:
        logfile = OUT / ("gurobi_%s_%s.log" % (mode, TAG))
        if logfile.exists():
            logfile.unlink()
        shim = make_shim(mode, logfile)
        inst = load_instance(shim)
        print("\n### %s 시작 (P=%d |F|=%d T=%d)" % (mode, len(inst.install_locations), len(inst.feasible_pairs), len(inst.periods)), flush=True)
        t0 = time.time()
        sol = saffar_w_adaptive.solve_milp(inst, shim)
        wall = time.time() - t0
        s = sol.summary
        row = {
            "mode": mode, "beta": BETA, "balance_eq_S": USE_S,
            "status": s.get("status_name"),
            "objective": s.get("objective"),
            "best_bound": s.get("best_bound"),
            "gap": s.get("mip_gap"),
            "lp_bound": s.get("lp_relaxation_bound"),
            "runtime_s": round(float(s.get("runtime_seconds", 0)), 1),
            "wall_s": round(wall, 1),
            "num_vars": s.get("num_vars"), "num_binary": s.get("num_binary_vars"),
            "num_constraints": s.get("num_constraints"), "nodes": s.get("node_count"),
            "purchase": sol.cost_breakdown.get("purchase_cost"),
            "reconfig": sol.cost_breakdown.get("reconfiguration_cost"),
            "mhc": sol.cost_breakdown.get("material_handling_cost"),
            "move": sol.cost_breakdown.get("relocation_cost"),
            "n_machines": s.get("n_machines"),
            "n_relocations": s.get("n_relocations"),
            "n_reconfigurations": s.get("n_reconfigurations"),
            "n_move_and_reconfig": s.get("n_move_and_reconfig"),
            "relocations": sol.relocations,
        }
        rows.append(row)
        print("    -> %s obj=%s bound=%s gap=%s LP=%s  %ss(wall %ss)" % (
            row["status"], row["objective"], row["best_bound"], row["gap"],
            row["lp_bound"], row["runtime_s"], row["wall_s"]), flush=True)
        print("    비용: 구매=%s 재구성=%s MHC=%s 이동=%s | 기계=%s 이동횟수=%s 재구성횟수=%s 동시=%s" % (
            row["purchase"], row["reconfig"], row["mhc"], row["move"],
            row["n_machines"], row["n_relocations"], row["n_reconfigurations"],
            row["n_move_and_reconfig"]), flush=True)
        print("    크기: 변수=%s 이진=%s 제약=%s 노드=%s" % (
            row["num_vars"], row["num_binary"], row["num_constraints"], row["nodes"]), flush=True)
        (OUT / ("summary_%s.json" % TAG)).write_text(
            json.dumps(rows, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    print("\n\n==== Saffar식 w 정식화: %s, 제한 %ds ====" % (DATASET, TIME_LIMIT))
    print("%-10s %-11s" % ("mode", "status"), end="")
    print("%10s %10s %8s %10s %8s %6s %6s" % ("obj", "bound", "gap", "LP", "time", "이동", "재구성"))
    for r in rows:
        gap = r["gap"]
        print("%-10s %-11s %10s %10s %8s %10s %8s %6s %6s" % (
            r["mode"], r["status"], r["objective"], r["best_bound"],
            ("%.2f%%" % (gap * 100)) if gap is not None else "-",
            r["lp_bound"], r["runtime_s"], r["n_relocations"], r["n_reconfigurations"]))


if __name__ == "__main__":
    main()
