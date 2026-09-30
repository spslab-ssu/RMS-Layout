# -*- coding: utf-8 -*-
"""dk_w(off)가 base 모델의 증명된 최적해를 같은 비용으로 표현하는가.

base(Src/milp.py)는 multi_part off를 48.1시간 걸려 35,775로 증명했다.
그 해를 dk_w off에 MIP start로 넣고, 첫 incumbent가 정확히 35,775인지 본다.
  - 35,775 -> dk_w off와 base가 같은 해집합·같은 비용. 교차모델 우려 해소.
  - 더 큼   -> dk_w가 그 해를 그대로 못 받았다 (제약이 더 빡빡하거나 warm start 실패).
  - 더 작음 -> dk_w가 base보다 느슨하다 = 모델 불일치(버그).
600초를 태워 찾게 하는 것(35,791에서 멈춤)보다 훨씬 싸고 결정적이다.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import config  # noqa: E402
from Src.data import load_instance  # noqa: E402
from scratchpad import saffar_w_adaptive as engine  # noqa: E402

SRC_SOL = REPO / "Result" / "multi_part_optimal"
OUT = REPO / "Result" / "quick_checks"
OUT.mkdir(parents=True, exist_ok=True)
WS = OUT / "ws_multipart_optimal"
TL = int(sys.argv[1]) if len(sys.argv) > 1 else 120

# warm_start의 pandas 파서는 BOM만 있는 3바이트 CSV에서 깨진다 -> 복사 후 제거
if WS.exists():
    shutil.rmtree(WS)
WS.mkdir(parents=True)
for fp in SRC_SOL.glob("*.csv"):
    if fp.stat().st_size >= 10:
        shutil.copy(fp, WS / fp.name)
print("warm start 파일:", sorted(p.name for p in WS.glob("*.csv")), flush=True)
print("base 비용 분해:", (SRC_SOL / "cost_breakdown.csv").read_text(encoding="utf-8-sig").strip(), flush=True)

data_dir = REPO / "Data" / "multi_part"
s = SimpleNamespace(**{k: getattr(config, k) for k in dir(config) if k.isupper()})
s.PROBLEM_NAME = "multi_part"
for key, fn in [("LOCATION_FILE", "locations.csv"), ("CONFIGURATION_FILE", "configurations.csv"),
                ("PRODUCTION_RATE_FILE", "production_rates.csv"), ("DEMAND_FILE", "demands.csv"),
                ("PARAMETER_FILE", "parameters.csv"), ("SHARED_RESOURCE_FILE", "shared_resources.csv"),
                ("RESOURCE_REQUIREMENT_FILE", "resource_requirements.csv"),
                ("MODULE_COST_FILE", "module_costs.csv")]:
    setattr(s, key, data_dir / fn)
s.SHARED_RESOURCE_MODE = "off"
s.ALLOW_RECONFIGURATION = True
s.USE_WARM_START = True
s.WARM_START_DIR = WS
s.USE_OBJECTIVE_CUTOFF = False
s.USE_MIN_MACHINE_CUTS = False
s.MINIMIZE_SIZING = False
s.FIXED_PURCHASES = None
s.COMPUTE_LP_RELAXATION_BOUND = False
s.OUTPUT_FLAG = 1
s.TIME_LIMIT = TL
s.MIP_GAP = 0.0
s.MIP_FOCUS = None
s.ADAPTIVE_MODE = "off"
s.ALPHA, s.BETA, s.MOVE_COST_FLAT = 0.0, 0.0, 0.0
s.SAFFAR_BALANCE_EQ = True
s.SAFFAR_W_BINARY = True
s.GUROBI_PARAMS = {"Seed": 0, "LogFile": str(OUT / "gurobi_validate_dkw_off.log")}

inst = load_instance(s)
sol = engine.solve_milp(inst, s)
sm = sol.summary
obj = sm.get("objective")
print("\n" + "=" * 64, flush=True)
print("dk_w(off) + base 증명해 warm start  ->  obj = %s  bound = %s  status = %s"
      % (obj, sm.get("best_bound"), sm.get("status")), flush=True)
print("  구매 %s / 재구성 %s / MHC %s / 이동비 %s | 기계 %s대 이동 %s회"
      % (sm.get("purchase_cost"), sm.get("reconfiguration_cost"), sm.get("material_handling_cost"),
         sm.get("relocation_cost"), sm.get("n_machines"), sm.get("n_relocations")), flush=True)
if obj is not None:
    d = float(obj) - 35775.0
    verdict = ("일치 — dk_w off ≡ base (교차모델 우려 해소)" if abs(d) < 1e-6 else
               "dk_w가 더 낮음 = 모델 불일치(버그 신호)" if d < 0 else
               "dk_w가 더 높음 = warm start를 못 받았거나 제약이 더 빡빡함")
    print("  base 35,775 대비 %+0.2f  ->  %s" % (d, verdict), flush=True)
print("=" * 64, flush=True)
(OUT / "validate_dkw_off.json").write_text(
    json.dumps({k: sm.get(k) for k in ("objective", "best_bound", "status", "mip_gap",
                                       "purchase_cost", "reconfiguration_cost",
                                       "material_handling_cost", "relocation_cost",
                                       "n_machines", "n_relocations")},
               ensure_ascii=False, indent=1, default=str), encoding="utf-8")
