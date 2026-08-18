"""Full-enumeration Dantzig-Wolfe master for the RMS machine schedules.

Each column is one feasible, full-horizon (configuration, operation) trajectory
for one installed RMT.  This is the explicit-column counterpart of the compact
machine-lifecycle network formulation and is intended for controlled research
comparisons on the four-period paper instances.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from itertools import product
from typing import Any

import gurobipy as gp
from gurobipy import GRB

from Src.milp import RMSSolution
from Src.strengthening import add_strengthening_cuts, resolve_profile


@dataclass(frozen=True)
class ScheduleColumn:
    id: int
    machine: str
    states: tuple[tuple[str, int], ...]
    purchase_cost: float
    reconfiguration_cost: float


def enumerate_schedule_columns(instance) -> list[ScheduleColumn]:
    """Enumerate every same-machine full-horizon state trajectory."""
    states_by_machine: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for configuration, operation in instance.feasible_pairs:
        states_by_machine[instance.machine[configuration]].append((configuration, operation))

    columns: list[ScheduleColumn] = []
    for machine in sorted(states_by_machine):
        states = sorted(states_by_machine[machine])
        for trajectory in product(states, repeat=len(instance.periods)):
            reconfiguration_cost = sum(
                instance.reconfiguration_cost[previous[0], current[0]]
                for previous, current in zip(trajectory[:-1], trajectory[1:])
                if previous[0] != current[0]
            )
            columns.append(
                ScheduleColumn(
                    id=len(columns),
                    machine=machine,
                    states=trajectory,
                    purchase_cost=instance.cost[trajectory[0][0]],
                    reconfiguration_cost=reconfiguration_cost,
                )
            )
    return columns


def solve_schedule_dw(instance, config) -> RMSSolution:
    if bool(getattr(config, "OPTIMIZE_SHARED_RESOURCE_CAPACITY", False)):
        raise ValueError("schedule_dw comparison does not support resource-capacity optimization")

    model = gp.Model(f"rms_schedule_dw_{instance.problem_name}")
    model.Params.TimeLimit = float(config.TIME_LIMIT)
    model.Params.MIPGap = float(config.MIP_GAP)
    model.Params.OutputFlag = int(getattr(config, "OUTPUT_FLAG", 1))
    if getattr(config, "SEED", None) is not None:
        model.Params.Seed = int(config.SEED)
    if getattr(config, "THREADS", None) is not None:
        model.Params.Threads = int(config.THREADS)

    P, L, T = instance.install_locations, instance.operations, instance.periods
    columns = enumerate_schedule_columns(instance)
    column_by_id = {column.id: column for column in columns}
    lp_relaxation = bool(getattr(config, "LP_RELAXATION", False))
    lambda_vtype = GRB.CONTINUOUS if lp_relaxation else GRB.BINARY
    lam = model.addVars(
        [(p, column.id) for p in P for column in columns],
        lb=0.0,
        ub=1.0,
        vtype=lambda_vtype,
        name="lambda",
    )

    for p in P:
        model.addConstr(
            gp.quicksum(lam[p, column.id] for column in columns) <= 1,
            name=f"one_schedule_per_location[{p}]",
        )

    # State expressions let the exact same valid-inequality generator be used
    # by both formulations without introducing auxiliary state variables.
    state_columns: dict[tuple[str, int, int], list[int]] = defaultdict(list)
    for column in columns:
        for period_index, period in enumerate(T):
            configuration, operation = column.states[period_index]
            state_columns[configuration, operation, period].append(column.id)
    w = {
        (p, configuration, operation, period): gp.quicksum(
            lam[p, column_id]
            for column_id in state_columns[configuration, operation, period]
        )
        for p in P
        for configuration, operation in instance.feasible_pairs
        for period in T
    }

    fixed_purchases = getattr(config, "FIXED_PURCHASES", None)
    if fixed_purchases is not None:
        fixed_set = set(fixed_purchases)
        for p in P:
            for configuration, operation in instance.feasible_pairs:
                model.addConstr(
                    w[p, configuration, operation, T[0]]
                    == (1 if (p, configuration, operation) in fixed_set else 0),
                    name=f"fixed_purchase[{p},{configuration},{operation}]",
                )

    v = model.addVars([(p, operation, period) for p in P for operation in L for period in T], lb=0.0, name="v")
    flow_keys = _flow_keys(instance)
    f = model.addVars(flow_keys, lb=0.0, name="f")

    for p in P:
        for operation in L:
            for period in T:
                model.addConstr(
                    v[p, operation, period]
                    <= gp.quicksum(
                        instance.production_rate[configuration, operation]
                        * w[p, configuration, operation, period]
                        for configuration, feasible_operation in instance.feasible_pairs
                        if feasible_operation == operation
                    ),
                    name=f"capacity[{p},{operation},{period}]",
                )

    if instance.shared_resource_capacity:
        for resource, capacity in instance.shared_resource_capacity.items():
            for period in T:
                model.addConstr(
                    gp.quicksum(
                        instance.resource_requirement[configuration, resource]
                        * w[p, configuration, operation, period]
                        for p in P
                        for configuration, operation in instance.feasible_pairs
                        if (configuration, resource) in instance.resource_requirement
                    )
                    <= capacity,
                    name=f"shared_resource[{resource},{period}]",
                )

    strengthening = add_strengthening_cuts(model, w, instance, config)
    _add_material_flow_constraints(model, f, v, flow_keys, instance)

    purchase_cost = gp.quicksum(
        column.purchase_cost * lam[p, column.id] for p in P for column in columns
    )
    reconfiguration_cost = gp.quicksum(
        column.reconfiguration_cost * lam[p, column.id] for p in P for column in columns
    )
    handling_cost = gp.quicksum(
        instance.parameters["material_handling_cost"]
        * instance.distance[p, q]
        * f[p, left, q, right, period]
        for p, left, q, right, period in flow_keys
    )
    model.setObjective(purchase_cost + reconfiguration_cost + handling_cost, GRB.MINIMIZE)
    recorder = getattr(config, "PROGRESS_RECORDER", None)
    if recorder is None:
        model.optimize()
    else:
        model.optimize(recorder)
        recorder.finish(model)

    profile, _ = resolve_profile(config)
    return _extract_solution(
        model=model,
        instance=instance,
        columns=column_by_id,
        lam=lam,
        v=v,
        f=f,
        purchase_cost=purchase_cost,
        reconfiguration_cost=reconfiguration_cost,
        handling_cost=handling_cost,
        profile=profile,
        strengthening=strengthening.to_dict(),
        lp_relaxation=lp_relaxation,
    )


def _flow_keys(instance) -> list[tuple[int, int, int, int, int]]:
    keys = []
    for period in instance.periods:
        for left, right in instance.route_arcs:
            if instance.arc_demand.get((period, left, right), 0.0) <= 0:
                continue
            from_locations = [instance.start_location] if left == instance.start_operation else instance.install_locations
            to_locations = [instance.end_location] if right == instance.end_operation else instance.install_locations
            keys.extend(
                (p, left, q, right, period)
                for p in from_locations
                for q in to_locations
                if p != q
            )
    return keys


def _add_material_flow_constraints(model, f, v, flow_keys, instance) -> None:
    incoming: dict[tuple[int, int, int], list[tuple]] = defaultdict(list)
    outgoing: dict[tuple[int, int, int], list[tuple]] = defaultdict(list)
    for key in flow_keys:
        p, left, q, right, period = key
        if left != instance.start_operation:
            outgoing[p, left, period].append(key)
        if right != instance.end_operation:
            incoming[q, right, period].append(key)
    for p in instance.install_locations:
        for operation in instance.operations:
            for period in instance.periods:
                model.addConstr(gp.quicksum(f[key] for key in incoming[p, operation, period]) == v[p, operation, period])
                model.addConstr(gp.quicksum(f[key] for key in outgoing[p, operation, period]) == v[p, operation, period])
    for period in instance.periods:
        for left, right in instance.route_arcs:
            required = instance.arc_demand.get((period, left, right), 0.0)
            if required <= 0:
                continue
            model.addConstr(
                gp.quicksum(
                    f[key] for key in flow_keys
                    if key[1] == left and key[3] == right and key[4] == period
                ) == required,
                name=f"arc_demand[{period},{left},{right}]",
            )


def _extract_solution(
    model, instance, columns, lam, v, f, purchase_cost, reconfiguration_cost,
    handling_cost, profile, strengthening, lp_relaxation,
) -> RMSSolution:
    status_name = {
        GRB.OPTIMAL: "OPTIMAL", GRB.TIME_LIMIT: "TIME_LIMIT",
        GRB.INFEASIBLE: "INFEASIBLE", GRB.INF_OR_UNBD: "INF_OR_UNBD",
    }.get(model.Status, str(model.Status))
    summary: dict[str, Any] = {
        "problem_name": instance.problem_name,
        "formulation": "schedule_dantzig_wolfe_full_enumeration",
        "strengthening_profile": profile,
        "strengthening": strengthening,
        "lp_relaxation": lp_relaxation,
        "status": int(model.Status),
        "status_name": status_name,
        "periods": instance.periods,
        "operations": instance.operations,
        "schedule_column_count": len(columns),
        "model_size": {
            "variables": int(model.NumVars),
            "binary_variables": int(model.NumBinVars),
            "integer_variables": int(model.NumIntVars),
            "continuous_variables": int(model.NumVars - model.NumIntVars),
            "constraints": int(model.NumConstrs),
        },
        "runtime_seconds": float(model.Runtime),
        "solution_count": int(model.SolCount),
        "node_count": float(model.NodeCount),
    }
    if not model.SolCount:
        return RMSSolution(summary=summary)

    costs = {
        "purchase_cost": _clean(purchase_cost.getValue()),
        "reconfiguration_cost": _clean(reconfiguration_cost.getValue()),
        "material_handling_cost": _clean(handling_cost.getValue()),
    }
    costs["total_objective"] = _clean(sum(costs.values()))
    summary.update(
        {
            "objective": costs["total_objective"],
            "upper_bound": costs["total_objective"],
            "lower_bound": _clean(model.ObjBound),
            "absolute_gap": _clean(model.ObjVal - model.ObjBound),
            "mip_gap": float(model.MIPGap) if model.IsMIP else 0.0,
            "optimization_mode": "system_cost",
            "resource_counting_mode": "disabled",
        }
    )

    selected = sorted(
        ((p, columns[column_id]) for (p, column_id), variable in lam.items() if variable.X > 0.5),
        key=lambda item: item[0],
    )
    purchased, states, reconfigurations = [], [], []
    for p, column in selected:
        initial_configuration, initial_operation = column.states[0]
        purchased.append(
            {"location": p, "machine": column.machine, "configuration": initial_configuration,
             "initial_operation": initial_operation, "purchase_cost": instance.cost[initial_configuration]}
        )
        for index, period in enumerate(instance.periods):
            configuration, operation = column.states[index]
            states.append(
                {"period": period, "location": p, "machine": column.machine,
                 "configuration": configuration, "operation": operation,
                 "flow": round(v[p, operation, period].X, 6)}
            )
            if index and configuration != column.states[index - 1][0]:
                previous = column.states[index - 1][0]
                reconfigurations.append(
                    {"period": period, "location": p, "from_machine": column.machine,
                     "from_configuration": previous, "to_machine": column.machine,
                     "to_configuration": configuration, "operation": operation,
                     "reconfiguration_cost": instance.reconfiguration_cost[previous, configuration]}
                )

    flows = []
    for (p, left, q, right, period), variable in sorted(f.items()):
        if variable.X <= 1e-6:
            continue
        distance = instance.distance[p, q]
        mhc = instance.parameters["material_handling_cost"]
        flows.append(
            {"period": period, "from_location": p, "from_operation": left,
             "to_location": q, "to_operation": right, "flow": round(variable.X, 6),
             "distance": distance, "mhc": mhc,
             "flow_cost": round(variable.X * distance * mhc, 6)}
        )
    return RMSSolution(
        summary=summary, purchased_machines=purchased, machine_states=states,
        reconfigurations=reconfigurations, material_flows=flows, cost_breakdown=costs,
    )


def _clean(value: float, tolerance: float = 1e-3) -> float:
    value = float(value)
    nearest = round(value)
    return float(nearest) if abs(value - nearest) <= tolerance else round(value, 6)
