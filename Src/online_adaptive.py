from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from typing import Any

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


@dataclass(frozen=True)
class AssetState:
    asset: int
    machine: str
    location: int
    configuration: str
    operation: int


@dataclass
class PeriodDecision:
    period: int
    status_name: str
    summary: dict[str, Any]
    next_assets: dict[int, AssetState]
    purchased: list[dict[str, Any]]
    states: list[dict[str, Any]]
    transitions: list[dict[str, Any]]
    material_flows: list[dict[str, Any]]
    costs: dict[str, float]


def solve_online_adaptive(instance, config, on_reveal=None) -> RMSSolution:
    """Reveal one period's demand at a time and execute a myopic decision.

    Past purchases and the latest physical state are irreversible inputs to the
    next period.  No demand from a future period is included in a period model.
    Purchases are immediate; retirement/sale and purchase lead times are not
    part of the current policy.
    """
    assets: dict[int, AssetState] = {}
    decisions: list[PeriodDecision] = []

    for period in instance.periods:
        if on_reveal is not None:
            on_reveal(period, _period_demand(instance, period))
        decision = solve_online_period(instance, config, period, assets)
        decisions.append(decision)
        if not decision.next_assets:
            break
        assets = decision.next_assets

    purchased = [row for decision in decisions for row in decision.purchased]
    states = [row for decision in decisions for row in decision.states]
    transitions = [row for decision in decisions for row in decision.transitions]
    flows = [row for decision in decisions for row in decision.material_flows]
    period_costs = [decision.costs for decision in decisions if decision.costs]

    total_costs = {
        key: clean_float(sum(row.get(key, 0.0) for row in period_costs))
        for key in (
            "purchase_cost",
            "reconfiguration_cost",
            "relocation_cost",
            "material_handling_cost",
        )
    }
    total_costs["total_objective"] = clean_float(sum(total_costs.values()))

    all_optimal = len(decisions) == len(instance.periods) and all(
        decision.status_name == "OPTIMAL" for decision in decisions
    )
    any_without_solution = any(not decision.costs for decision in decisions)
    status_name = (
        "PERIOD_OPTIMAL_POLICY"
        if all_optimal
        else "NO_SOLUTION"
        if any_without_solution
        else "FEASIBLE_POLICY"
    )
    summary = {
        "problem_name": instance.problem_name,
        "formulation": "online_myopic_paper_adaptive",
        "policy": "current-period demand only",
        "status_name": status_name,
        "policy_periods_completed": len(period_costs),
        "periods": instance.periods,
        "operations": instance.operations,
        "objective": total_costs["total_objective"] if period_costs else None,
        "purchase_count": len(purchased),
        "final_owned_rmt_count": len(assets),
        "relocation_count": sum(
            1 for row in transitions if row["from_location"] != row["to_location"]
        ),
        "reconfiguration_count": sum(
            1 for row in transitions if row["from_configuration"] != row["to_configuration"]
        ),
        "information_available_by_period": {
            str(period): {"revealed_periods": [period], "future_demand_used": False}
            for period in instance.periods
        },
        "period_solves": [decision.summary for decision in decisions],
        "optimality_note": (
            "Every period subproblem was solved optimally. This does not make the sequential policy a perfect-information global optimum."
            if all_optimal
            else "One or more period subproblems was not proven optimal."
        ),
    }
    return RMSSolution(
        summary=summary,
        purchased_machines=purchased,
        machine_states=states,
        reconfigurations=transitions,
        material_flows=flows,
        period_costs=period_costs,
        cost_breakdown=total_costs,
    )


