# -*- coding: utf-8 -*-
"""z vs w 정식화 비교 — Youssef / Saffar(multi_part) 원본 데이터.

측정: LP relaxation bound / objective / best bound / gap / 풀이시간 / 모델 크기.
조건 통일: joint, 이동비 0, seed 0, MIPGap 0, warm start 없음, 순차 실행.
w는 (S) 강화식 없이 돌린다 — 논문 원형에 이동변수만 더한 순수 형태.

사용: python scratchpad/compare_zw.py [TIME_LIMIT=600]
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
from scratchpad import saffar_w_adaptive as engine_w  # noqa: E402
from scratchpad import milp_adaptive_flat as engine_z  # noqa: E402

TL = int(sys.argv[1]) if len(sys.argv) > 1 else 600
OUT = REPO / "Result" / "compare_zw"
OUT.mkdir(parents=True, exist_ok=True)


def shim(data_dir: Path, tag: str, use_S: bool) -> SimpleNamespace:
    s = SimpleNamespace(**{k: getattr(config, k) for k in dir(config) if k.isupper()})
    s.PROBLEM_NAME = data_dir.name
    for key, fn in [("LOCATION_FILE", "locations.csv"), ("CONFIGURATION_FILE", "configurations.csv"),
                    ("PRODUCTION_RATE_FILE", "production_rates.csv"), ("DEMAND_FILE", "demands.csv"),
                    ("PARAMETER_FILE", "parameters.csv"), ("SHARED_RESOURCE_FILE", "shared_resources.csv"),
                    ("RESOURCE_REQUIREMENT_FILE", "resource_requirements.csv"),
                    ("MODULE_COST_FILE", "module_costs.csv")]:
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
    s.TIME_LIMIT = TL
    s.MIP_GAP = 0.0
    s.MIP_FOCUS = None
    s.ADAPTIVE_MODE = "joint"
    s.ALPHA, s.BETA, s.MOVE_COST_FLAT = 0.0, 0.0, 0.0
    s.SAFFAR_BALANCE_EQ = use_S
    s.SAFFAR_W_BINARY = True
    s.GUROBI_PARAMS = {"Seed": 0, "LogFile": str(OUT / ("gurobi_%s.log" % tag))}
    return s


CASES = [
    ("youssef_2007", "z", engine_z, False),
    ("youssef_2007", "w", engine_w, False),
    ("multi_part",   "z", engine_z, False),
    ("multi_part",   "w", engine_w, False),
]

rows = []
for ds, name, eng, use_S in CASES:
    tag = "%s_%s" % (ds, name.replace("+", "plus"))
    print("\n" + "=" * 72, flush=True)
    print("[%s] %s  (TL=%ds, joint, 이동비 0%s)"
          % (ds, name, TL, ", (S) 포함" if use_S else ""), flush=True)
    print("=" * 72, flush=True)
    cfg = shim(REPO / "Data" / ds, tag, use_S)
    inst = load_instance(cfg)
    t0 = time.time()
    sol = eng.solve_milp(inst, cfg)
    sm = sol.summary
    row = {"dataset": ds, "model": name, "elapsed": round(time.time() - t0, 1),
           "status": sm.get("status"),
           "objective": sm.get("objective"), "best_bound": sm.get("best_bound"),
           "mip_gap": sm.get("mip_gap"), "runtime": sm.get("runtime"),
           "lp_bound": sm.get("lp_relaxation_bound"), "lp_seconds": sm.get("lp_relaxation_seconds"),
           "num_vars": sm.get("num_variables"), "num_binary": sm.get("num_binary_variables"),
           "num_constrs": sm.get("num_constraints"),
           "n_machines": sm.get("n_machines"), "n_relocations": sm.get("n_relocations")}
    rows.append(row)
    print("  ->", json.dumps(row, ensure_ascii=False, default=str), flush=True)
    (OUT / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=str),
                                      encoding="utf-8")

print("\n\n" + "=" * 96, flush=True)
print("%-14s %-6s %-14s %-12s %-12s %-9s %-10s %-9s %s"
      % ("데이터", "모형", "LP bound", "objective", "best bound", "gap", "변수", "이진", "시간"), flush=True)
print("=" * 96, flush=True)
for r in rows:
    print("%-14s %-6s %-14s %-12s %-12s %-9s %-10s %-9s %ss"
          % (r["dataset"], r["model"],
             round(r["lp_bound"], 4) if r["lp_bound"] is not None else "-",
             r["objective"], round(r["best_bound"], 1) if r["best_bound"] is not None else "-",
             "%.3f%%" % (100 * r["mip_gap"]) if r["mip_gap"] is not None else "-",
             r["num_vars"], r["num_binary"], r["elapsed"]), flush=True)
print("저장:", OUT / "results.json", flush=True)
