from __future__ import annotations

from collections import defaultdict
from typing import Any

import gurobipy as gp
from gurobipy import GRB

from Src.data import resource_mode
from Src.milp import (
    RMSSolution,
    _clean_float,
    _solver_metrics,
    _compute_lp_relaxation_bound,
    _add_shared_resource_constraints,
    _apply_stage_time_limits,
)


def solve_milp(instance, config) -> RMSSolution:
    """Adaptive layout MILP: 기간 경계에서 기계 relocation(이동)을 허용한다.

    통합 전이변수 z[k,p,j_prev,j_next,l,t] 하나가 유지/재구성/이동/(이동+재구성)을 모두 표현하고,
    ADAPTIVE_MODE로 정책을 나눈다:
      off      : k=p만 허용 (위치 고정, base와 동등)
      separate : 이동이면 config 유지, 재구성이면 제자리 (동시 금지)
      joint    : 이동 + 재구성 동시 허용
    z는 연속(0..1) — s가 binary면 전이가 transportation 구조라 정수해가 보장된다.
    이동비 = C_{j_prev}·(ALPHA + BETA·D_kp).
    """
    model = gp.Model(f"rms_adaptive_{instance.problem_name}")
    model.Params.TimeLimit = config.TIME_LIMIT
    model.Params.MIPGap = config.MIP_GAP
    if hasattr(config, "OUTPUT_FLAG"):
        model.Params.OutputFlag = int(config.OUTPUT_FLAG)

    P = instance.install_locations
    J = instance.configurations
    L = instance.operations
    T = instance.periods
    feasible_pairs = instance.feasible_pairs
    route_arcs = instance.route_arcs

    mode_a = str(getattr(config, "ADAPTIVE_MODE", "separate")).lower()
    if mode_a not in {"off", "separate", "joint"}:
        raise ValueError(f"ADAPTIVE_MODE must be off/separate/joint, got {mode_a!r}")
    alpha = float(getattr(config, "ALPHA", 0.0))
    beta = float(getattr(config, "BETA", 0.0))

    feasible_by_op: dict[int, list[str]] = defaultdict(list)
    feasible_by_config: dict[str, list[int]] = defaultdict(list)
    for j, l in feasible_pairs:
        feasible_by_op[l].append(j)
        feasible_by_config[j].append(l)

    # 목적 config j_next로 전이 가능한 이전 config j_prev (동일 machine, reconfig cost 존재; j_prev=j_next 포함)
    prev_configs: dict[str, list[str]] = defaultdict(list)
    for (jp, jn) in instance.reconfiguration_cost:
        prev_configs[jn].append(jp)

    first_t = T[0]
    later_ts = [t for t in T if t != first_t]

    x_keys = [(p, j, l) for p in P for (j, l) in feasible_pairs]
    s_keys = [(p, j, l, t) for p in P for (j, l) in feasible_pairs for t in T]

    # 정책별 z arc 생성
    z_keys = []
    for t in later_ts:
        for (jn, l) in feasible_pairs:
            for jp in prev_configs[jn]:
                for k in P:
                    for p in P:
                        if mode_a == "off" and k != p:
                            continue
                        if mode_a == "separate" and k != p and jp != jn:
                            continue
                        z_keys.append((k, p, jp, jn, l, t))

    v_keys = [(p, l, t) for p in P for l in L for t in T]
    flow_keys = _build_flow_keys(instance, P, T, route_arcs)

    x = model.addVars(x_keys, vtype=GRB.BINARY, name="x")
    s = model.addVars(s_keys, vtype=GRB.BINARY, name="s")
    z = model.addVars(z_keys, lb=0.0, ub=1.0, name="z")
    v = model.addVars(v_keys, lb=0.0, name="v")
    f = model.addVars(flow_keys, lb=0.0, name="f")

    fixed_purchases = getattr(config, "FIXED_PURCHASES", None)
    if fixed_purchases is not None:
        fixed_set = set(fixed_purchases)
        invalid = sorted(fixed_set - set(x_keys))
        if invalid:
            raise ValueError(f"Invalid fixed purchase keys: {invalid}")
        for key in x_keys:
            model.addConstr(x[key] == (1 if key in fixed_set else 0), name=f"fixed_purchase[{key}]")

    # 위치당 최대 1대 구매
    for p in P:
        model.addConstr(gp.quicksum(x[p, j, l] for j, l in feasible_pairs) <= 1, name=f"one_rmt[{p}]")
    # 위치당 기간별 점유 <= 1 (relocation이라 구매 위치와 점유 위치가 분리된다)
    for p in P:
        for t in T:
            model.addConstr(gp.quicksum(s[p, j, l, t] for j, l in feasible_pairs) <= 1, name=f"occupancy[{p},{t}]")
    # 첫 기간 상태 = 구매
    for p, j, l in x_keys:
        model.addConstr(s[p, j, l, first_t] == x[p, j, l], name=f"init_state[{p},{j},{l}]")

    # 전이 보존: outflow(t-1의 각 기계는 어디론가) / inflow(점유 = 들어온 전이 합)
    out_by_source: dict[tuple, list] = defaultdict(list)
    in_by_dest: dict[tuple, list] = defaultdict(list)
    for key in z_keys:
        k, p, jp, jn, l, t = key
        out_by_source[(k, jp, t)].append(key)
        in_by_dest[(p, jn, l, t)].append(key)

    for t in later_ts:
        for k in P:
            for jp in feasible_by_config:
                prev_occ = gp.quicksum(
                    s[k, jp, l_prev, t - 1]
                    for l_prev in feasible_by_config[jp]
                    if (k, jp, l_prev, t - 1) in s
                )
                keys = out_by_source.get((k, jp, t), [])
                model.addConstr(gp.quicksum(z[key] for key in keys) == prev_occ, name=f"outflow[{k},{jp},{t}]")

    for t in later_ts:
        for (jn, l) in feasible_pairs:
            for p in P:
                keys = in_by_dest.get((p, jn, l, t), [])
                model.addConstr(s[p, jn, l, t] == gp.quicksum(z[key] for key in keys), name=f"inflow[{p},{jn},{l},{t}]")

    # shared resource (선택; s 기반 기존 구현 재사용)
    res_mode = resource_mode(config)
    cap_ub = getattr(config, "CAP_UPPER_BOUNDS", None)
    cap_vars = _add_shared_resource_constraints(model, instance, P, T, feasible_pairs, s, res_mode, cap_ub)

    # capacity
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

    # flow layer (base와 동일)
    incoming: dict[tuple, list] = defaultdict(list)
    outgoing: dict[tuple, list] = defaultdict(list)
    for key in flow_keys:
        p, left, q, right, t = key
        if left != instance.start_operation:
            outgoing[(p, left, t)].append(key)
        if right != instance.end_operation:
            incoming[(q, right, t)].append(key)
    for p in P:
        for l in L:
            for t in T:
                model.addConstr(gp.quicksum(f[key] for key in incoming[p, l, t]) == v[p, l, t])
                model.addConstr(gp.quicksum(f[key] for key in outgoing[p, l, t]) == v[p, l, t])
    for t in T:
        for left, right in route_arcs:
            required = instance.arc_demand.get((t, left, right), 0.0)
            if required <= 0:
                continue
            arc_flow = gp.quicksum(f[key] for key in flow_keys if key[1] == left and key[3] == right and key[4] == t)
            model.addConstr(arc_flow == required, name=f"arc_demand[{t},{left},{right}]")

    # 비용
    purchase_cost = gp.quicksum(instance.cost[j] * x[p, j, l] for p, j, l in x_keys)
    reconfiguration_cost = gp.quicksum(
        instance.reconfiguration_cost[jp, jn] * z[k, p, jp, jn, l, t]
        for (k, p, jp, jn, l, t) in z_keys
        if jp != jn
    )
    move_cost = gp.quicksum(
        instance.cost[jp] * (alpha + beta * instance.distance[k, p]) * z[k, p, jp, jn, l, t]
        for (k, p, jp, jn, l, t) in z_keys
        if k != p
    )
    handling_cost = gp.quicksum(
        instance.parameters["material_handling_cost"] * instance.distance[p, q] * f[p, left, q, right, t]
        for p, left, q, right, t in flow_keys
    )

    cost_expr = purchase_cost + reconfiguration_cost + handling_cost + move_cost
    model.setObjective(cost_expr, GRB.MINIMIZE)
    lp_relaxation_bound, lp_relaxation_seconds = _compute_lp_relaxation_bound(model, config)
    if cap_vars is not None:
        model.ModelSense = GRB.MINIMIZE
        model.setObjectiveN(cost_expr, index=0, priority=1, name="cost")
        model.setObjectiveN(gp.quicksum(cap_vars[r] for r in cap_vars), index=1, priority=0, name="sizing")
        _apply_stage_time_limits(model, config)

    if bool(getattr(config, "USE_OBJECTIVE_CUTOFF", False)):
        cutoff = getattr(config, "OBJECTIVE_CUTOFF", None)
        if cutoff is not None:
            model.Params.Cutoff = float(cutoff)

    model.optimize()

    return _extract_solution(
        model, instance, x, s, z, v, f,
        purchase_cost, reconfiguration_cost, handling_cost, move_cost,
        lp_relaxation_bound, lp_relaxation_seconds, cap_vars, mode_a, alpha, beta,
    )


