# -*- coding: utf-8 -*-
"""30분짜리 검증 2건.

A. dk_w(off) x multi_part 원본 -> base 모델이 48.1시간 걸려 증명한 35,775를 재현하는가.
   지금 유일한 "문헌 데이터에서 나온 증명된 양의 이득" 0.35%는
   off=Src/milp.py(base) / joint=dk_z 라는 교차모델 결과라 방어가 약하다.
   dk_w off가 35,775를 찍으면 단일 코드베이스 안의 결과가 된다.
   (판정: obj == 35775 이면 통과. 35775 미만이면 모델 불일치 = 버그 신호.)

B. R_layers_12 x alpha=0.05 -> 포락선 외삽 "이득(alpha) = 320 - 4608*alpha" 검증.
   예측 이득 89.6. off는 이미 OPTIMAL 15,595로 증명돼 있어 다시 풀지 않는다.
   (판정: joint obj <= 15595 - 89.6 + 여유 이면 외삽 유효.)
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
from scratchpad import saffar_w_adaptive as engine  # noqa: E402

OUT = REPO / "Result" / "quick_checks"
OUT.mkdir(parents=True, exist_ok=True)
TL = int(sys.argv[1]) if len(sys.argv) > 1 else 600


def shim(data_dir: Path, mode: str, tag: str, *, alpha=None, beta=None) -> SimpleNamespace:
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
    s.ADAPTIVE_MODE = mode
    if alpha is None:
        s.ALPHA, s.BETA, s.MOVE_COST_FLAT = 0.0, 0.0, 0.0
    else:
        s.ALPHA, s.BETA, s.MOVE_COST_FLAT = float(alpha), float(beta), None
    s.SAFFAR_BALANCE_EQ = True
    s.SAFFAR_W_BINARY = True
    s.GUROBI_PARAMS = {"Seed": 0, "LogFile": str(OUT / ("gurobi_%s.log" % tag))}
    return s


def run(tag, data_dir, mode, **kw):
    print("\n" + "=" * 70, flush=True)
    print("[%s] %s  mode=%s  TL=%ds" % (tag, data_dir, mode, TL), flush=True)
    print("=" * 70, flush=True)
    cfg = shim(data_dir, mode, tag, **kw)
    inst = load_instance(cfg)
    t0 = time.time()
    sol = engine.solve_milp(inst, cfg)
    s = sol.summary
    row = {"tag": tag, "mode": mode, "elapsed": round(time.time() - t0, 1),
           **{k: s.get(k) for k in ("status", "objective", "best_bound", "mip_gap", "runtime",
                                    "lp_relaxation_bound", "num_variables", "num_binary_variables",
                                    "purchase_cost", "reconfiguration_cost", "material_handling_cost",
                                    "relocation_cost", "n_machines", "n_relocations")}}
    print("  ->", json.dumps(row, ensure_ascii=False, default=str), flush=True)
    return row


rows = []

# ---- A ----
rows.append(run("A_dkw_off_multipart", REPO / "Data" / "multi_part", "off"))
a = rows[-1]
print("\n[A 판정] base 증명값 35,775 vs dk_w off obj=%s" % a.get("objective"), flush=True)
if a.get("objective") is not None:
    d = float(a["objective"]) - 35775.0
    print("  차이 %+0.1f -> %s" % (d, "일치(통과)" if abs(d) < 1e-6 else
                                   ("dk_w가 더 낮음 = 모델 불일치 의심" if d < 0 else "미수렴(incumbent가 아직 위)")), flush=True)

# ---- B ----
rows.append(run("B_alpha005", REPO / "Result" / "adaptive_campaign" / "R_layers_12" / "data",
                "joint", alpha=0.05, beta=0.01))
b = rows[-1]
if b.get("objective") is not None:
    gain = 15595.0 - float(b["objective"])
    print("\n[B 판정] 외삽 예측 이득 89.6 vs 실측 %.1f (%.2f%%)" % (gain, 100 * gain / 15595.0), flush=True)
    print("  %s" % ("외삽 유효(실측 >= 예측)" if gain >= 89.0 else "실측이 예측보다 낮음 - 미수렴이거나 외삽 과대"), flush=True)

(OUT / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("\n저장:", OUT / "results.json", flush=True)
