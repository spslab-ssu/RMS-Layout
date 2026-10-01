# -*- coding: utf-8 -*-
"""시나리오 하나를 엔진·모드 지정해서 1회만 푼다 (off 없이 joint만 돌릴 때 씀).

사용: python scratchpad/run_one.py <스펙JSON> <id> <엔진 z|w> <모드 off|joint>
                                   [TIME_LIMIT=600] [MIP_GAP=0] [WARM_START_DIR]
해를 Result/run_one/<id>_<엔진>_<모드>_solution/ 에 저장한다 (다음 단계 warm start용).
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
from scratchpad import campaign_gen  # noqa: E402
from scratchpad import saffar_w_adaptive as engine_w  # noqa: E402
from scratchpad import milp_adaptive_flat as engine_z  # noqa: E402
from Src.output import save_solution  # noqa: E402

QUEUE, SID, ENG, MODE = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
TL = int(sys.argv[5]) if len(sys.argv) > 5 else 600
GAP = float(sys.argv[6]) if len(sys.argv) > 6 else 0.0
WARM = Path(sys.argv[7]) if len(sys.argv) > 7 and sys.argv[7] not in ("", "-") else None
OUT = REPO / "Result" / "run_one"
OUT.mkdir(parents=True, exist_ok=True)

spec = next(s for s in json.loads(QUEUE.read_text(encoding="utf-8")) if s["id"] == SID)
data_dir = campaign_gen.generate(spec)

s = SimpleNamespace(**{k: getattr(config, k) for k in dir(config) if k.isupper()})
s.PROBLEM_NAME = SID
for key, fn in [("LOCATION_FILE", "locations.csv"), ("CONFIGURATION_FILE", "configurations.csv"),
                ("PRODUCTION_RATE_FILE", "production_rates.csv"), ("DEMAND_FILE", "demands.csv"),
                ("PARAMETER_FILE", "parameters.csv"), ("SHARED_RESOURCE_FILE", "shared_resources.csv"),
                ("RESOURCE_REQUIREMENT_FILE", "resource_requirements.csv"),
                ("MODULE_COST_FILE", "module_costs.csv")]:
    setattr(s, key, data_dir / fn)
s.SHARED_RESOURCE_MODE = "off"
s.ALLOW_RECONFIGURATION = True
s.USE_WARM_START = WARM is not None
s.WARM_START_DIR = WARM
s.USE_OBJECTIVE_CUTOFF = False
s.USE_MIN_MACHINE_CUTS = False
s.MINIMIZE_SIZING = False
s.FIXED_PURCHASES = None
s.COMPUTE_LP_RELAXATION_BOUND = True
s.OUTPUT_FLAG = 1
s.TIME_LIMIT = TL
s.MIP_GAP = GAP
s.MIP_FOCUS = None
s.ADAPTIVE_MODE = MODE
s.ALPHA = float(spec.get("alpha", 0.0))
s.BETA = float(spec.get("beta", 0.0))
s.MOVE_COST_FLAT = None if ("alpha" in spec or "beta" in spec) else float(spec.get("move_cost_flat", 0.0))
s.SAFFAR_BALANCE_EQ = bool(spec.get("balance_eq", False))
s.SAFFAR_W_BINARY = True
s.GUROBI_PARAMS = {"Seed": 0, "LogFile": str(OUT / ("gurobi_%s_%s_%s.log" % (SID, ENG, MODE)))}

print("=" * 72, flush=True)
print("[%s] 엔진=%s 모드=%s TL=%ds MIPGap=%s warm=%s" % (SID, ENG, MODE, TL, GAP, WARM), flush=True)
for d in spec["demands"]:
    print("   %-4s %2d공정  %s" % (d["part"], len(d["seq"].split(">")), d["periods"]), flush=True)
print("=" * 72, flush=True)

eng = engine_z if ENG == "z" else engine_w
inst = load_instance(s)
t0 = time.time()
sol = eng.solve_milp(inst, s)
sm = sol.summary
row = {"id": SID, "engine": ENG, "mode": MODE, "time_limit": TL,
       "elapsed": round(time.time() - t0, 1), "status": sm.get("status"),
       "objective": sm.get("objective"), "best_bound": sm.get("best_bound"),
       "mip_gap": sm.get("mip_gap"), "lp_bound": sm.get("lp_relaxation_bound"),
       "lp_seconds": sm.get("lp_relaxation_seconds"),
       "purchase_cost": sm.get("purchase_cost"), "reconfiguration_cost": sm.get("reconfiguration_cost"),
       "material_handling_cost": sm.get("material_handling_cost"),
       "relocation_cost": sm.get("relocation_cost"),
       "n_machines": sm.get("n_machines"), "n_relocations": sm.get("n_relocations"),
       "num_constraints": sm.get("num_constraints")}
print("\n->", json.dumps(row, ensure_ascii=False, indent=1, default=str), flush=True)
sol_dir = OUT / ("%s_%s_%s_solution" % (SID, ENG, MODE))
try:
    sol_dir.mkdir(parents=True, exist_ok=True)
    save_solution(sol, sol_dir)
    for fp in sol_dir.glob("*.csv"):      # BOM만 있는 빈 CSV는 warm_start 파서를 깨뜨린다
        if fp.stat().st_size < 10:
            fp.unlink()
    print("해 저장:", sol_dir, flush=True)
except Exception as e:
    print("해 저장 실패:", repr(e), flush=True)

f = OUT / ("%s_%s_%s.json" % (SID, ENG, MODE))
f.write_text(json.dumps(row, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("저장:", f, flush=True)
