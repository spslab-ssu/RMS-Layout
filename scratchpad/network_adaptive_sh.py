from __future__ import annotations

from collections import defaultdict
import math
from dataclasses import dataclass, field
from typing import Any

import gurobipy as gp
from gurobipy import GRB


@dataclass
class RMSSolution:
    """output.py가 파일로 저장할 표준 solution container."""

    summary: dict[str, Any]
    purchased_machines: list[dict[str, Any]] = field(default_factory=list)
    machine_states: list[dict[str, Any]] = field(default_factory=list)
    reconfigurations: list[dict[str, Any]] = field(default_factory=list)
    material_flows: list[dict[str, Any]] = field(default_factory=list)
    resource_usage: list[dict[str, Any]] = field(default_factory=list)
    cost_breakdown: dict[str, float] = field(default_factory=dict)


def solve_milp(instance, config) -> RMSSolution:
    """Full adaptive layout을 허용하는 time-expanded network MILP를 생성하고 푼다.

    기존 network model은 같은 위치 안에서만 period 간 state가 이어진다.
    이 모델은 transition arc가 이전 위치 p_prev와 다음 위치 p_next를 모두 포함해
    period 사이 RMT relocation을 허용한다.
    """
    model = gp.Model(f"rms_layout_network_adaptive_{instance.problem_name}")
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

    feasible_by_op: dict[int, list[str]] = defaultdict(list)
    feasible_by_config: dict[str, list[int]] = defaultdict(list)
    for j, l in feasible_pairs:
        feasible_by_op[l].append(j)
        feasible_by_config[j].append(l)

    node_keys = [(p, j, l, t) for p in P for (j, l) in feasible_pairs for t in T]
    purchase_arc_keys = [(p, j, l) for p in P for (j, l) in feasible_pairs]
    max_relocation_distance = _read_max_relocation_distance(config)
    transition_arc_keys, transition_arc_stats = _build_transition_arc_keys(
        instance,
        P,
        T,
        feasible_pairs,
        max_relocation_distance=max_relocation_distance,
    )
    sink_arc_keys = [(p, j, l) for p in P for (j, l) in feasible_pairs]

    v_keys = [(p, l, t) for p in P for l in L for t in T]
    flow_keys = _build_flow_keys(instance, P, T, route_arcs)

    s = model.addVars(node_keys, vtype=GRB.BINARY, name="s")
    x = model.addVars(purchase_arc_keys, vtype=GRB.BINARY, name="x")

    transition_vtype = GRB.BINARY if bool(getattr(config, "NETWORK_BINARY_ARCS", True)) else GRB.CONTINUOUS
    z = model.addVars(transition_arc_keys, lb=0.0, ub=1.0, vtype=transition_vtype, name="z")
    e = model.addVars(sink_arc_keys, lb=0.0, ub=1.0, vtype=transition_vtype, name="e")

    v = model.addVars(v_keys, lb=0.0, name="v")
    f = model.addVars(flow_keys, lb=0.0, name="f")

    _add_fixed_purchase_constraints(model, x, purchase_arc_keys, config)
    _add_network_constraints(model, P, T, feasible_pairs, s, x, z, e)
    _add_shared_resource_constraints(model, instance, P, T, feasible_pairs, s)
    _add_capacity_constraints(model, instance, P, L, T, feasible_by_op, s, v)
    _add_flow_constraints(model, instance, P, L, T, route_arcs, flow_keys, v, f)

    purchase_cost = gp.quicksum(instance.cost[j] * x[p, j, l] for p, j, l in purchase_arc_keys)
    reconfiguration_cost = gp.quicksum(
        instance.reconfiguration_cost[j_prev, j_next] * z[p_prev, p_next, t, j_prev, l_prev, j_next, l_next]
        for p_prev, p_next, t, j_prev, l_prev, j_next, l_next in transition_arc_keys
    )
    relocation_unit_cost = float(getattr(config, "RELOCATION_COST_PER_DISTANCE", 100.0))
    relocation_fixed_cost = float(getattr(config, "RELOCATION_FIXED_COST", 0.0))
    relocation_cost = gp.quicksum(
        (relocation_unit_cost * instance.distance[p_prev, p_next] + relocation_fixed_cost)
        * z[p_prev, p_next, t, j_prev, l_prev, j_next, l_next]
        for p_prev, p_next, t, j_prev, l_prev, j_next, l_next in transition_arc_keys
        if p_prev != p_next
    )
    model._relocation_cost_per_distance = relocation_unit_cost
    model._relocation_fixed_cost = relocation_fixed_cost
    model._max_relocation_distance = max_relocation_distance
    model._transition_arc_stats = transition_arc_stats
    handling_cost = gp.quicksum(
        instance.parameters["material_handling_cost"] * instance.distance[p, q] * f[p, left, q, right, t]
        for p, left, q, right, t in flow_keys
    )

    model.setObjective(purchase_cost + reconfiguration_cost + relocation_cost + handling_cost, GRB.MINIMIZE)
    lp_relaxation_bound = _compute_lp_relaxation_bound(model, config)

    if bool(getattr(config, "USE_WARM_START", False)):
        raise ValueError("network model은 아직 기존 warm start CSV 적용을 지원하지 않습니다. MODEL_TYPE='base'로 실행하거나 USE_WARM_START=False로 설정하세요.")

    if bool(getattr(config, "USE_OBJECTIVE_CUTOFF", False)):
        cutoff = getattr(config, "OBJECTIVE_CUTOFF", None)
        if cutoff is not None:
            model.Params.Cutoff = float(cutoff)

    model.optimize()

    return _extract_solution(
        model=model,
        instance=instance,
        s=s,
        x=x,
        z=z,
        v=v,
        f=f,
        purchase_cost=purchase_cost,
        reconfiguration_cost=reconfiguration_cost,
        relocation_cost=relocation_cost,
        handling_cost=handling_cost,
        lp_relaxation_bound=lp_relaxation_bound,
    )


