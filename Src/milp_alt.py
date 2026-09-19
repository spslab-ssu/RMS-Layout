from __future__ import annotations

from collections import defaultdict
from typing import Any

import gurobipy as gp
from gurobipy import GRB

from Src.data import resource_mode
from Src.milp import (
    RMSSolution,
    _add_shared_resource_constraints,
    _apply_gurobi_params,
    _apply_stage_time_limits,
    _compute_lp_relaxation_bound,
    _extract_solution,
    _minimize_sizing,
)
from Src.warm_start import apply_warm_start


def solve_milp(instance, config) -> RMSSolution:
    """대안 라우트(λ) 확장 모델.

    base(Src/milp.py)와 동일한 문제이되, demands.csv에서 같은 part 이름으로 적힌
    여러 행을 그 파트의 대안 라우트로 보고, 각 (파트, 대안, 기간)에 수요 배분 비율
    λ ∈ [0,1](Σ_대안 λ = 1)을 두어 어느 라우트를 얼마나 쓸지 솔버가 결정한다.

    base와의 차이는 흐름층의 수요 등식 하나뿐이다:
        base : Σ_{p,q} f[p,left,q,right,t] == (고정 arc 수요)
        alt  : Σ_{p,q} f[p,left,q,right,t] == Σ_{(part,k) ∋ arc} d[part,t] · λ[part,k,t]
    대안이 파트마다 1개뿐이면 λ ≡ 1이 되어 base와 정확히 같은 모델이다.
    기계 상태/용량/재구성/MHC/공유자원 제약은 base와 동일하다.
    """
    model = gp.Model(f"rms_layout_alt_{instance.problem_name}")
    model.Params.TimeLimit = config.TIME_LIMIT
    model.Params.MIPGap = config.MIP_GAP
    if hasattr(config, "OUTPUT_FLAG"):
        model.Params.OutputFlag = int(config.OUTPUT_FLAG)
    mip_focus = getattr(config, "MIP_FOCUS", None)
    if mip_focus is not None:
        model.Params.MIPFocus = int(mip_focus)
    _apply_gurobi_params(model, config)

    P = instance.install_locations
    J = instance.configurations
    L = instance.operations
    T = instance.periods
    feasible_pairs = instance.feasible_pairs
    route_arcs = instance.route_arcs           # 모든 대안 라우트의 arc 합집합
    part_routes = instance.part_routes         # part -> [full_route(start/end 포함), ...]
    part_demand = instance.part_demand         # (part, t) -> demand

    # 대안 목록과 arc 멤버십: 어떤 (part, k)의 라우트가 이 arc를 지나는가
    alternatives = [(part, k, route) for part, routes in part_routes.items() for k, route in enumerate(routes)]
    arc_members: dict[tuple[int, int], list[tuple[str, int]]] = defaultdict(list)
    for part, k, route in alternatives:
        for arc in zip(route[:-1], route[1:]):
            arc_members[arc].append((part, k))

    def demand_of(part: str, t: int) -> float:
        return float(part_demand.get((part, t), 0.0))

    def arc_active(arc: tuple[int, int], t: int) -> bool:
        return any(demand_of(part, t) > 0 for part, _k in arc_members.get(arc, []))

    lam_keys = [(part, k, t) for part, k, _route in alternatives for t in T if demand_of(part, t) > 0]

    x_keys = [(p, j, l) for p in P for (j, l) in feasible_pairs]
    s_keys = [(p, j, l, t) for p in P for (j, l) in feasible_pairs for t in T]
    y_keys = [
        (p, j_prev, j_next, l, t)
        for p in P
        for j_prev in J
        for (j_next, l) in feasible_pairs
        for t in T
        if t != 1 and j_prev != j_next and (j_prev, j_next) in instance.reconfiguration_cost
    ]
    v_keys = [(p, l, t) for p in P for l in L for t in T]

    flow_keys = []
    for t in T:
        for left, right in route_arcs:
            if not arc_active((left, right), t):
                continue
            from_locations = [instance.start_location] if left == instance.start_operation else P
            to_locations = [instance.end_location] if right == instance.end_operation else P
            for p in from_locations:
                for q in to_locations:
                    if p != q:
                        flow_keys.append((p, left, q, right, t))

    x = model.addVars(x_keys, vtype=GRB.BINARY, name="x")

    fixed_purchases = getattr(config, "FIXED_PURCHASES", None)
    if fixed_purchases is not None:
        fixed_set = set(fixed_purchases)
        invalid = sorted(fixed_set - set(x_keys))
        if invalid:
            raise ValueError(f"Invalid fixed purchase keys: {invalid}")
        for key in x_keys:
            model.addConstr(x[key] == (1 if key in fixed_set else 0), name=f"fixed_purchase[{key}]")

    s = model.addVars(s_keys, vtype=GRB.BINARY, name="s")
    y = model.addVars(y_keys, vtype=GRB.BINARY, name="y")
    v = model.addVars(v_keys, lb=0.0, name="v")
    f = model.addVars(flow_keys, lb=0.0, name="f")
    lam = model.addVars(lam_keys, lb=0.0, ub=1.0, name="lam")   # 대안 라우트 수요 배분 비율

    feasible_by_op: dict[int, list[str]] = defaultdict(list)
    feasible_by_config: dict[str, list[int]] = defaultdict(list)
    for j, l in feasible_pairs:
        feasible_by_op[l].append(j)
        feasible_by_config[j].append(l)

    # --- 기계 상태 제약 (base와 동일) ---
    for p in P:
        purchased_at_p = gp.quicksum(x[p, j, l] for j, l in feasible_pairs)
        model.addConstr(purchased_at_p <= 1, name=f"one_rmt_per_location[{p}]")
        for t in T:
            model.addConstr(
                gp.quicksum(s[p, j, l, t] for j, l in feasible_pairs) == purchased_at_p,
                name=f"one_state_if_purchased[{p},{t}]",
            )

    for p, j, l in x_keys:
        model.addConstr(s[p, j, l, 1] == x[p, j, l], name=f"initial_state[{p},{j},{l}]")

    for p in P:
        for t in T:
            if t == 1:
                continue
            for j, l in feasible_pairs:
                same_config_previous = gp.quicksum(
                    s[p, j, prev_l, t - 1] for prev_l in feasible_by_config[j] if (p, j, prev_l, t - 1) in s
                )
                reconfigured_to_current = gp.quicksum(
                    y[p, j_prev, j, l, t] for j_prev in J if (p, j_prev, j, l, t) in y
                )
                model.addConstr(
                    s[p, j, l, t] <= same_config_previous + reconfigured_to_current,
                    name=f"state_transition[{p},{j},{l},{t}]",
                )

    for p, j_prev, j_next, l, t in y_keys:
        previous_state = gp.quicksum(
            s[p, j_prev, prev_l, t - 1] for prev_l in feasible_by_config[j_prev] if (p, j_prev, prev_l, t - 1) in s
        )
        model.addConstr(y[p, j_prev, j_next, l, t] <= previous_state)
        model.addConstr(y[p, j_prev, j_next, l, t] <= s[p, j_next, l, t])

    mode = resource_mode(config)
    cap_ub = getattr(config, "CAP_UPPER_BOUNDS", None)
    cap_vars = _add_shared_resource_constraints(model, instance, P, T, feasible_pairs, s, mode, cap_ub)

    for p in P:
        for l in L:
            for t in T:
                model.addConstr(
                    v[p, l, t]
                    <= gp.quicksum(
                        instance.production_rate[j, l] * s[p, j, l, t]
                        for j in feasible_by_op[l]
                        if (p, j, l, t) in s
                    ),
                    name=f"capacity[{p},{l},{t}]",
                )

    # --- 흐름층 ---
    incoming: dict[tuple[int, int, int], list[tuple[int, int, int, int, int]]] = defaultdict(list)
    outgoing: dict[tuple[int, int, int], list[tuple[int, int, int, int, int]]] = defaultdict(list)
    flows_by_arc_t: dict[tuple[int, int, int], list[tuple[int, int, int, int, int]]] = defaultdict(list)
    for key in flow_keys:
        p, left, q, right, t = key
        if left != instance.start_operation:
            outgoing[(p, left, t)].append(key)
        if right != instance.end_operation:
            incoming[(q, right, t)].append(key)
        flows_by_arc_t[(left, right, t)].append(key)

    for p in P:
        for l in L:
            for t in T:
                model.addConstr(gp.quicksum(f[key] for key in incoming[p, l, t]) == v[p, l, t])
                model.addConstr(gp.quicksum(f[key] for key in outgoing[p, l, t]) == v[p, l, t])

    # 파트별 대안 배분 비율의 합은 1 (수요가 있는 기간만)
    for part, routes in part_routes.items():
        for t in T:
            if demand_of(part, t) <= 0:
                continue
            model.addConstr(
                gp.quicksum(lam[part, k, t] for k in range(len(routes))) == 1.0,
                name=f"route_mix[{part},{t}]",
            )

    # arc별 총 flow == Σ (그 arc를 지나는 대안의 수요 × λ)   ← base와 다른 유일한 제약
    for t in T:
        for left, right in route_arcs:
            if not arc_active((left, right), t):
                continue
            arc_flow = gp.quicksum(f[key] for key in flows_by_arc_t[(left, right, t)])
            required = gp.quicksum(
                demand_of(part, t) * lam[part, k, t]
                for part, k in arc_members[(left, right)]
                if demand_of(part, t) > 0
            )
            model.addConstr(arc_flow == required, name=f"arc_demand[{t},{left},{right}]")

    purchase_cost = gp.quicksum(instance.cost[j] * x[p, j, l] for p, j, l in x_keys)
    reconfiguration_cost = gp.quicksum(
        instance.reconfiguration_cost[j_prev, j_next] * y[p, j_prev, j_next, l, t]
        for p, j_prev, j_next, l, t in y_keys
    )
    handling_cost = gp.quicksum(
        instance.parameters["material_handling_cost"] * instance.distance[p, q] * f[p, left, q, right, t]
        for p, left, q, right, t in flow_keys
    )

    cost_expr = purchase_cost + reconfiguration_cost + handling_cost
    model.setObjective(cost_expr, GRB.MINIMIZE)
    lp_relaxation_bound, lp_relaxation_seconds = _compute_lp_relaxation_bound(model, config)

    if cap_vars is not None and _minimize_sizing(config):
        model.ModelSense = GRB.MINIMIZE
        model.setObjectiveN(cost_expr, index=0, priority=1, name="cost")
        model.setObjectiveN(gp.quicksum(cap_vars[r] for r in cap_vars), index=1, priority=0, name="sizing")
        _apply_stage_time_limits(model, config)

    if bool(getattr(config, "USE_WARM_START", False)):
        warm_start_dir = getattr(config, "WARM_START_DIR", None)
        if warm_start_dir is None:
            raise ValueError("USE_WARM_START=True이면 config.WARM_START_DIR를 지정해야 한다.")
        assigned = apply_warm_start({"x": x, "s": s, "y": y, "v": v, "f": f}, warm_start_dir)
        print(f"Applied warm start from {warm_start_dir}: {assigned}")

    if bool(getattr(config, "USE_OBJECTIVE_CUTOFF", False)):
        cutoff = getattr(config, "OBJECTIVE_CUTOFF", None)
        if cutoff is not None:
            model.Params.Cutoff = float(cutoff)

    model.optimize()

    solution = _extract_solution(
        model, instance, x, s, y, v, f, purchase_cost, reconfiguration_cost, handling_cost,
        lp_relaxation_bound, cap_vars, lp_relaxation_seconds,
    )
    solution.summary["model_type"] = "alt"
    solution.summary["num_route_alternatives"] = {part: len(routes) for part, routes in part_routes.items()}
    if model.SolCount:
        shares: list[dict[str, Any]] = []
        for (part, k, t), var in sorted(lam.items(), key=lambda item: (item[0][0], item[0][2], item[0][1])):
            if var.X > 1e-6:
                route = part_routes[part][k]
                shares.append({
                    "part": part, "period": t, "alternative": k,
                    "route": ">".join(str(op) for op in route[1:-1]),
                    "share": round(float(var.X), 4),
                    "flow": round(float(var.X) * demand_of(part, t), 4),
                })
        solution.summary["route_shares"] = shares
    return solution