def _build_flow_keys(instance, locations, periods, route_arcs):
    flow_keys = []
    for t in periods:
        for left, right in route_arcs:
            if instance.arc_demand.get((t, left, right), 0.0) <= 0:
                continue
            from_locations = [instance.start_location] if left == instance.start_operation else locations
            to_locations = [instance.end_location] if right == instance.end_operation else locations
            for p in from_locations:
                for q in to_locations:
                    if p != q:
                        flow_keys.append((p, left, q, right, t))
    return flow_keys


def _extract_solution(
    model, instance, x, s, z, v, f,
    purchase_cost, reconfiguration_cost, handling_cost, move_cost,
    lp_relaxation_bound, lp_relaxation_seconds, cap_vars, mode_a, alpha, beta,
) -> RMSSolution:
    status_name = {
        GRB.OPTIMAL: "OPTIMAL",
        GRB.TIME_LIMIT: "TIME_LIMIT",
        GRB.INFEASIBLE: "INFEASIBLE",
        GRB.INF_OR_UNBD: "INF_OR_UNBD",
        # multi-objective에서 일부 pass가 시간 초과로 미증명이면 SUBOPTIMAL이 나온다.
        GRB.SUBOPTIMAL: "SUBOPTIMAL",
    }.get(model.Status, str(model.Status))
    summary: dict[str, Any] = {
        "problem_name": instance.problem_name,
        "model_type": f"adaptive_{mode_a}",
        "adaptive_mode": mode_a,
        "status": int(model.Status),
        "status_name": status_name,
        "periods": instance.periods,
        "operations": instance.operations,
    }
    summary.update(_solver_metrics(model))
    summary["lp_relaxation_bound"] = lp_relaxation_bound
    summary["lp_relaxation_seconds"] = lp_relaxation_seconds
    summary["num_cap_vars"] = len(cap_vars) if cap_vars is not None else 0

    if not model.SolCount:
        return RMSSolution(summary=summary)

    total_cost = _clean_float(
        purchase_cost.getValue() + reconfiguration_cost.getValue()
        + handling_cost.getValue() + move_cost.getValue()
    )
    cost_breakdown = {
        "purchase_cost": _clean_float(purchase_cost.getValue()),
        "reconfiguration_cost": _clean_float(reconfiguration_cost.getValue()),
        "material_handling_cost": _clean_float(handling_cost.getValue()),
        "relocation_cost": _clean_float(move_cost.getValue()),
        "total_objective": total_cost,
    }
    summary["objective"] = total_cost

    purchased = []
    for (p, j, l), var in sorted(x.items()):
        if var.X > 0.5:
            purchased.append({
                "location": p, "machine": instance.machine[j], "configuration": j,
                "initial_operation": l, "purchase_cost": instance.cost[j],
            })

    flow_by_node = {(p, l, t): var.X for (p, l, t), var in v.items()}
    states = []
    for (p, j, l, t), var in sorted(s.items(), key=lambda it: (it[0][3], it[0][0], it[0][1], it[0][2])):
        if var.X > 0.5:
            states.append({
                "period": t, "location": p, "machine": instance.machine[j], "configuration": j,
                "operation": l, "flow": round(flow_by_node.get((p, l, t), 0.0), 6),
            })

    reconfigs = []
    relocations = []
    for (k, p, jp, jn, l, t), var in sorted(z.items(), key=lambda it: (it[0][5], it[0][0], it[0][1])):
        if var.X <= 0.5:
            continue
        if jp != jn:
            reconfigs.append({
                "period": t, "location": p,
                "from_machine": instance.machine[jp], "from_configuration": jp,
                "to_machine": instance.machine[jn], "to_configuration": jn,
                "operation": l, "reconfiguration_cost": instance.reconfiguration_cost[jp, jn],
            })
        if k != p:
            relocations.append({
                "period": t, "from_location": k, "to_location": p,
                "configuration": jp if jp == jn else f"{jp}->{jn}",
                "distance": instance.distance[k, p],
                "relocation_cost": _clean_float(instance.cost[jp] * (alpha + beta * instance.distance[k, p])),
            })

    flows = []
    for (p, left, q, right, t), var in sorted(f.items(), key=lambda it: (it[0][4], it[0][0], it[0][2])):
        if var.X > 1e-6:
            distance = instance.distance[p, q]
            mhc = instance.parameters["material_handling_cost"]
            flows.append({
                "period": t, "from_location": p, "from_operation": left,
                "to_location": q, "to_operation": right, "flow": round(var.X, 6),
                "distance": distance, "mhc": mhc, "flow_cost": round(var.X * distance * mhc, 6),
            })

    resource_usage = []
    usage_resources = sorted(cap_vars) if cap_vars is not None else sorted(instance.shared_resource_capacity)
    for resource in usage_resources:
        capacity = (
            int(round(cap_vars[resource].X)) if cap_vars is not None
            else instance.shared_resource_capacity[resource]
        )
        for t in instance.periods:
            usage = sum(
                instance.resource_requirement[j, resource] * var.X
                for (p, j, l, period), var in s.items()
                if period == t and (j, resource) in instance.resource_requirement
            )
            resource_usage.append({
                "period": t, "resource": resource, "usage": round(usage, 6),
                "capacity": capacity, "slack": round(capacity - usage, 6),
            })

    summary["n_relocations"] = len(relocations)
    summary["relocation_cost"] = cost_breakdown["relocation_cost"]

    return RMSSolution(
        summary=summary,
        purchased_machines=purchased,
        machine_states=states,
        reconfigurations=reconfigs,
        material_flows=flows,
        resource_usage=resource_usage,
        cost_breakdown=cost_breakdown,
        relocations=relocations,
    )