def _read_max_relocation_distance(config) -> float | None:
    """config의 distance limit을 읽는다. None이면 full adaptive 이동을 허용한다."""
    value = getattr(config, "MAX_RELOCATION_DISTANCE", None)
    if value in {None, ""}:
        return None
    value = float(value)
    if value < 0:
        raise ValueError(f"MAX_RELOCATION_DISTANCE must be nonnegative or None, got {value}")
    return value


def _build_transition_arc_keys(instance, locations, periods, feasible_pairs, max_relocation_distance=None):
    """period 사이 위치 이동까지 포함한 가능한 state 전이 arc를 만든다."""
    if len(periods) <= 1:
        return [], {
            "max_relocation_distance": max_relocation_distance,
            "allowed_transition_arc_count": 0,
            "blocked_transition_arc_count": 0,
        }
    keys = []
    blocked = 0
    for p_prev in locations:
        for p_next in locations:
            if max_relocation_distance is not None and instance.distance[p_prev, p_next] > max_relocation_distance:
                blocked += _transition_pair_count(periods, feasible_pairs, instance)
                continue
            for t in periods:
                if t == periods[0]:
                    continue
                for j_prev, l_prev in feasible_pairs:
                    for j_next, l_next in feasible_pairs:
                        if instance.machine[j_prev] != instance.machine[j_next]:
                            continue
                        if (j_prev, j_next) not in instance.reconfiguration_cost:
                            continue
                        keys.append((p_prev, p_next, t, j_prev, l_prev, j_next, l_next))
    return keys, {
        "max_relocation_distance": max_relocation_distance,
        "allowed_transition_arc_count": len(keys),
        "blocked_transition_arc_count": blocked,
    }


def _transition_pair_count(periods, feasible_pairs, instance) -> int:
    """하나의 위치쌍에서 만들 수 있는 transition arc 수를 계산한다."""
    count = 0
    for t in periods:
        if t == periods[0]:
            continue
        for j_prev, _l_prev in feasible_pairs:
            for j_next, _l_next in feasible_pairs:
                if instance.machine[j_prev] != instance.machine[j_next]:
                    continue
                if (j_prev, j_next) not in instance.reconfiguration_cost:
                    continue
                count += 1
    return count

def _build_flow_keys(instance, locations, periods, route_arcs):
    """기존 base MILP와 동일한 material flow key를 만든다."""
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


