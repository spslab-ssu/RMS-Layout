# -*- coding: utf-8 -*-
"""λ 모델 속도 손잡이 테스트 (각 100초).

(a) 현재 데이터셋 그대로 + Gurobi MIPFocus=1 + MIPGap 3%
(b) 축소 변형: 16슬롯(single_part 레이아웃) + 대안 가지치기(A 2개, B 4개) + MIPGap 3%
목표: 100초 안에 gap 3% 도달 여부와 걸린 시간.
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402

import config  # noqa: E402
from Src.data import load_instance  # noqa: E402
from Src.milp_alt import solve_milp  # noqa: E402

BASE = REPO / "Data" / "youssef_2007"
FAST = REPO / "scratchpad" / "fast_variant"
KEEP_ROUTES = {
    "A": ["1>5>60>2>7>4>3", "1>5>60>15"],
    "B": ["1>5>11>6>2>7>10>4>3>8>9", "1>5>11>6>15>13>9", "1>5>6>16>12>9", "1>5>11>6>17>9"],
}


def shim_for(d: Path, name: str, **over) -> SimpleNamespace:
    shim = SimpleNamespace(**{k: getattr(config, k) for k in dir(config) if k.isupper()})
    shim.PROBLEM_NAME = name
    for key, fn in [("LOCATION_FILE", "locations.csv"), ("CONFIGURATION_FILE", "configurations.csv"),
                    ("PRODUCTION_RATE_FILE", "production_rates.csv"), ("DEMAND_FILE", "demands.csv"),
                    ("PARAMETER_FILE", "parameters.csv"), ("SHARED_RESOURCE_FILE", "shared_resources.csv"),
                    ("RESOURCE_REQUIREMENT_FILE", "resource_requirements.csv"), ("MODULE_COST_FILE", "module_costs.csv")]:
        setattr(shim, key, d / fn)
    shim.SHARED_RESOURCE_MODE = "off"
    shim.USE_WARM_START = False
    shim.OUTPUT_FLAG = 0
    shim.COMPUTE_LP_RELAXATION_BOUND = False
    shim.TIME_LIMIT = 100
    shim.MIP_GAP = 0.03
    for k, v in over.items():
        setattr(shim, k, v)
    return shim


def build_fast_variant() -> Path:
    if FAST.exists():
        shutil.rmtree(FAST)
    FAST.mkdir(parents=True)
    for f in ["configurations.csv", "production_rates.csv"]:
        shutil.copy(BASE / f, FAST / f)
    shutil.copy(REPO / "Data" / "single_part" / "locations.csv", FAST / "locations.csv")   # 16슬롯 + 도크 17/18
    params = (BASE / "parameters.csv").read_text(encoding="utf-8")
    params = params.replace("start_location,21", "start_location,17").replace("end_location,22", "end_location,18")
    (FAST / "parameters.csv").write_text(params, encoding="utf-8")
    dem = pd.read_csv(BASE / "demands.csv")
    keep = dem[dem.apply(lambda r: r.operation_sequence in KEEP_ROUTES[r.part], axis=1)]
    keep.to_csv(FAST / "demands.csv", index=False, lineterminator="\n")
    return FAST


def run(label: str, d: Path, **over) -> None:
    shim = shim_for(d, label, **over)
    inst = load_instance(shim)
    t0 = time.time()
    sol = solve_milp(inst, shim)
    s = sol.summary
    print(f"\n### {label}")
    print(f"    P={len(inst.install_locations)} arcs={len(inst.route_arcs)} 대안={ {p: len(r) for p, r in inst.part_routes.items()} } "
          f"binary={s.get('num_binary_vars')} vars={s.get('num_vars')}")
    print(f"    status={s.get('status_name')} obj={s.get('objective')} bound={s.get('best_bound')} "
          f"gap={s.get('mip_gap')} runtime={s.get('runtime_seconds'):.0f}s (wall {time.time() - t0:.0f}s)")
    print(f"    비용: {sol.cost_breakdown}")
    print(f"    라우트: " + ", ".join(f"{r['part']}t{r['period']}:{r['route']}({r['share']})" for r in s.get("route_shares", [])[:8]))


if __name__ == "__main__":
    run("(a) 현재 데이터셋 + MIPFocus=1 + gap3%", BASE, MIP_FOCUS=1)
    fast = build_fast_variant()
    run("(b) 16슬롯 + 대안 가지치기(A2/B4) + gap3%", fast)
    run("(c) 16슬롯 + 가지치기 + gap3% + MIPFocus=1", fast, MIP_FOCUS=1)
