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


def solve_adaptive_milp(instance, config) -> RMSSolution:
    """Solve the paper-style implication MILP with relocatable RMT assets.

    This is intentionally not a lifecycle-network formulation.  Each physical
    RMT is tracked with an asset index k.  Binary state, location,
    configuration, reconfiguration, and movement variables are connected by
    ordinary MILP implications.
    """
    model = gp.Model(f"rms_paper_adaptive_{instance.problem_name}")
    configure_model(model, config)

    P = list(instance.install_locations)
    J = list(instance.configurations)
    L = list(instance.operations)
    T = list(instance.periods)
    pairs = list(instance.feasible_pairs)
    first_period = T[0]
    period_pairs = list(zip(T[:-1], T[1:]))
    previous_period = {next_t: prev_t for prev_t, next_t in period_pairs}

    max_assets = int(getattr(config, "ADAPTIVE_MAX_ASSETS", len(P)) or len(P))
    if not 1 <= max_assets <= len(P):
        raise ValueError("ADAPTIVE_MAX_ASSETS must be between 1 and the number of install locations.")
    K = list(range(1, max_assets + 1))

    feasible_by_config: dict[str, list[int]] = defaultdict(list)
    feasible_by_op: dict[int, list[str]] = defaultdict(list)
    for j, l in pairs:
        feasible_by_config[j].append(l)
        feasible_by_op[l].append(j)

    buy = model.addVars(K, vtype=GRB.BINARY, name="buy")
    s = model.addVars(
        [(k, p, j, l, t) for k in K for p in P for j, l in pairs for t in T],
        vtype=GRB.BINARY,
        name="s",
    )
    z = model.addVars([(k, p, t) for k in K for p in P for t in T], vtype=GRB.BINARY, name="z")
    g = model.addVars([(k, j, t) for k in K for j in J for t in T], vtype=GRB.BINARY, name="g")

    reconfiguration_keys = [
        (k, j_prev, j_next, next_t)
        for k in K
        for j_prev in J
        for j_next in J
        for _, next_t in period_pairs
        if j_prev != j_next and (j_prev, j_next) in instance.reconfiguration_cost
    ]
    y = model.addVars(reconfiguration_keys, vtype=GRB.BINARY, name="y")
    move_keys = [
        (k, p_prev, p_next, next_t)
        for k in K
        for p_prev in P
        for p_next in P
        for _, next_t in period_pairs
        if p_prev != p_next
    ]
    move = model.addVars(move_keys, vtype=GRB.BINARY, name="move")

    # A purchased RMT occupies exactly one (location, configuration, operation)
    # state in every period; an unpurchased asset occupies none.
    for k in K:
        for t in T:
            model.addConstr(
                gp.quicksum(s[k, p, j, l, t] for p in P for j, l in pairs) == buy[k],
                name=f"one_state_if_bought[{k},{t}]",
            )

    # At most one RMT may occupy an install location in each period.
    for p in P:
        for t in T:
            model.addConstr(
                gp.quicksum(z[k, p, t] for k in K) <= 1,
                name=f"one_machine_per_location_period[{p},{t}]",
            )

    for k in K:
        for p in P:
            for t in T:
                model.addConstr(
                    z[k, p, t] == gp.quicksum(s[k, p, j, l, t] for j, l in pairs),
                    name=f"link_location[{k},{p},{t}]",
                )
        for j in J:
            for t in T:
                model.addConstr(
                    g[k, j, t]
                    == gp.quicksum(
                        s[k, p, j, l, t]
                        for p in P
                        for l in feasible_by_config[j]
                    ),
                    name=f"link_configuration[{k},{j},{t}]",
                )

    # Fix optional paper-layout purchases without assigning artificial asset IDs.
    fixed_purchases = getattr(config, "FIXED_PURCHASES", None)
    if fixed_purchases is not None:
        fixed_set = set(fixed_purchases)
        valid = {(p, j, l) for p in P for j, l in pairs}
        invalid = sorted(fixed_set - valid)
        if invalid:
            raise ValueError(f"Invalid fixed purchase keys: {invalid}")
        for p, j, l in valid:
            model.addConstr(
                gp.quicksum(s[k, p, j, l, first_period] for k in K)
                == (1 if (p, j, l) in fixed_set else 0),
                name=f"fixed_purchase[{p},{j},{l}]",
            )

    # Configuration change is represented by ordinary implication variables,
    # not by a source-sink lifecycle path.
    for key in reconfiguration_keys:
        k, j_prev, j_next, next_t = key
        prev_t = previous_period[next_t]
        model.addConstr(y[key] >= g[k, j_prev, prev_t] + g[k, j_next, next_t] - 1)
        model.addConstr(y[key] <= g[k, j_prev, prev_t])
        model.addConstr(y[key] <= g[k, j_next, next_t])

    for k in K:
        for _, next_t in period_pairs:
            prev_t = previous_period[next_t]
            for j_next in J:
                model.addConstr(
                    g[k, j_next, next_t]
                    <= g[k, j_next, prev_t]
                    + gp.quicksum(
                        y[k, j_prev, j_next, next_t]
                        for j_prev in J
                        if (k, j_prev, j_next, next_t) in y
                    ),
                    name=f"configuration_transition[{k},{j_next},{next_t}]",
                )

    # A location change activates exactly one move implication for the asset.
    for key in move_keys:
        k, p_prev, p_next, next_t = key
        prev_t = previous_period[next_t]
        model.addConstr(move[key] >= z[k, p_prev, prev_t] + z[k, p_next, next_t] - 1)
        model.addConstr(move[key] <= z[k, p_prev, prev_t])
        model.addConstr(move[key] <= z[k, p_next, next_t])

    # Remove the large interchangeable-asset symmetry without changing the
    # feasible physical layouts: bought IDs are consecutive and ordered by
    # their first-period locations.
    location_rank = {p: rank for rank, p in enumerate(P, start=1)}
    for k in K[:-1]:
        model.addConstr(buy[k] >= buy[k + 1], name=f"buy_order[{k}]")
        model.addConstr(
            gp.quicksum(location_rank[p] * z[k, p, first_period] for p in P)
            <= gp.quicksum(location_rank[p] * z[k + 1, p, first_period] for p in P)
            + len(P) * (1 - buy[k + 1]),
            name=f"initial_location_order[{k}]",
        )

    add_shared_resource_constraints(
        model,
        instance,
        lambda resource, t: gp.quicksum(
            instance.resource_requirement[j, resource] * s[k, p, j, l, t]
            for k in K
            for p in P
            for j, l in pairs
            if (j, resource) in instance.resource_requirement
        ),
    )

    v, f, handling_cost = add_material_flow_layer(
        model,
        instance,
        lambda p, l, t: gp.quicksum(
            instance.production_rate[j, l] * s[k, p, j, l, t]
            for k in K
            for j in feasible_by_op[l]
        ),
    )

    purchase_cost = gp.quicksum(
        instance.cost[j] * s[k, p, j, l, first_period]
        for k in K
        for p in P
        for j, l in pairs
    )
    reconfiguration_cost = gp.quicksum(
        instance.reconfiguration_cost[j_prev, j_next] * y[k, j_prev, j_next, t]
        for k, j_prev, j_next, t in reconfiguration_keys
    )
    relocation_unit = float(getattr(config, "RELOCATION_COST_PER_DISTANCE", 1.0))
    relocation_fixed = float(getattr(config, "RELOCATION_FIXED_COST", 0.0))
    relocation_cost = gp.quicksum(
        (relocation_unit * instance.distance[p_prev, p_next] + relocation_fixed)
        * move[k, p_prev, p_next, t]
        for k, p_prev, p_next, t in move_keys
    )

    model.setObjective(
        purchase_cost + reconfiguration_cost + relocation_cost + handling_cost,
        GRB.MINIMIZE,
    )
    model.optimize()
    return _extract_solution(
        model,
        instance,
        K,
        T,
        s,
        y,
        move,
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
    assets,
    periods,
    s,
    y,
    move,
    v,
    f,
    purchase_cost,
    reconfiguration_cost,
    relocation_cost,
    handling_cost,
    relocation_unit,
    relocation_fixed,
) -> RMSSolution:
    summary = solver_summary(model, instance, "paper_implication_adaptive")
    summary["adaptive_mechanism"] = "asset-indexed relocation implications"
    if not model.SolCount:
        return RMSSolution(summary=summary)

    first_period = periods[0]
    active_states: dict[tuple[int, int], tuple[int, str, int]] = {}
    flow_by_node = {(p, l, t): var.X for (p, l, t), var in v.items()}
    states = []
    for (k, p, j, l, t), var in sorted(s.items(), key=lambda item: (item[0][4], item[0][0])):
        if var.X <= 0.5:
            continue
        active_states[k, t] = (p, j, l)
        states.append(
            {
                "period": t,
                "asset": k,
                "location": p,
                "machine": instance.machine[j],
                "configuration": j,
                "operation": l,
                "flow": round(flow_by_node.get((p, l, t), 0.0), 6),
            }
        )

    purchased = []
    for k in assets:
        if (k, first_period) not in active_states:
            continue
        p, j, l = active_states[k, first_period]
        purchased.append(
            {
                "asset": k,
                "location": p,
                "machine": instance.machine[j],
                "configuration": j,
                "initial_operation": l,
                "purchase_cost": instance.cost[j],
            }
        )

    transitions = []
    for k in assets:
        for prev_t, t in zip(periods[:-1], periods[1:]):
            if (k, prev_t) not in active_states:
                continue
            p_prev, j_prev, _ = active_states[k, prev_t]
            p_next, j_next, l_next = active_states[k, t]
            if p_prev == p_next and j_prev == j_next:
                continue
            distance = instance.distance[p_prev, p_next] if p_prev != p_next else 0.0
            transitions.append(
                {
                    "period": t,
                    "asset": k,
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
    summary["relocation_count"] = sum(1 for row in transitions if row["from_location"] != row["to_location"])
    summary["reconfiguration_count"] = sum(
        1 for row in transitions if row["from_configuration"] != row["to_configuration"]
    )
    return RMSSolution(
        summary=summary,
        purchased_machines=purchased,
        machine_states=states,
        reconfigurations=transitions,
        material_flows=material_flow_rows(instance, f),
        cost_breakdown=cost_breakdown,
    )