def _add_fixed_purchase_constraints(model, x, purchase_arc_keys, config) -> None:
    """논문 Figure 해와 비교할 때 purchase arc를 강제로 고정한다."""
    fixed_purchases = getattr(config, "FIXED_PURCHASES", None)
    if fixed_purchases is None:
        return
    fixed_set = set(fixed_purchases)
    invalid = sorted(fixed_set - set(purchase_arc_keys))
    if invalid:
        raise ValueError(f"Invalid fixed purchase keys for network model: {invalid}")
    for key in purchase_arc_keys:
        model.addConstr(x[key] == (1 if key in fixed_set else 0), name=f"fixed_purchase[{key}]")


def _add_network_constraints(model, locations, periods, feasible_pairs, s, x, z, e) -> None:
    """machine lifecycle path를 만들되, period 사이 location 이동을 허용한다."""
    first_period = periods[0]
    last_period = periods[-1]

    # 첫 period에 같은 location에는 최대 한 대만 구매/설치한다.
    for p in locations:
        model.addConstr(
            gp.quicksum(x[p, j, l] for j, l in feasible_pairs) <= 1,
            name=f"one_purchase_per_location[{p}]",
        )

    # adaptive transition으로 여러 machine이 같은 위치에 모이지 않도록 period별 위치 점유를 제한한다.
    for p in locations:
        for t in periods:
            model.addConstr(
                gp.quicksum(s[p, j, l, t] for j, l in feasible_pairs) <= 1,
                name=f"one_machine_per_location_period[{p},{t}]",
            )

    incoming_transition = defaultdict(list)
    outgoing_transition = defaultdict(list)
    for key in z.keys():
        p_prev, p_next, t, j_prev, l_prev, j_next, l_next = key
        outgoing_transition[(p_prev, j_prev, l_prev, t - 1)].append(key)
        incoming_transition[(p_next, j_next, l_next, t)].append(key)

    for p in locations:
        for t in periods:
            for j, l in feasible_pairs:
                node = (p, j, l, t)
                if t == first_period:
                    incoming = x[p, j, l]
                else:
                    incoming = gp.quicksum(z[key] for key in incoming_transition[node])

                if t == last_period:
                    outgoing = e[p, j, l]
                else:
                    outgoing = gp.quicksum(z[key] for key in outgoing_transition[node])

                model.addConstr(incoming == s[node], name=f"node_in[{p},{j},{l},{t}]")
                model.addConstr(s[node] == outgoing, name=f"node_out[{p},{j},{l},{t}]")

def _add_shared_resource_constraints(model, instance, locations, periods, feasible_pairs, s) -> None:
    """shared resource 사용량 제약. network state 변수 s를 사용한다."""
    for resource, capacity in instance.shared_resource_capacity.items():
        for t in periods:
            usage = gp.quicksum(
                instance.resource_requirement[j, resource] * s[p, j, l, t]
                for p in locations
                for j, l in feasible_pairs
                if (j, resource) in instance.resource_requirement and (p, j, l, t) in s
            )
            model.addConstr(usage <= capacity, name=f"shared_resource[{resource},{t}]")


def _add_capacity_constraints(model, instance, locations, operations, periods, feasible_by_op, s, v) -> None:
    """location-operation 처리량은 해당 period state의 생산률 합 이하로 제한한다."""
    for p in locations:
        for l in operations:
            for t in periods:
                model.addConstr(
                    v[p, l, t]
                    <= gp.quicksum(
                        instance.production_rate[j, l] * s[p, j, l, t]
                        for j in feasible_by_op[l]
                        if (p, j, l, t) in s
                    ),
                    name=f"capacity[{p},{l},{t}]",
                )