def solve_online_period(
    instance,
    config,
    period: int,
    existing_assets: dict[int, AssetState],
) -> PeriodDecision:
    """Solve exactly one revealed-demand period conditional on executed state."""
    if period not in instance.periods:
        raise ValueError(f"Unknown period: {period}")

    period_instance = copy(instance)
    period_instance.periods = [period]
    period_instance.arc_demand = {
        key: value for key, value in instance.arc_demand.items() if key[0] == period
    }
    # This explicit audit field makes accidental future-demand use detectable
    # in tests and in the saved period metadata.
    revealed_arc_demand = dict(period_instance.arc_demand)

    model = gp.Model(f"rms_online_{instance.problem_name}_period_{period}")
    configure_model(model, config)
    P = list(instance.install_locations)
    pairs = list(instance.feasible_pairs)

    allowed_pairs: dict[int, list[tuple[str, int]]] = {}
    for k, asset in existing_assets.items():
        allowed_pairs[k] = [
            (j, l)
            for j, l in pairs
            if instance.machine[j] == asset.machine
            and (asset.configuration, j) in instance.reconfiguration_cost
        ]
        if not allowed_pairs[k]:
            raise ValueError(f"Asset {k} has no feasible state in period {period}.")

    existing_keys = [
        (k, p, j, l)
        for k in sorted(existing_assets)
        for p in P
        for j, l in allowed_pairs[k]
    ]
    old_state = model.addVars(existing_keys, vtype=GRB.BINARY, name="existing_state")
    new_state = model.addVars(
        [(p, j, l) for p in P for j, l in pairs],
        vtype=GRB.BINARY,
        name="new_purchase_state",
    )

    for k in sorted(existing_assets):
        model.addConstr(
            gp.quicksum(old_state[k, p, j, l] for p in P for j, l in allowed_pairs[k]) == 1,
            name=f"one_state_existing[{k}]",
        )

    for p in P:
        model.addConstr(
            gp.quicksum(
                old_state[k, p, j, l]
                for k in sorted(existing_assets)
                for j, l in allowed_pairs[k]
            )
            + gp.quicksum(new_state[p, j, l] for j, l in pairs)
            <= 1,
            name=f"one_machine_per_location[{p}]",
        )

    # New machines have no asset labels in the MILP, which removes purchase
    # symmetry. Stable IDs are assigned after optimization for the next period.
    add_shared_resource_constraints(
        model,
        period_instance,
        lambda resource, _t: gp.quicksum(
            instance.resource_requirement[j, resource] * old_state[k, p, j, l]
            for k in sorted(existing_assets)
            for p in P
            for j, l in allowed_pairs[k]
            if (j, resource) in instance.resource_requirement
        )
        + gp.quicksum(
            instance.resource_requirement[j, resource] * new_state[p, j, l]
            for p in P
            for j, l in pairs
            if (j, resource) in instance.resource_requirement
        ),
    )

    feasible_by_op: dict[int, list[str]] = {}
    for operation in instance.operations:
        feasible_by_op[operation] = [j for j, l in pairs if l == operation]

    v, f, handling_cost = add_material_flow_layer(
        model,
        period_instance,
        lambda p, l, _t: gp.quicksum(
            instance.production_rate[j, l] * old_state[k, p, j, l]
            for k in sorted(existing_assets)
            for j in feasible_by_op[l]
            if (k, p, j, l) in old_state
        )
        + gp.quicksum(
            instance.production_rate[j, l] * new_state[p, j, l]
            for j in feasible_by_op[l]
        ),
    )

    purchase_cost = gp.quicksum(
        instance.cost[j] * new_state[p, j, l]
        for p in P
        for j, l in pairs
    )
    reconfiguration_cost = gp.quicksum(
        instance.reconfiguration_cost[existing_assets[k].configuration, j]
        * old_state[k, p, j, l]
        for k in sorted(existing_assets)
        for p in P
        for j, l in allowed_pairs[k]
        if j != existing_assets[k].configuration
    )
    relocation_unit = float(getattr(config, "RELOCATION_COST_PER_DISTANCE", 1.0))
    relocation_fixed = float(getattr(config, "RELOCATION_FIXED_COST", 0.0))
    relocation_cost = gp.quicksum(
        (
            relocation_unit * instance.distance[existing_assets[k].location, p]
            + relocation_fixed
        )
        * old_state[k, p, j, l]
        for k in sorted(existing_assets)
        for p in P
        for j, l in allowed_pairs[k]
        if p != existing_assets[k].location
    )

    total_current_cost = purchase_cost + reconfiguration_cost + relocation_cost + handling_cost
    installed_capacity = gp.quicksum(
        instance.production_rate[j, l] * old_state[k, p, j, l]
        for k in sorted(existing_assets)
        for p in P
        for j, l in allowed_pairs[k]
    ) + gp.quicksum(
        instance.production_rate[j, l] * new_state[p, j, l]
        for p in P
        for j, l in pairs
    )

    model.setObjective(total_current_cost, GRB.MINIMIZE)
    model.optimize()
    primary_summary = solver_summary(model, period_instance, "online_period_implication_adaptive")
    primary_cost = float(total_current_cost.getValue()) if model.SolCount else None
    secondary_summary = None
    if (
        bool(getattr(config, "ONLINE_CAPACITY_TIE_BREAK", True))
        and model.Status == GRB.OPTIMAL
        and model.SolCount
    ):
        tolerance = float(getattr(config, "ONLINE_PRIMARY_COST_TOLERANCE", 1e-4))
        model.addConstr(
            total_current_cost <= primary_cost + tolerance,
            name=f"preserve_period_cost_optimum[{period}]",
        )
        remaining_time = max(0.001, float(config.TIME_LIMIT) - float(model.Runtime))
        model.Params.TimeLimit = remaining_time
        model.setObjective(installed_capacity, GRB.MAXIMIZE)
        model.optimize()
        secondary_summary = solver_summary(
            model, period_instance, "online_period_capacity_tie_break"
        )

    period_summary = dict(primary_summary)
    if secondary_summary is not None:
        period_summary["runtime_seconds"] = float(primary_summary["runtime_seconds"]) + float(
            secondary_summary["runtime_seconds"]
        )
        period_summary["capacity_tie_break"] = {
            "status_name": secondary_summary["status_name"],
            "installed_capacity": clean_float(installed_capacity.getValue()),
            "primary_cost_ceiling": clean_float(primary_cost),
            "rule": "maximize current-operation installed capacity among period-cost-optimal solutions",
        }
        if secondary_summary["status_name"] != "OPTIMAL":
            period_summary["status_name"] = "PRIMARY_OPTIMAL_TIEBREAK_FEASIBLE"
    period_summary.update(
        {
            "period": period,
            "revealed_arc_demand": {
                f"{left}->{right}": value
                for (_t, left, right), value in sorted(revealed_arc_demand.items())
            },
            "future_demand_used": False,
            "existing_rmt_count_before_decision": len(existing_assets),
        }
    )
    if not model.SolCount:
        return PeriodDecision(
            period=period,
            status_name=period_summary["status_name"],
            summary=period_summary,
            next_assets={},
            purchased=[],
            states=[],
            transitions=[],
            material_flows=[],
            costs={},
        )

    selected: dict[int, AssetState] = {}
    states: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    flow_by_node = {(p, l): var.X for (p, l, _t), var in v.items()}
    for (k, p, j, l), var in sorted(old_state.items()):
        if var.X <= 0.5:
            continue
        previous = existing_assets[k]
        current = AssetState(k, previous.machine, p, j, l)
        selected[k] = current
        states.append(_state_row(period, current, flow_by_node.get((p, l), 0.0)))
        if p != previous.location or j != previous.configuration:
            distance = instance.distance[previous.location, p] if p != previous.location else 0.0
            added_modules = sorted(instance.modules[j] - instance.modules[previous.configuration])
            removed_modules = sorted(instance.modules[previous.configuration] - instance.modules[j])
            module_add_cost = (
                len(added_modules) * instance.parameters.get("add_module_cost", 0.0)
            )
            module_remove_cost = (
                len(removed_modules) * instance.parameters.get("remove_module_cost", 0.0)
            )
            transitions.append(
                {
                    "period": period,
                    "asset": k,
                    "location": p,
                    "from_location": previous.location,
                    "to_location": p,
                    "from_machine": previous.machine,
                    "from_configuration": previous.configuration,
                    "to_machine": current.machine,
                    "to_configuration": j,
                    "operation": l,
                    "reconfiguration_cost": (
                        instance.reconfiguration_cost[previous.configuration, j]
                        if j != previous.configuration
                        else 0.0
                    ),
                    "modules_added": ";".join(str(module) for module in added_modules),
                    "modules_removed": ";".join(str(module) for module in removed_modules),
                    "module_add_cost": clean_float(module_add_cost),
                    "module_remove_cost": clean_float(module_remove_cost),
                    "relocation_distance": distance,
                    "relocation_cost": clean_float(
                        relocation_unit * distance
                        + (relocation_fixed if p != previous.location else 0.0)
                    ),
                }
            )

    purchased: list[dict[str, Any]] = []
    next_asset_id = max(existing_assets, default=0) + 1
    for (p, j, l), var in sorted(new_state.items()):
        if var.X <= 0.5:
            continue
        k = next_asset_id
        next_asset_id += 1
        current = AssetState(k, instance.machine[j], p, j, l)
        selected[k] = current
        purchased.append(
            {
                "period": period,
                "asset": k,
                "location": p,
                "machine": current.machine,
                "configuration": j,
                "initial_operation": l,
                "purchase_cost": instance.cost[j],
            }
        )
        states.append(_state_row(period, current, flow_by_node.get((p, l), 0.0)))

    costs = {
        "period": period,
        "demand": _period_demand(instance, period),
        "purchase_cost": clean_float(purchase_cost.getValue()),
        "reconfiguration_cost": clean_float(reconfiguration_cost.getValue()),
        "relocation_cost": clean_float(relocation_cost.getValue()),
        "material_handling_cost": clean_float(handling_cost.getValue()),
        "period_total": clean_float(total_current_cost.getValue()),
        "owned_rmt_count_after_decision": len(selected),
        "purchased_rmt_count": len(purchased),
        "relocation_count": sum(
            1 for row in transitions if row["from_location"] != row["to_location"]
        ),
        "reconfiguration_count": sum(
            1 for row in transitions if row["from_configuration"] != row["to_configuration"]
        ),
    }
    period_summary["owned_rmt_count_after_decision"] = len(selected)
    period_summary["purchased_rmt_count"] = len(purchased)
    return PeriodDecision(
        period=period,
        status_name=period_summary["status_name"],
        summary=period_summary,
        next_assets=selected,
        purchased=purchased,
        states=sorted(states, key=lambda row: row["location"]),
        transitions=transitions,
        material_flows=material_flow_rows(period_instance, f),
        costs=costs,
    )


def _state_row(period: int, state: AssetState, flow: float) -> dict[str, Any]:
    return {
        "period": period,
        "asset": state.asset,
        "location": state.location,
        "machine": state.machine,
        "configuration": state.configuration,
        "operation": state.operation,
        "flow": round(flow, 6),
    }


def _period_demand(instance, period: int) -> float:
    values = [
        value
        for (t, left, _right), value in instance.arc_demand.items()
        if t == period and left == instance.start_operation
    ]
    return clean_float(sum(values))
