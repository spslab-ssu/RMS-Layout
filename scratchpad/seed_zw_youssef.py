# -*- coding: utf-8 -*-
"""Youssef 데이터에서 z vs w 를 seed 3개로 반복 측정.

단일 seed 결과(w 26초 vs z 129초)가 재현되는지 확인한다.
LP bound 와 objective 는 seed 와 무관해야 하고, 풀이시간만 변동해야 한다.
조건: joint, 이동비 0, (S) 제외, 모듈 단가 ON(add 280 / remove 140), MIPGap 0.
"""
from __future__ import annotations

import json
import statistics as st
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
SEEDS = [int(x) for x in (sys.argv[2].split(",") if len(sys.argv) > 2 else ["0", "1", "2"])]
OUT = REPO / "Result" / "compare_zw"
OUT.mkdir(parents=True, exist_ok=True)
DATA = REPO / "Data" / "youssef_2007"


def shim(seed: int, tag: str) -> SimpleNamespace:
    s = SimpleNamespace(**{k: getattr(config, k) for k in dir(config) if k.isupper()})
    s.PROBLEM_NAME = "youssef_2007"
    for key, fn in [("LOCATION_FILE", "locations.csv"), ("CONFIGURATION_FILE", "configurations.csv"),
                    ("PRODUCTION_RATE_FILE", "production_rates.csv"), ("DEMAND_FILE", "demands.csv"),
                    ("PARAMETER_FILE", "parameters.csv"), ("SHARED_RESOURCE_FILE", "shared_resources.csv"),
                    ("RESOURCE_REQUIREMENT_FILE", "resource_requirements.csv"),
                    ("MODULE_COST_FILE", "module_costs.csv")]:
        setattr(s, key, DATA / fn)
    off = DATA / "module_costs.csv.off"
    if off.exists():
        s.MODULE_COST_FILE = off          # Youssef 논문 실제 모듈 단가
    s.SHARED_RESOURCE_MODE = "off"
    s.ALLOW_RECONFIGURATION = True
    s.USE_WARM_START = False
    s.USE_OBJECTIVE_CUTOFF = False
    s.USE_MIN_MACHINE_CUTS = False
    s.MINIMIZE_SIZING = False
    s.FIXED_PURCHASES = None
    s.COMPUTE_LP_RELAXATION_BOUND = True
    s.OUTPUT_FLAG = 0
    s.TIME_LIMIT = TL
    s.MIP_GAP = 0.0
    s.MIP_FOCUS = None
    s.ADAPTIVE_MODE = "joint"
    s.ALPHA, s.BETA, s.MOVE_COST_FLAT = 0.0, 0.0, 0.0
    s.SAFFAR_BALANCE_EQ = False           # (S) 제외
    s.SAFFAR_W_BINARY = True
    s.GUROBI_PARAMS = {"Seed": seed, "LogFile": str(OUT / ("gurobi_seed_%s.log" % tag))}
    return s


rows = []
for name, eng in (("z", engine_z), ("w", engine_w)):
    for seed in SEEDS:
        cfg = shim(seed, "%s_s%d" % (name, seed))
        inst = load_instance(cfg)
        t0 = time.time()
        sol = eng.solve_milp(inst, cfg)
        sm = sol.summary
        r = {"model": name, "seed": seed, "elapsed": round(time.time() - t0, 1),
             "status": sm.get("status"), "objective": sm.get("objective"),
             "best_bound": sm.get("best_bound"), "mip_gap": sm.get("mip_gap"),
             "lp_bound": sm.get("lp_relaxation_bound"),
             "lp_seconds": round(sm.get("lp_relaxation_seconds") or 0, 2),
             "n_relocations": sm.get("n_relocations")}
        rows.append(r)
        print("  %-2s seed %d  %-9s obj=%-9s LP=%-12s %.1fs"
              % (name, seed, {2: "OPTIMAL", 9: "TIME_LIMIT"}.get(r["status"], r["status"]),
                 r["objective"], round(r["lp_bound"], 4) if r["lp_bound"] else "-", r["elapsed"]),
              flush=True)
        (OUT / "seed_results.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

print("\n" + "=" * 70)
print("%-6s %-10s %-10s %-10s %-12s %s" % ("모형", "평균(초)", "최소", "최대", "LP bound", "objective"))
print("=" * 70)
for name in ("z", "w"):
    g = [r for r in rows if r["model"] == name]
    ts = [r["elapsed"] for r in g]
    lps = {round(r["lp_bound"], 6) for r in g if r["lp_bound"] is not None}
    objs = {r["objective"] for r in g}
    print("%-6s %-10.1f %-10.1f %-10.1f %-12s %s"
          % (name, st.mean(ts), min(ts), max(ts),
             lps.pop() if len(lps) == 1 else lps, objs.pop() if len(objs) == 1 else objs))
print("\n저장:", OUT / "seed_results.json")