def _add_flow_constraints(model, instance, locations, operations, periods, route_arcs, flow_keys, v, f) -> None:
    """기존 base MILP와 동일한 flow balance와 route arc demand 제약을 추가한다."""
    incoming: dict[tuple[int, int, int], list[tuple[int, int, int, int, int]]] = defaultdict(list)
    outgoing: dict[tuple[int, int, int], list[tuple[int, int, int, int, int]]] = defaultdict(list)
    for key in flow_keys:
        p, left, q, right, t = key
        if left != instance.start_operation:
            outgoing[(p, left, t)].append(key)
        if right != instance.end_operation:
            incoming[(q, right, t)].append(key)

    for p in locations:
        for l in operations:
            for t in periods:
                model.addConstr(gp.quicksum(f[key] for key in incoming[p, l, t]) == v[p, l, t])
                model.addConstr(gp.quicksum(f[key] for key in outgoing[p, l, t]) == v[p, l, t])

    for t in periods:
        for left, right in route_arcs:
            required = instance.arc_demand.get((t, left, right), 0.0)
            if required <= 0:
                continue
            arc_flow = gp.quicksum(
                f[key] for key in flow_keys if key[1] == left and key[3] == right and key[4] == t
            )
            model.addConstr(arc_flow == required, name=f"arc_demand[{t},{left},{right}]")


def _extract_solution(
    model,
    instance,
    s,
    x,
    z,
    v,
    f,
    purchase_cost,
    reconfiguration_cost,
    relocation_cost,
    handling_cost,
    lp_relaxation_bound,
) -> RMSSolution:
    """Network 변수값을 기존 output.py가 저장하는 표준 row list로 변환한다."""
    status_name = {
        GRB.OPTIMAL: "OPTIMAL",
        GRB.TIME_LIMIT: "TIME_LIMIT",
        GRB.INFEASIBLE: "INFEASIBLE",
        GRB.INF_OR_UNBD: "INF_OR_UNBD",
    }.get(model.Status, str(model.Status))
    summary: dict[str, Any] = {
        "problem_name": instance.problem_name,
        "model_type": "network_adaptive",
        "status": int(model.Status),
        "status_name": status_name,
        "periods": instance.periods,
        "operations": instance.operations,
    }
    summary.update(_solver_metrics(model))
    summary["lp_relaxation_bound"] = lp_relaxation_bound
    summary.update(getattr(model, "_transition_arc_stats", {}))

    if not model.SolCount:
        return RMSSolution(summary=summary)

    cost_breakdown = {
        "purchase_cost": _clean_float(purchase_cost.getValue()),
        "reconfiguration_cost": _clean_float(reconfiguration_cost.getValue()),
        "relocation_cost": _clean_float(relocation_cost.getValue()),
        "material_handling_cost": _clean_float(handling_cost.getValue()),
        "total_objective": _clean_float(model.ObjVal),
    }
    summary.update(
        {
            "objective": _clean_float(model.ObjVal),
        }
    )

    purchased = []
    for (p, j, l), var in sorted(x.items()):
        if var.X > 0.5:
            purchased.append(
                {
                    "location": p,
                    "machine": instance.machine[j],
                    "configuration": j,
                    "initial_operation": l,
                    "purchase_cost": instance.cost[j],
                }
            )

    flow_by_node = {(p, l, t): var.X for (p, l, t), var in v.items()}
    states = []
    for (p, j, l, t), var in sorted(s.items(), key=lambda item: (item[0][3], item[0][0], item[0][1], item[0][2])):
        if var.X > 0.5:
            states.append(
                {
                    "period": t,
                    "location": p,
                    "machine": instance.machine[j],
                    "configuration": j,
                    "operation": l,
                    "flow": round(flow_by_node.get((p, l, t), 0.0), 6),
                }
            )

    reconfigs = []
    relocation_unit_cost = float(getattr(model, "_relocation_cost_per_distance", 100.0))
    relocation_fixed_cost = float(getattr(model, "_relocation_fixed_cost", 0.0))
    for (p_prev, p_next, t, j_prev, _l_prev, j_next, l_next), var in sorted(
        z.items(), key=lambda item: (item[0][2], item[0][0], item[0][1], item[0][3], item[0][5], item[0][6])
    ):
        if var.X > 0.5 and (j_prev != j_next or p_prev != p_next):
            relocation_distance = instance.distance[p_prev, p_next] if p_prev != p_next else 0.0
            relocation_row_cost = relocation_unit_cost * relocation_distance + (relocation_fixed_cost if p_prev != p_next else 0.0)
            reconfigs.append(
                {
                    "period": t,
                    "location": p_next,
                    "from_location": p_prev,
                    "to_location": p_next,
                    "from_machine": instance.machine[j_prev],
                    "from_configuration": j_prev,
                    "to_machine": instance.machine[j_next],
                    "to_configuration": j_next,
                    "operation": l_next,
                    "reconfiguration_cost": instance.reconfiguration_cost[j_prev, j_next] if j_prev != j_next else 0.0,
                    "relocation_distance": relocation_distance,
                    "relocation_cost": round(relocation_row_cost, 6),
                }
            )

    flows = []
    for (p, left, q, right, t), var in sorted(f.items(), key=lambda item: (item[0][4], item[0][0], item[0][2])):
        if var.X > 1e-6:
            distance = instance.distance[p, q]
            mhc = instance.parameters["material_handling_cost"]
            flows.append(
                {
                    "period": t,
                    "from_location": p,
                    "from_operation": left,
                    "to_location": q,
                    "to_operation": right,
                    "flow": round(var.X, 6),
                    "distance": distance,
                    "mhc": mhc,
                    "flow_cost": round(var.X * distance * mhc, 6),
                }
            )

    resource_usage = []
    for resource, capacity in sorted(instance.shared_resource_capacity.items()):
        for t in instance.periods:
            usage = sum(
                instance.resource_requirement[j, resource] * var.X
                for (p, j, l, period), var in s.items()
                if period == t and (j, resource) in instance.resource_requirement
            )
            resource_usage.append(
                {
                    "period": t,
                    "resource": resource,
                    "usage": round(usage, 6),
                    "capacity": capacity,
                    "slack": round(capacity - usage, 6),
                }
            )

    return RMSSolution(
        summary=summary,
        purchased_machines=purchased,
        machine_states=states,
        reconfigurations=reconfigs,
        material_flows=flows,
        resource_usage=resource_usage,
        cost_breakdown=cost_breakdown,
    )


