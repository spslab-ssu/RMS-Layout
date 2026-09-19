# -*- coding: utf-8 -*-
"""milp_alt(λ 모델) 검증.

1) 대안이 1개뿐인 데이터셋(S0_base)에서 base와 alt의 LP relaxation bound가 동일해야 한다.
2) 대안 16개 데이터셋(Data/youssef_2007)에서 alt 로드/라우트 커버리지(각 OC 정확히 1회)/선행관계 검사.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import config  # noqa: E402
from Src.data import load_instance  # noqa: E402
from Src import milp as base_milp  # noqa: E402
from Src import milp_alt  # noqa: E402

BUNDLE_OCS = {12: {3, 11}, 13: {8, 10}, 14: {2, 4, 7}, 15: {2, 3, 4, 7}, 16: {2, 4, 7, 8, 10}, 17: {2, 3, 4, 7, 8, 10}}
PART_OCS = {"A": {1, 2, 3, 4, 5, 60, 7}, "B": {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11}}
# OC 수준 선행관계 (Fig B1): (선행, 후행)
PRECEDENCE = [(1, oc) for oc in [2, 3, 4, 5, 6, 60, 7, 8, 9, 10, 11]] + [
    (2, 3), (4, 3), (7, 3), (5, 6), (5, 60), (5, 11), (7, 10), (4, 9), (8, 9),
]


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
    shim.COMPUTE_LP_RELAXATION_BOUND = True
    for k, v in over.items():
        setattr(shim, k, v)
    return shim


def check(name, cond, detail=""):
    print(f"[{'OK ' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        raise SystemExit(1)


# ---- 1) 대안 1개 → base ≡ alt (LP bound 동일)
single = REPO / "scratchpad" / "bundle_scenarios" / "S0_base"
sh = shim_for(single, "S0_base", TIME_LIMIT=3, MIP_GAP=0.0)
inst = load_instance(sh)
check("S0_base는 대안 없음", not inst.has_route_alternatives)
lp_base = base_milp.solve_milp(inst, sh).summary["lp_relaxation_bound"]
lp_alt = milp_alt.solve_milp(inst, sh).summary["lp_relaxation_bound"]
check("LP bound base == alt (대안 1개)", abs(lp_base - lp_alt) < 1e-6, f"base={lp_base} alt={lp_alt}")

# ---- 2) 대안 16개 데이터셋
multi = REPO / "Data" / "youssef_2007"
sh2 = shim_for(multi, "youssef_2007", TIME_LIMIT=3)
inst2 = load_instance(sh2)
check("대안 감지", inst2.has_route_alternatives)
check("A 3개 / B 13개", {p: len(r) for p, r in inst2.part_routes.items()} == {"A": 3, "B": 13},
      f"{ {p: len(r) for p, r in inst2.part_routes.items()} }")
check("operations = 18개 (1~17 + 60)", inst2.operations == list(range(1, 18)) + [60], f"{inst2.operations}")
check("feasible_pairs 78개", len(inst2.feasible_pairs) == 78, f"{len(inst2.feasible_pairs)}")

for part, routes in inst2.part_routes.items():
    for k, full in enumerate(routes):
        route = full[1:-1]
        covered = []
        for op in route:
            covered += sorted(BUNDLE_OCS.get(op, {op}))
        check(f"{part} 대안{k} {'>'.join(map(str, route))}: OC 정확히 1회 커버",
              sorted(covered) == sorted(PART_OCS[part]), f"covered={sorted(covered)}")
        pos = {}
        for i, op in enumerate(route):
            for oc in BUNDLE_OCS.get(op, {op}):
                pos[oc] = i
        bad = [(a, b) for a, b in PRECEDENCE if a in pos and b in pos and pos[a] > pos[b]]
        check(f"{part} 대안{k}: 선행관계", not bad, f"위반={bad}")

for t in inst2.periods:
    for part in ["A", "B"]:
        print(f"    part_demand[{part},{t}] = {inst2.part_demand[(part, t)]}")

# base(네이티브 λ) vs milp_alt(독립 구현): 같은 16행 데이터셋에서 LP bound 동일해야 함
from Src import milp_network  # noqa: E402
sol_alt = milp_alt.solve_milp(inst2, sh2)
sol_base = base_milp.solve_milp(inst2, sh2)
check("base 네이티브 λ 실행 정상", sol_base.summary["status"] in (2, 9), f"status={sol_base.summary['status']}")
check("LP bound base(λ) == milp_alt(λ) (대안 16개)",
      abs(sol_base.summary["lp_relaxation_bound"] - sol_alt.summary["lp_relaxation_bound"]) < 1e-6,
      f"base={sol_base.summary['lp_relaxation_bound']} alt={sol_alt.summary['lp_relaxation_bound']}")
check("base summary에 대안 수 기록", sol_base.summary.get("num_route_alternatives") == {"A": 3, "B": 13})
sol_net = milp_network.solve_milp(inst2, sh2)
check("network 네이티브 λ 실행 정상", sol_net.summary["status"] in (2, 9), f"status={sol_net.summary['status']}")
print("    LP bound: base/alt =", sol_base.summary["lp_relaxation_bound"], "| network =", sol_net.summary["lp_relaxation_bound"])
# 대안 1개 데이터셋에서 network도 그대로 동작(회귀)
sol_net1 = milp_network.solve_milp(inst, sh)
check("network 단일 라우트 회귀 정상", sol_net1.summary["status"] in (2, 9) and "route_shares" not in sol_net1.summary)
print("\n모든 검증 통과")
