# -*- coding: utf-8 -*-
"""번들 OS12~17을 가짜 operation(112~117)으로 라우트에 박은 시퀀스 변형 시나리오를
데이터만으로 만들어 각 100초씩 풀고 비교한다. (코드/λ 없음, 기존 youssef_2007 무변경)

- 시나리오 데이터셋: scratchpad/bundle_scenarios/<name>/  (youssef_2007 복사 + demands/production_rates 변경)
- 결과: Result/youssef_2007_bundles/<name>/ + summary.json
"""
from __future__ import annotations

import json
import math
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402

import config  # noqa: E402
from Src.data import load_instance  # noqa: E402
from Src.milp import solve_milp  # noqa: E402
from Src.output import save_solution  # noqa: E402

BASE = REPO / "Data" / "youssef_2007"
SCEN_ROOT = REPO / "scratchpad" / "bundle_scenarios"
RESULT_ROOT = REPO / "Result" / "youssef_2007_bundles"
TIME_LIMIT = 100
assert not (BASE / "module_costs.csv").exists(), "module_costs.csv가 켜져 있으면 parameters의 50/25가 무시됩니다"

# Table B5 번들 setup: op ID = OS 번호 (OS6'는 60). (config: rate)  M2는 전부 X.
BUNDLES = {
    12: {"os": "OS12", "ocs": [3, 11], "rates": {"MC11": 60, "MC12": 120, "MC13": 180, "MC14": 240, "MC15": 60}},
    13: {"os": "OS13", "ocs": [8, 10], "rates": {"MC11": 120, "MC12": 240, "MC13": 360, "MC14": 480, "MC15": 120}},
    14: {"os": "OS14", "ocs": [2, 4, 7], "rates": {"MC11": 90, "MC12": 180, "MC13": 270, "MC14": 360, "MC15": 90}},
    15: {"os": "OS15", "ocs": [2, 3, 4, 7], "rates": {"MC11": 60, "MC12": 120, "MC13": 180, "MC14": 240, "MC15": 60}},
    16: {"os": "OS16", "ocs": [2, 4, 7, 8, 10], "rates": {"MC15": 60}},
    17: {"os": "OS17", "ocs": [2, 3, 4, 7, 8, 10], "rates": {"MC15": 40}},
}

A_BASE = "1>2>4>7>3>5>60"
B_BASE = "1>2>4>7>3>5>6>8>9>10>11"

# (이름, A 라우트, B 라우트) — 번들 노드 위치는 Fig B1 선행관계(OC3 after 2/4/7, OC11·OC6 after OC5, OC10 after OC7, OC9 after OC4/OC8)를 지킴
SCENARIOS = [
    ("S0_base",        A_BASE,           B_BASE),
    ("S1_os14",        "1>14>3>5>60",   "1>14>3>5>6>8>9>10>11"),
    ("S2_os15",        "1>15>5>60",     "1>15>5>6>8>9>10>11"),
    ("S3_os12_B",      A_BASE,           "1>2>4>7>5>12>6>8>9>10"),
    ("S4_os13_B",      A_BASE,           "1>2>4>7>3>5>6>13>9>11"),
    ("S5_os15_os13",   "1>15>5>60",     "1>15>5>6>13>9>11"),
    ("S6_os16_os12_B", "1>14>3>5>60",   "1>16>5>12>6>9"),
    ("S7_os17_B",      "1>15>5>60",     "1>17>5>11>6>9"),
]


def build_dataset(name: str, route_a: str, route_b: str) -> Path:
    d = SCEN_ROOT / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    for f in ["configurations.csv", "locations.csv", "parameters.csv", "module_costs.csv"]:
        if (BASE / f).exists():  # module_costs.csv가 없으면 전역 add/remove 단가(fallback) 사용
            shutil.copy(BASE / f, d / f)
    # production_rates: 기본 56행 + 번들 22행 (라우트에 없는 op는 로더가 자동 제외)
    rates = pd.read_csv(BASE / "production_rates.csv")
    extra = [
        {"machine": "M1", "configuration": cfg, "operation": op, "production_rate": r}
        for op, b in BUNDLES.items() for cfg, r in b["rates"].items()
        if not ((rates.configuration == cfg) & (rates.operation == op)).any()  # base에 이미 있으면 생략
    ]
    pd.concat([rates, pd.DataFrame(extra)], ignore_index=True).to_csv(d / "production_rates.csv", index=False)
    dem = pd.read_csv(BASE / "demands.csv").drop_duplicates(subset="part", keep="first")  # 대안 행 → 파트당 1행
    dem.loc[dem.part == "A", "operation_sequence"] = route_a
    dem.loc[dem.part == "B", "operation_sequence"] = route_b
    dem.to_csv(d / "demands.csv", index=False)
    return d


