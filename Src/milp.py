from __future__ import annotations

from collections import defaultdict
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
    """단일/다중부품을 공통으로 처리하는 RMS Layout MILP를 생성하고 푼다."""
    model = gp.Model(f"rms_layout_{instance.problem_name}")
    model.Params.TimeLimit = config.TIME_LIMIT
    model.Params.MIPGap = config.MIP_GAP

    P = instance.install_locations
    J = instance.configurations
    L = instance.operations
    T = instance.periods
    feasible_pairs = instance.feasible_pairs
    route_arcs = instance.route_arcs

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
    v_keys = [(p, l, t) for p in P for l in L for t in T] # period t에 위치 p에서 operation l의 flow량

    flow_keys = []
    for t in T:
        for left, right in route_arcs:
            if instance.arc_demand.get((t, left, right), 0.0) <= 0:
                continue
            from_locations = [instance.start_location] if left == instance.start_operation else P
            to_locations = [instance.end_location] if right == instance.end_operation else P
            for p in from_locations:
                for q in to_locations:
                    if p != q:
                        flow_keys.append((p, left, q, right, t))

    x = model.addVars(x_keys, vtype=GRB.BINARY, name="x") 

    # 선택 사항: 논문 Figure 2(a)처럼 초기 구매 배치를 강제로 고정해 비교할 때 사용한다.
    # config.FIXED_PURCHASES = [(p, j, l), ...] 형식으로 전달한다.
    fixed_purchases = getattr(config, "FIXED_PURCHASES", None)
    if fixed_purchases is not None:
        fixed_set = set(fixed_purchases)
        invalid = sorted(fixed_set - set(x_keys))
        if invalid:
            raise ValueError(f"Invalid fixed purchase keys: {invalid}")
        for key in x_keys:
            model.addConstr(x[key] == (1 if key in fixed_set else 0), name=f"fixed_purchase[{key}]")

    s = model.addVars(s_keys, vtype=GRB.BINARY, name="s") #period t에 위치 p에 configuration j, operation l 상태이면 1
    y = model.addVars(y_keys, vtype=GRB.BINARY, name="y") #period t에 위치 p에서 configuration j_prev에서 j_next로 operation l로 재구성하면 1
    v = model.addVars(v_keys, lb=0.0, name="v")           #위치 p, configuration j, operation l 설치하면 1 
    f = model.addVars(flow_keys, lb=0.0, name="f")        #period t에 위치 p에서 operation left에서 위치 q로 operation right로 flow량

    feasible_by_op: dict[int, list[str]] = defaultdict(list)
    feasible_by_config: dict[str, list[int]] = defaultdict(list)
    for j, l in feasible_pairs:
        feasible_by_op[l].append(j)
        feasible_by_config[j].append(l)

    # 위치 하나에는 최대 하나의 RMT만 설치한다.
    for p in P:
        purchased_at_p = gp.quicksum(x[p, j, l] for j, l in feasible_pairs)
        model.addConstr(purchased_at_p <= 1, name=f"one_rmt_per_location[{p}]")
        for t in T:
            # 구매된 RMT는 매 period 하나의 상태를 가진다. flow=0이면 idle 상태다.
            model.addConstr(
                gp.quicksum(s[p, j, l, t] for j, l in feasible_pairs) == purchased_at_p,
                name=f"one_state_if_purchased[{p},{t}]",
            )

    # 첫 period state는 구매 의사결정과 일치한다.
    for p, j, l in x_keys:
        model.addConstr(s[p, j, l, 1] == x[p, j, l], name=f"initial_state[{p},{j},{l}]")

    # 두 번째 period부터는 같은 configuration 유지 또는 재구성으로만 state 전이가 가능하다.
    for p in P:
        for t in T:
            if t == 1:
                continue
            for j, l in feasible_pairs:
                same_config_previous = gp.quicksum(
                    s[p, j, prev_l, t - 1]
                    for prev_l in feasible_by_config[j]
                    if (p, j, prev_l, t - 1) in s
                )
                reconfigured_to_current = gp.quicksum(
                    y[p, j_prev, j, l, t]
                    for j_prev in J
                    if (p, j_prev, j, l, t) in y
                )
                model.addConstr(
                    s[p, j, l, t] <= same_config_previous + reconfigured_to_current,
                    name=f"state_transition[{p},{j},{l},{t}]",
                )

    # 재구성 변수는 이전 state와 현재 state가 모두 있을 때만 1이 될 수 있다.
    for p, j_prev, j_next, l, t in y_keys:
        previous_state = gp.quicksum(
            s[p, j_prev, prev_l, t - 1]
            for prev_l in feasible_by_config[j_prev]
            if (p, j_prev, prev_l, t - 1) in s
        )
        model.addConstr(y[p, j_prev, j_next, l, t] <= previous_state)
        model.addConstr(y[p, j_prev, j_next, l, t] <= s[p, j_next, l, t])

    # RMT capacity 제약.
    # 각 auxiliary module은 한정된 shared resource로 보고, period별 동시 점유량을 제한한다.
    for resource, capacity in instance.shared_resource_capacity.items():
        for t in T:
            usage = gp.quicksum(
                s[p, j, l, t]
                for p in P
                for j, l in feasible_pairs
                if resource in instance.auxiliary_modules[j] and (p, j, l, t) in s
            )
            model.addConstr(usage <= capacity, name=f"shared_resource[{resource},{t}]")

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

    incoming: dict[tuple[int, int, int], list[tuple[int, int, int, int, int]]] = defaultdict(list)
    outgoing: dict[tuple[int, int, int], list[tuple[int, int, int, int, int]]] = defaultdict(list)
    for key in flow_keys:
        p, left, q, right, t = key
        if left != instance.start_operation:
            outgoing[(p, left, t)].append(key)
        if right != instance.end_operation:
            incoming[(q, right, t)].append(key)

    # 각 실제 RMT에서 incoming = 처리량 = outgoing이 되도록 flow balance를 둔다.
    for p in P:
        for l in L:
            for t in T:
                model.addConstr(gp.quicksum(f[key] for key in incoming[p, l, t]) == v[p, l, t])
                model.addConstr(gp.quicksum(f[key] for key in outgoing[p, l, t]) == v[p, l, t])

    # route arc별 총 flow는 해당 period의 집계 demand와 같아야 한다.
    for t in T:
        for left, right in route_arcs:
            required = instance.arc_demand.get((t, left, right), 0.0)
            if required <= 0:
                continue
            arc_flow = gp.quicksum(
                f[key] for key in flow_keys if key[1] == left and key[3] == right and key[4] == t
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

    model.setObjective(purchase_cost + reconfiguration_cost + handling_cost, GRB.MINIMIZE)
    model.optimize()

    return _extract_solution(model, instance, x, s, y, v, f, purchase_cost, reconfiguration_cost, handling_cost)


def _extract_solution(model, instance, x, s, y, v, f, purchase_cost, reconfiguration_cost, handling_cost) -> RMSSolution:
    """Gurobi 변수값을 output.py가 저장하기 쉬운 row list로 변환한다."""
    status_name = {
        GRB.OPTIMAL: "OPTIMAL",
        GRB.TIME_LIMIT: "TIME_LIMIT",
        GRB.INFEASIBLE: "INFEASIBLE",
        GRB.INF_OR_UNBD: "INF_OR_UNBD",
    }.get(model.Status, str(model.Status))
    summary: dict[str, Any] = {
        "problem_name": instance.problem_name,
        "status": int(model.Status),
        "status_name": status_name,
        "periods": instance.periods,
        "operations": instance.operations,
    }

    if not model.SolCount:
        return RMSSolution(summary=summary)

    cost_breakdown = {
        "purchase_cost": _clean_float(purchase_cost.getValue()),
        "reconfiguration_cost": _clean_float(reconfiguration_cost.getValue()),
        "material_handling_cost": _clean_float(handling_cost.getValue()),
        "total_objective": _clean_float(model.ObjVal),
    }
    summary.update({"objective": _clean_float(model.ObjVal), "runtime_seconds": float(model.Runtime), "mip_gap": float(model.MIPGap) if model.IsMIP else 0.0})

    purchased = []
    for (p, j, l), var in sorted(x.items()):
        if var.X > 0.5:
            purchased.append({"location": p, "machine": instance.machine[j], "configuration": j, "initial_operation": l, "purchase_cost": instance.cost[j]})

    flow_by_node = {(p, l, t): var.X for (p, l, t), var in v.items()}
    states = []
    for (p, j, l, t), var in sorted(s.items(), key=lambda item: (item[0][3], item[0][0], item[0][1], item[0][2])):
        if var.X > 0.5:
            states.append({"period": t, "location": p, "machine": instance.machine[j], "configuration": j, "operation": l, "flow": round(flow_by_node.get((p, l, t), 0.0), 6)})

    reconfigs = []
    for (p, j_prev, j_next, l, t), var in sorted(y.items(), key=lambda item: (item[0][4], item[0][0])):
        if var.X > 0.5:
            reconfigs.append({"period": t, "location": p, "from_machine": instance.machine[j_prev], "from_configuration": j_prev, "to_machine": instance.machine[j_next], "to_configuration": j_next, "operation": l, "reconfiguration_cost": instance.reconfiguration_cost[j_prev, j_next]})

    flows = []
    for (p, left, q, right, t), var in sorted(f.items(), key=lambda item: (item[0][4], item[0][0], item[0][2])):
        if var.X > 1e-6:
            distance = instance.distance[p, q]
            mhc = instance.parameters["material_handling_cost"]
            flows.append({"period": t, "from_location": p, "from_operation": left, "to_location": q, "to_operation": right, "flow": round(var.X, 6), "distance": distance, "mhc": mhc, "flow_cost": round(var.X * distance * mhc, 6)})

    resource_usage = []
    for resource, capacity in sorted(instance.shared_resource_capacity.items()):
        for t in instance.periods:
            usage = sum(
                var.X
                for (p, j, l, period), var in s.items()
                if period == t and resource in instance.auxiliary_modules[j]
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

    return RMSSolution(summary=summary, purchased_machines=purchased, machine_states=states, reconfigurations=reconfigs, material_flows=flows, resource_usage=resource_usage, cost_breakdown=cost_breakdown)


def _clean_float(value: float, integer_tolerance: float = 1e-3) -> float:
    """Gurobi numerical noise를 사람이 읽기 좋은 값으로 정리한다."""
    value = float(value)
    nearest_integer = round(value)
    if abs(value - nearest_integer) <= integer_tolerance:
        return float(nearest_integer)
    return round(value, 6)