def _clean_float(value: float, integer_tolerance: float = 1e-3) -> float | None:
    """Gurobi numerical noise를 사람이 읽기 좋은 값으로 정리한다."""
    value = float(value)
    if not math.isfinite(value):
        return None
    nearest_integer = round(value)
    if abs(value - nearest_integer) <= integer_tolerance:
        return float(nearest_integer)
    return round(value, 6)


def _compute_lp_relaxation_bound(model, config) -> float | None:
    """선택적으로 pure LP relaxation bound를 계산한다.

    MIP solve 전에 별도 relaxation model을 한 번 풀기 때문에 큰 instance에서는
    시간이 추가로 든다. 필요할 때만 config.COMPUTE_LP_RELAXATION_BOUND=True로 켠다.
    """
    if not bool(getattr(config, "COMPUTE_LP_RELAXATION_BOUND", False)):
        return None
    model.update()
    relaxation = model.relax()
    relaxation.Params.OutputFlag = 0
    relaxation.optimize()
    if relaxation.Status != GRB.OPTIMAL:
        return None
    return _clean_float(relaxation.ObjVal)


def _solver_metrics(model) -> dict[str, float | int | None]:
    """formulation 비교에 필요한 Gurobi solve 지표를 summary에 기록한다."""
    metrics: dict[str, float | int | None] = {
        "runtime_seconds": float(model.Runtime),
        "num_vars": int(model.NumVars),
        "num_constraints": int(model.NumConstrs),
        "node_count": float(model.NodeCount),
        "simplex_iterations": float(model.IterCount),
    }
    if model.IsMIP:
        metrics["mip_gap"] = _safe_model_attr(model, "MIPGap")
        metrics["best_bound"] = _safe_model_attr(model, "ObjBound")
        metrics["best_bound_c"] = _safe_model_attr(model, "ObjBoundC")
    else:
        metrics["mip_gap"] = 0.0
        metrics["best_bound"] = _safe_model_attr(model, "ObjVal")
        metrics["best_bound_c"] = _safe_model_attr(model, "ObjVal")
    return metrics


def _safe_model_attr(model, name: str):
    """status에 따라 존재하지 않을 수 있는 Gurobi attribute를 안전하게 읽는다."""
    try:
        value = getattr(model, name)
    except (AttributeError, gp.GurobiError):
        return None
    value = float(value)
    if not math.isfinite(value) or abs(value) >= GRB.INFINITY:
        return None
    return _clean_float(value)
