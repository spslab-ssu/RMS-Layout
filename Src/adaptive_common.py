from __future__ import annotations

from collections import defaultdict
from typing import Any

import gurobipy as gp
from gurobipy import GRB


def configure_model(model: gp.Model, config) -> None:
    model.Params.TimeLimit = float(config.TIME_LIMIT)
    model.Params.MIPGap = float(config.MIP_GAP)
    model.Params.OutputFlag = int(getattr(config, "OUTPUT_FLAG", 1))
    if getattr(config, "SEED", None) is not None:
        model.Params.Seed = int(config.SEED)
    if getattr(config, "THREADS", None) is not None:
        model.Params.Threads = int(config.THREADS)


def build_flow_keys(instance) -> list[tuple[int, int, int, int, int]]:
    keys: list[tuple[int, int, int, int, int]] = []
    for t in instance.periods:
        for left, right in instance.route_arcs:
            if instance.arc_demand.get((t, left, right), 0.0) <= 0:
                continue
            from_locations = (
                [instance.start_location]
                if left == instance.start_operation
                else instance.install_locations
            )
            to_locations = (
                [instance.end_location]
                if right == instance.end_operation
                else instance.install_locations
            )
            for p in from_locations:
                for q in to_locations:
                    if p != q:
                        keys.append((p, left, q, right, t))
    return keys


def add_material_flow_layer(model, instance, state_capacity):
    """Add the paper's material-flow layer around an adaptive state model.

    ``state_capacity(p, l, t)`` must return the total capacity installed at
    location p for operation l in period t.
    """
    P = instance.install_locations
    L = instance.operations
    T = instance.periods
    flow_keys = build_flow_keys(instance)
    v = model.addVars([(p, l, t) for p in P for l in L for t in T], lb=0.0, name="v")
    f = model.addVars(flow_keys, lb=0.0, name="f")

    for p in P:
        for l in L:
            for t in T:
                model.addConstr(v[p, l, t] <= state_capacity(p, l, t), name=f"capacity[{p},{l},{t}]")

    incoming: dict[tuple[int, int, int], list[tuple[int, int, int, int, int]]] = defaultdict(list)
    outgoing: dict[tuple[int, int, int], list[tuple[int, int, int, int, int]]] = defaultdict(list)
    for key in flow_keys:
        p, left, q, right, t = key
        if left != instance.start_operation:
            outgoing[p, left, t].append(key)
        if right != instance.end_operation:
            incoming[q, right, t].append(key)

    for p in P:
        for l in L:
            for t in T:
                model.addConstr(gp.quicksum(f[key] for key in incoming[p, l, t]) == v[p, l, t])
                model.addConstr(gp.quicksum(f[key] for key in outgoing[p, l, t]) == v[p, l, t])

    for t in T:
        for left, right in instance.route_arcs:
            required = instance.arc_demand.get((t, left, right), 0.0)
            if required <= 0:
                continue
            model.addConstr(
                gp.quicksum(
                    f[key]
                    for key in flow_keys
                    if key[1] == left and key[3] == right and key[4] == t
                )
                == required,
                name=f"arc_demand[{t},{left},{right}]",
            )

    handling_cost = gp.quicksum(
        instance.parameters["material_handling_cost"]
        * instance.distance[p, q]
        * f[p, left, q, right, t]
        for p, left, q, right, t in flow_keys
    )
    return v, f, handling_cost


def add_shared_resource_constraints(model, instance, state_usage) -> None:
    """Apply the same optional configuration-module capacity constraints."""
    for resource, capacity in instance.shared_resource_capacity.items():
        for t in instance.periods:
            model.addConstr(
                state_usage(resource, t) <= capacity,
                name=f"shared_resource[{resource},{t}]",
            )


def material_flow_rows(instance, f) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (p, left, q, right, t), var in sorted(
        f.items(), key=lambda item: (item[0][4], item[0][0], item[0][2])
    ):
        if var.X <= 1e-6:
            continue
        distance = instance.distance[p, q]
        mhc = instance.parameters["material_handling_cost"]
        rows.append(
            {
                "period": t,
                "from_location": p,
                "from_operation": left,
                "to_location": q,
                "to_operation": right,
                "flow": round(var.X, 6),
                "distance": distance,
                "mhc": mhc,
                "flow_cost": clean_float(var.X * distance * mhc),
            }
        )
    return rows


def solver_summary(model, instance, formulation: str) -> dict[str, Any]:
    status_name = {
        GRB.OPTIMAL: "OPTIMAL",
        GRB.TIME_LIMIT: "TIME_LIMIT",
        GRB.INFEASIBLE: "INFEASIBLE",
        GRB.INF_OR_UNBD: "INF_OR_UNBD",
    }.get(model.Status, str(model.Status))
    summary: dict[str, Any] = {
        "problem_name": instance.problem_name,
        "formulation": formulation,
        "status": int(model.Status),
        "status_name": status_name,
        "periods": instance.periods,
        "operations": instance.operations,
        "runtime_seconds": float(model.Runtime),
        "solution_count": int(model.SolCount),
        "node_count": float(model.NodeCount),
        "model_size": {
            "variables": int(model.NumVars),
            "binary_variables": int(model.NumBinVars),
            "integer_variables": int(model.NumIntVars),
            "continuous_variables": int(model.NumVars - model.NumIntVars),
            "constraints": int(model.NumConstrs),
        },
    }
    if model.SolCount:
        summary.update(
            {
                "objective": clean_float(model.ObjVal),
                "upper_bound": clean_float(model.ObjVal),
                "lower_bound": clean_float(model.ObjBound),
                "mip_gap": float(model.MIPGap) if model.IsMIP else 0.0,
            }
        )
    return summary


def clean_float(value: float, tolerance: float = 1e-4) -> float:
    value = float(value)
    nearest = round(value)
    return float(nearest) if abs(value - nearest) <= tolerance else round(value, 6)
