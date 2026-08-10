from __future__ import annotations

from collections import defaultdict

import gurobipy as gp
from gurobipy import GRB

from Src.adaptive_common import (
    add_material_flow_layer,
    add_shared_resource_constraints,
    clean_float,
    configure_model,
    material_flow_rows,
    solver_summary,
)
from Src.milp import RMSSolution


def solve_network_adaptive_milp(instance, config) -> RMSSolution:
    """Reference implementation of main's network + adaptive mechanism."""
    model = gp.Model(f"rms_network_adaptive_{instance.problem_name}")
    configure_model(model, config)

    P = list(instance.install_locations)
    T = list(instance.periods)
    pairs = list(instance.feasible_pairs)
    first_period = T[0]
    period_pairs = list(zip(T[:-1], T[1:]))
    previous_period = {next_t: prev_t for prev_t, next_t in period_pairs}

    feasible_by_op: dict[int, list[str]] = defaultdict(list)
    for j, l in pairs:
        feasible_by_op[l].append(j)

    w_keys = [(p, j, l, t) for p in P for j, l in pairs for t in T]
    transition_keys = [
        (p_prev, p_next, j_prev, l_prev, j_next, l_next, next_t)
        for p_prev in P
        for p_next in P
        for j_prev, l_prev in pairs
        for j_next, l_next in pairs
        for _, next_t in period_pairs
        if (j_prev, j_next) in instance.reconfiguration_cost
    ]
    w = model.addVars(w_keys, vtype=GRB.BINARY, name="w")
    transition_vtype = (
        GRB.BINARY if bool(getattr(config, "NETWORK_BINARY_ARCS", True)) else GRB.CONTINUOUS
    )
    a = model.addVars(
        transition_keys,
        lb=0.0,
        ub=1.0,
        vtype=transition_vtype,
        name="adaptive_transition",
    )

    fixed_purchases = getattr(config, "FIXED_PURCHASES", None)
    if fixed_purchases is not None:
        fixed_set = set(fixed_purchases)
        valid = {(p, j, l) for p in P for j, l in pairs}
        invalid = sorted(fixed_set - valid)
        if invalid:
            raise ValueError(f"Invalid fixed purchase keys: {invalid}")
        for p, j, l in valid:
            model.addConstr(
                w[p, j, l, first_period] == (1 if (p, j, l) in fixed_set else 0),
                name=f"fixed_purchase[{p},{j},{l}]",
            )

    # Source layer and per-period location occupancy.
    for p in P:
        model.addConstr(
            gp.quicksum(w[p, j, l, first_period] for j, l in pairs) <= 1,
            name=f"one_purchase_per_location[{p}]",
        )
        for t in T:
            model.addConstr(
                gp.quicksum(w[p, j, l, t] for j, l in pairs) <= 1,
                name=f"one_machine_per_location_period[{p},{t}]",
            )

    arcs_from: dict[tuple[int, str, int, int], list[tuple]] = defaultdict(list)
    arcs_to: dict[tuple[int, str, int, int], list[tuple]] = defaultdict(list)
    for key in transition_keys:
        p_prev, p_next, j_prev, l_prev, j_next, l_next, next_t = key
        prev_t = previous_period[next_t]
        arcs_from[p_prev, j_prev, l_prev, prev_t].append(key)
        arcs_to[p_next, j_next, l_next, next_t].append(key)

    # Main's adaptive mechanism: each occupied state sends exactly one unit to
    # a state in the next period, possibly at a different location.  Every
    # occupied next-period state receives exactly one unit.
    for prev_t, next_t in period_pairs:
        for p in P:
            for j, l in pairs:
                model.addConstr(
                    gp.quicksum(a[key] for key in arcs_from[p, j, l, prev_t])
                    == w[p, j, l, prev_t],
                    name=f"adaptive_out[{p},{j},{l},{prev_t}]",
                )
                model.addConstr(
                    gp.quicksum(a[key] for key in arcs_to[p, j, l, next_t])
                    == w[p, j, l, next_t],
                    name=f"adaptive_in[{p},{j},{l},{next_t}]",
                )

    add_shared_resource_constraints(
        model,
        instance,
        lambda resource, t: gp.quicksum(
            instance.resource_requirement[j, resource] * w[p, j, l, t]
            for p in P
            for j, l in pairs
            if (j, resource) in instance.resource_requirement
        ),
    )
    v, f, handling_cost = add_material_flow_layer(
        model,
        instance,
        lambda p, l, t: gp.quicksum(
            instance.production_rate[j, l] * w[p, j, l, t]
            for j in feasible_by_op[l]
        ),
    )

    purchase_cost = gp.quicksum(
        instance.cost[j] * w[p, j, l, first_period]
        for p in P
        for j, l in pairs
    )
    reconfiguration_cost = gp.quicksum(
        instance.reconfiguration_cost[j_prev, j_next] * a[key]
        for key in transition_keys
        for p_prev, p_next, j_prev, l_prev, j_next, l_next, next_t in [key]
        if j_prev != j_next
    )
    relocation_unit = float(getattr(config, "RELOCATION_COST_PER_DISTANCE", 1.0))
    relocation_fixed = float(getattr(config, "RELOCATION_FIXED_COST", 0.0))
    relocation_cost = gp.quicksum(
        (relocation_unit * instance.distance[p_prev, p_next] + relocation_fixed) * a[key]
        for key in transition_keys
        for p_prev, p_next, j_prev, l_prev, j_next, l_next, next_t in [key]
        if p_prev != p_next
    )

    model.setObjective(
        purchase_cost + reconfiguration_cost + relocation_cost + handling_cost,
        GRB.MINIMIZE,
    )
    model.optimize()
    return _extract_solution(
        model,
        instance,
        T,
        w,
        a,
        v,
        f,
        purchase_cost,
        reconfiguration_cost,
        relocation_cost,
        handling_cost,
        relocation_unit,
        relocation_fixed,
    )