def make_shim(d: Path, name: str) -> SimpleNamespace:
    shim = SimpleNamespace(**{k: getattr(config, k) for k in dir(config) if k.isupper()})
    shim.PROBLEM_NAME = f"youssef_2007_bundles/{name}"
    shim.LOCATION_FILE = d / "locations.csv"
    shim.CONFIGURATION_FILE = d / "configurations.csv"
    shim.PRODUCTION_RATE_FILE = d / "production_rates.csv"
    shim.DEMAND_FILE = d / "demands.csv"
    shim.PARAMETER_FILE = d / "parameters.csv"
    shim.SHARED_RESOURCE_FILE = d / "shared_resources.csv"
    shim.RESOURCE_REQUIREMENT_FILE = d / "resource_requirements.csv"
    shim.MODULE_COST_FILE = d / "module_costs.csv"
    shim.RESULT_DIR = RESULT_ROOT / name
    shim.SHARED_RESOURCE_MODE = "off"
    shim.TIME_LIMIT = TIME_LIMIT
    shim.MIP_GAP = 0.0
    shim.USE_WARM_START = False
    shim.OUTPUT_FLAG = 0
    return shim


def machine_lower_bound(inst) -> dict[int, int]:
    """기간별 필요 기계 수 하한 = Σ_op ceil(op 수요 / 최고 rate)."""
    best = {}
    for (j, l), r in inst.production_rate.items():
        if (j, l) in set(inst.feasible_pairs):
            best[l] = max(best.get(l, 0.0), r)
    dem = pd.read_csv(inst.demand_file)
    out = {}
    for t in inst.periods:
        need: dict[int, float] = {}
        for row in dem.itertuples(index=False):
            d = float(getattr(row, f"period{t}"))
            if d <= 0:
                continue
            for op in str(row.operation_sequence).split(">"):
                need[int(op)] = need.get(int(op), 0.0) + d
        out[t] = sum(math.ceil(v / best[op]) for op, v in need.items())
    return out


def main() -> None:
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, ra, rb in SCENARIOS:
        d = build_dataset(name, ra, rb)
        shim = make_shim(d, name)
        inst = load_instance(shim)
        lb = machine_lower_bound(inst)
        print(f"\n### {name}  A={ra}  B={rb}", flush=True)
        print(f"    ops={len(inst.operations)} arcs={len(inst.route_arcs)} pairs={len(inst.feasible_pairs)} "
              f"기계하한={list(lb.values())}", flush=True)
        sol = solve_milp(inst, shim)
        save_solution(sol, shim.RESULT_DIR)
        s = sol.summary
        cb = sol.cost_breakdown
        fleet: dict[str, int] = {}
        for m in sol.purchased_machines:
            fleet[str(m.get("configuration"))] = fleet.get(str(m.get("configuration")), 0) + 1
        row = {
            "scenario": name, "route_A": ra, "route_B": rb,
            "status": s.get("status"), "objective": s.get("objective"), "best_bound": s.get("best_bound"),
            "gap": s.get("mip_gap"), "lp_bound": s.get("lp_relaxation_bound"),
            "purchase": cb.get("purchase_cost"), "reconfig": cb.get("reconfiguration_cost"),
            "mhc": cb.get("material_handling_cost"),
            "machines": len(sol.purchased_machines), "fleet": dict(sorted(fleet.items())),
            "reconfigs": len(sol.reconfigurations), "lb": lb,
            "num_binary": s.get("num_binary_vars"),
        }
        rows.append(row)
        print(f"    -> status={row['status']} obj={row['objective']} bound={row['best_bound']} gap={row['gap']}"
              f"  구매={row['purchase']} 재구성={row['reconfig']} MHC={row['mhc']}  기계={row['machines']} {row['fleet']}"
              f" 재구성건수={row['reconfigs']}", flush=True)

    (RESULT_ROOT / "summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("\n\n==== 비교표 (100초 incumbent) ====")
    print(f"{'scenario':<16}{'obj':>8}{'bound':>8}{'gap':>7}{'구매':>8}{'재구성':>7}{'MHC':>8}{'기계':>5}  fleet / 하한")
    for r in rows:
        obj = r["objective"]; bd = r["best_bound"]; gap = r["gap"]
        print(f"{r['scenario']:<16}{(obj if obj is None else round(obj)):>8}{(bd if bd is None else round(bd)):>8}"
              f"{(gap if gap is None else f'{gap*100:.1f}%'):>7}{(r['purchase'] or 0):>8.0f}{(r['reconfig'] or 0):>7.0f}"
              f"{(r['mhc'] or 0):>8.0f}{r['machines']:>5}  {r['fleet']} / {list(r['lb'].values())}")


if __name__ == "__main__":
    main()
