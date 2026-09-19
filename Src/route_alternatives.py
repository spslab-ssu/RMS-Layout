"""파트별 대안 라우트("메뉴") 공용 헬퍼.

demands.csv에서 같은 part 이름의 행 여러 개 = 그 파트의 대안 라우트. 어느 라우트에
수요를 얼마나 보낼지는 비율 변수 λ[part, k, t] ∈ [0,1] (Σ_k λ = 1)로 솔버가 결정한다.

base(Src/milp.py)와 network(Src/milp_network.py)의 흐름층은 동일하므로, 두 모델 모두
arc별 수요 등식을 이 모듈의 add_route_demand_constraints()로 건다.
  - 대안이 없으면(파트당 행 1개): 기존과 같은 고정 등식  Σ f == arc_demand
  - 대안이 있으면:                   Σ f == Σ_{(part,k) ∋ arc} d[part,t] · λ[part,k,t]
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import gurobipy as gp


def add_route_demand_constraints(model, instance, flow_keys, f, force_lambda: bool = False):
    """arc별 수요 등식을 추가하고, 대안 라우트가 있으면(또는 force_lambda) λ 변수 dict를, 없으면 None을 반환한다.

    force_lambda=True는 대안이 파트당 1개뿐이어도 λ 경로를 강제한다(λ≡1이 되어 결과는 동일해야 함 — 동일성 확인용).
    """
    flows_by_arc_t: dict[tuple[int, int, int], list] = defaultdict(list)
    for key in flow_keys:
        _p, left, _q, right, t = key
        flows_by_arc_t[(left, right, t)].append(key)

    periods = instance.periods
    if not getattr(instance, "has_route_alternatives", False) and not force_lambda:
        for t in periods:
            for left, right in instance.route_arcs:
                required = instance.arc_demand.get((t, left, right), 0.0)
                if required <= 0:
                    continue
                arc_flow = gp.quicksum(f[key] for key in flows_by_arc_t[(left, right, t)])
                model.addConstr(arc_flow == required, name=f"arc_demand[{t},{left},{right}]")
        return None

    part_routes = instance.part_routes
    part_demand = instance.part_demand

    def demand_of(part: str, t: int) -> float:
        return float(part_demand.get((part, t), 0.0))

    arc_members: dict[tuple[int, int], list[tuple[str, int]]] = defaultdict(list)
    for part, routes in part_routes.items():
        for k, route in enumerate(routes):
            for arc in zip(route[:-1], route[1:]):
                arc_members[arc].append((part, k))

    lam_keys = [
        (part, k, t)
        for part, routes in part_routes.items()
        for k in range(len(routes))
        for t in periods
        if demand_of(part, t) > 0
    ]
    lam = model.addVars(lam_keys, lb=0.0, ub=1.0, name="lam")

    # 파트별 배분 비율 합 = 1 (수요가 있는 기간만)
    for part, routes in part_routes.items():
        for t in periods:
            if demand_of(part, t) <= 0:
                continue
            model.addConstr(
                gp.quicksum(lam[part, k, t] for k in range(len(routes))) == 1.0,
                name=f"route_mix[{part},{t}]",
            )

    # arc별 흐름 == 그 arc를 지나는 대안들의 (수요 × λ) 합
    for t in periods:
        for left, right in instance.route_arcs:
            members = [(part, k) for part, k in arc_members.get((left, right), []) if demand_of(part, t) > 0]
            if not members:
                continue
            arc_flow = gp.quicksum(f[key] for key in flows_by_arc_t[(left, right, t)])
            required = gp.quicksum(demand_of(part, t) * lam[part, k, t] for part, k in members)
            model.addConstr(arc_flow == required, name=f"arc_demand[{t},{left},{right}]")
    return lam


def route_shares(instance, lam) -> list[dict[str, Any]]:
    """해에서 λ > 0인 (파트, 대안, 기간)을 사람이 읽기 좋은 row list로 만든다."""
    if lam is None:
        return []
    rows: list[dict[str, Any]] = []
    for (part, k, t), var in sorted(lam.items(), key=lambda item: (item[0][0], item[0][2], item[0][1])):
        if var.X > 1e-6:
            route = instance.part_routes[part][k]
            demand = float(instance.part_demand.get((part, t), 0.0))
            rows.append({
                "part": part,
                "period": t,
                "alternative": k,
                "route": ">".join(str(op) for op in route[1:-1]),
                "share": round(float(var.X), 4),
                "flow": round(float(var.X) * demand, 4),
            })
    return rows