def _extract_solution(
    model,
    instance,
    periods,
    w,
    transitions,
    v,
    f,
    purchase_cost,
    reconfiguration_cost,
    relocation_cost,
    handling_cost,
    relocation_unit,
    relocation_fixed,
) -> RMSSolution:
    summary = solver_summary(model, instance, "machine_lifecycle_network_adaptive")
    summary["adaptive_mechanism"] = "cross-location lifecycle transition arcs"
    if not model.SolCount:
        return RMSSolution(summary=summary)

    first_period = periods[0]
    flow_by_node = {(p, l, t): var.X for (p, l, t), var in v.items()}
    purchased = []
    states = []
    for (p, j, l, t), var in sorted(w.items(), key=lambda item: (item[0][3], item[0][0])):
        if var.X <= 0.5:
            continue
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
        if t == first_period:
            purchased.append(
                {
                    "location": p,
                    "machine": instance.machine[j],
                    "configuration": j,
                    "initial_operation": l,
                    "purchase_cost": instance.cost[j],
                }
            )

    transition_rows = []
    for key, var in sorted(transitions.items(), key=lambda item: (item[0][6], item[0][0], item[0][1])):
        if var.X <= 0.5:
            continue
        p_prev, p_next, j_prev, _l_prev, j_next, l_next, t = key
        if p_prev == p_next and j_prev == j_next:
            continue
        distance = instance.distance[p_prev, p_next] if p_prev != p_next else 0.0
        transition_rows.append(
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
                "reconfiguration_cost": (
                    instance.reconfiguration_cost[j_prev, j_next] if j_prev != j_next else 0.0
                ),
                "relocation_distance": distance,
                "relocation_cost": clean_float(
                    relocation_unit * distance + (relocation_fixed if p_prev != p_next else 0.0)
                ),
            }
        )

    cost_breakdown = {
        "purchase_cost": clean_float(purchase_cost.getValue()),
        "reconfiguration_cost": clean_float(reconfiguration_cost.getValue()),
        "relocation_cost": clean_float(relocation_cost.getValue()),
        "material_handling_cost": clean_float(handling_cost.getValue()),
        "total_objective": clean_float(model.ObjVal),
    }
    summary["relocation_count"] = sum(
        1 for row in transition_rows if row["from_location"] != row["to_location"]
    )
    summary["reconfiguration_count"] = sum(
        1 for row in transition_rows if row["from_configuration"] != row["to_configuration"]
    )
    return RMSSolution(
        summary=summary,
        purchased_machines=purchased,
        machine_states=states,
        reconfigurations=transition_rows,
        material_flows=material_flow_rows(instance, f),
        cost_breakdown=cost_breakdown,
    )
