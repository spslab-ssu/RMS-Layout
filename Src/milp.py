from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

import gurobipy as gp
from gurobipy import GRB

from Src.relocation import (
    RelocationPolicy,
    add_relocation_policy,
    add_transition_variables,
    build_transition_keys,
    effective_capacity,
)
from Src.strengthening import add_strengthening_cuts, resolve_profile


@dataclass
class RMSSolution:
    """output.py가 파일로 저장할 표준 solution container."""

    summary: dict[str, Any]
    purchased_machines: list[dict[str, Any]] = field(default_factory=list)
    machine_states: list[dict[str, Any]] = field(default_factory=list)
    reconfigurations: list[dict[str, Any]] = field(default_factory=list)
    relocations: list[dict[str, Any]] = field(default_factory=list)
    material_flows: list[dict[str, Any]] = field(default_factory=list)
    resource_usage: list[dict[str, Any]] = field(default_factory=list)
    shared_resource_capacities: list[dict[str, Any]] = field(default_factory=list)
    cost_breakdown: dict[str, float] = field(default_factory=dict)
    stage_one_purchased_machines: list[dict[str, Any]] = field(default_factory=list)
    stage_one_machine_states: list[dict[str, Any]] = field(default_factory=list)
    stage_one_reconfigurations: list[dict[str, Any]] = field(default_factory=list)
    stage_one_relocations: list[dict[str, Any]] = field(default_factory=list)
    stage_one_material_flows: list[dict[str, Any]] = field(default_factory=list)
    stage_one_candidates: list[dict[str, Any]] = field(default_factory=list)


def solve_milp(instance, config) -> RMSSolution:
    """Machine lifecycle network reformulation으로 RMS Layout MILP를 푼다.

    w는 각 기간의 (configuration, operation) node 점유 이진변수이고,
    z는 연속 transition arc 변수이다. 각 위치의 기계 lifecycle을
    source-sink path로 표현하여 base model의 약한 implication 제약을 제거한다.
    """
    model = gp.Model(f"rms_network_{instance.problem_name}")
    model.Params.TimeLimit = config.TIME_LIMIT
    model.Params.MIPGap = config.MIP_GAP
    model.Params.OutputFlag = int(getattr(config, "OUTPUT_FLAG", 1))
    if getattr(config, "SEED", None) is not None:
        model.Params.Seed = int(config.SEED)
    if getattr(config, "THREADS", None) is not None:
        model.Params.Threads = int(config.THREADS)
    best_bound_stop = getattr(config, "BEST_BOUND_STOP", None)
    if best_bound_stop is not None:
        model.Params.BestBdStop = float(best_bound_stop)

    P = instance.install_locations
    L = instance.operations
    T = instance.periods
    feasible_pairs = instance.feasible_pairs
    route_arcs = instance.route_arcs
    first_period = T[0]
    period_pairs = list(zip(T[:-1], T[1:]))
    relocation_policy = RelocationPolicy.from_config(config)
    optimize_resource_capacity = bool(getattr(config, "OPTIMIZE_SHARED_RESOURCE_CAPACITY", False))
    resources = (
        sorted(
            set(instance.shared_resource_capacity)
            | {resource for _, resource in instance.resource_requirement}
        )
        if optimize_resource_capacity
        else sorted(instance.shared_resource_capacity)
    )

    w_keys = [(p, j, l, t) for p in P for j, l in feasible_pairs for t in T]
    stay_keys, move_keys = build_transition_keys(instance, relocation_policy)
    z_keys = stay_keys + move_keys
    v_keys = [(p, l, t) for p in P for l in L for t in T]

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

    lp_relaxation = bool(getattr(config, "LP_RELAXATION", False))
    state_vtype = GRB.CONTINUOUS if lp_relaxation else GRB.BINARY
    w = model.addVars(w_keys, lb=0.0, ub=1.0, vtype=state_vtype, name="w")
    # Detailed state-to-state arcs stay continuous. A much smaller binary
    # direction indicator in relocation.py restores exact move counting after
    # coupling rows are added (P(P-1)(T-1), not six-index binaries).
    z = add_transition_variables(model, stay_keys, move_keys)

    # 선택 사항: 논문 Figure 2(a)처럼 초기 구매 배치를 강제로 고정해 비교할 때 사용한다.
    # config.FIXED_PURCHASES = [(p, j, l), ...] 형식으로 전달한다.
    fixed_purchases = getattr(config, "FIXED_PURCHASES", None)
    if fixed_purchases is not None:
        fixed_set = set(fixed_purchases)
        initial_keys = {(p, j, l) for p in P for j, l in feasible_pairs}
        invalid = sorted(fixed_set - initial_keys)
        if invalid:
            raise ValueError(f"Invalid fixed purchase keys: {invalid}")
        for p, j, l in initial_keys:
            model.addConstr(
                w[p, j, l, first_period] == (1 if (p, j, l) in fixed_set else 0),
                name=f"fixed_purchase[{p},{j},{l}]",
            )

    v = model.addVars(v_keys, lb=0.0, name="v")
    f = model.addVars(flow_keys, lb=0.0, name="f")
    resource_capacity = (
        model.addVars(
            resources,
            lb=0,
            ub=len(P),
            vtype=GRB.CONTINUOUS if lp_relaxation else GRB.INTEGER,
            name="resource_capacity",
        )
        if optimize_resource_capacity
        else None
    )

    arcs_from: dict[tuple[int, str, int, int], list[tuple]] = defaultdict(list)
    arcs_to: dict[tuple[int, str, int, int], list[tuple]] = defaultdict(list)
    previous_period = {next_t: prev_t for prev_t, next_t in period_pairs}
    for key in z_keys:
        p_prev, p_next, j_prev, l_prev, j_next, l_next, next_t = key
        prev_t = previous_period[next_t]
        arcs_from[p_prev, j_prev, l_prev, prev_t].append(key)
        arcs_to[p_next, j_next, l_next, next_t].append(key)

    # Layer (i), lifecycle: source occupancy and time-expanded flow balance.
    for p in P:
        model.addConstr(
            gp.quicksum(w[p, j, l, first_period] for j, l in feasible_pairs) <= 1,
            name=f"network_source[{p}]",
        )

    # 각 state node에서 incoming = occupancy = outgoing이 되도록 한다.
    # 이 제약으로 한 위치의 machine lifecycle이 하나의 source-sink path가 된다.
    for p in P:
        for prev_t, next_t in period_pairs:
            for j, l in feasible_pairs:
                model.addConstr(
                    gp.quicksum(z[key] for key in arcs_from[p, j, l, prev_t])
                    == w[p, j, l, prev_t],
                    name=f"network_out[{p},{j},{l},{prev_t}]",
                )
                model.addConstr(
                    gp.quicksum(z[key] for key in arcs_to[p, j, l, next_t])
                    == w[p, j, l, next_t],
                    name=f"network_in[{p},{j},{l},{next_t}]",
                )

    # Layer (ii), coupling: shared resources, capacity, and relocation policy.
    for resource in resources:
        for t in T:
            usage = gp.quicksum(
                instance.resource_requirement[j, resource] * w[p, j, l, t]
                for p in P
                for j, l in feasible_pairs
                if (j, resource) in instance.resource_requirement
            )
            capacity = (
                resource_capacity[resource]
                if resource_capacity is not None
                else instance.shared_resource_capacity[resource]
            )
            model.addConstr(usage <= capacity, name=f"shared_resource[{resource},{t}]")

    for p in P:
        for l in L:
            for t in T:
                model.addConstr(
                    v[p, l, t]
                    <= effective_capacity(
                        instance,
                        w,
                        z,
                        move_keys,
                        p,
                        l,
                        t,
                        relocation_policy.downtime_fraction,
                    ),
                    name=f"capacity[{p},{l},{t}]",
                )

    relocation_cost, congestion_cost, moves_by_period = add_relocation_policy(
        model,
        instance,
        z,
        move_keys,
        relocation_policy,
        lp_relaxation,
    )

    strengthening = add_strengthening_cuts(model, w, instance, config)

    incoming: dict[tuple[int, int, int], list[tuple[int, int, int, int, int]]] = defaultdict(list)
    outgoing: dict[tuple[int, int, int], list[tuple[int, int, int, int, int]]] = defaultdict(list)
    for key in flow_keys:
        p, left, q, right, t = key
        if left != instance.start_operation:
            outgoing[(p, left, t)].append(key)
        if right != instance.end_operation:
            incoming[(q, right, t)].append(key)

    # Layer (iii), material flow: continuous min-cost-flow equations.
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

    purchase_cost = gp.quicksum(
        instance.cost[j] * w[p, j, l, first_period]
        for p in P
        for j, l in feasible_pairs
    )
    reconfiguration_cost = gp.quicksum(
        instance.reconfiguration_cost[j_prev, j_next]
        * z[p_prev, p_next, j_prev, l_prev, j_next, l_next, t]
        for p_prev, p_next, j_prev, l_prev, j_next, l_next, t in z_keys
        if j_prev != j_next
    )
    handling_cost = gp.quicksum(
        instance.parameters["material_handling_cost"] * instance.distance[p, q] * f[p, left, q, right, t]
        for p, left, q, right, t in flow_keys
    )

    total_system_cost = (
        purchase_cost
        + reconfiguration_cost
        + relocation_cost
        + congestion_cost
        + handling_cost
    )
    profile, _ = resolve_profile(config)
    strengthening_metadata = strengthening.to_dict()
    strengthening_metadata["downtime_treatment"] = (
        "nominal_capacity_cuts_remain_valid_but_are_not_relocation_tightened"
        if relocation_policy.downtime_fraction > 0
        else "not_applicable"
    )
    optimization_metadata: dict[str, Any] = {
        "strengthening": strengthening_metadata,
        "strengthening_profile": profile,
        "lp_relaxation": lp_relaxation,
        "relocation_policy": relocation_policy.to_dict(),
    }
    total_move_count = gp.quicksum(moves_by_period.values())
    total_resource_capacity = (
        gp.quicksum(resource_capacity[resource] for resource in resources)
        if resource_capacity is not None
        else None
    )
    hierarchy_metadata, primary_snapshots = _run_objective_hierarchy(
            model=model,
            config=config,
            total_system_cost=total_system_cost,
            total_move_count=total_move_count,
            relocation_secondary=bool(
                relocation_policy.enabled
                and not lp_relaxation
                and getattr(config, "MINIMIZE_RELOCATIONS_SECONDARY", True)
            ),
            total_resource_capacity=total_resource_capacity,
            snapshot_groups={"w": w, "z": z, "v": v, "f": f},
        )
    optimization_metadata.update(hierarchy_metadata)

    return _extract_solution(
        model,
        instance,
        w,
        z,
        v,
        f,
        purchase_cost,
        reconfiguration_cost,
        relocation_cost,
        congestion_cost,
        handling_cost,
        resource_capacity,
        optimization_metadata,
        moves_by_period,
        primary_snapshots,
    )


def _capture_variable_snapshot(
    groups: dict[str, Any],
    *,
    pool_solution: bool = False,
) -> dict[str, dict[Any, float]]:
    """Freeze the stage-1 values before the lexicographic objective changes."""
    return {
        name: {
            key: float(variable.Xn if pool_solution else variable.X)
            for key, variable in variables.items()
        }
        for name, variables in groups.items()
    }


def _run_objective_hierarchy(
    model,
    config,
    total_system_cost,
    total_move_count,
    relocation_secondary: bool,
    total_resource_capacity,
    snapshot_groups: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Solve strict priorities: system cost -> move count -> resource count."""
    total_time_limit = float(config.TIME_LIMIT)
    solve_started = monotonic()
    resource_requested = total_resource_capacity is not None

    relocation_reserve = (
        min(
            float(getattr(config, "RELOCATION_SECONDARY_RESERVED_SECONDS", 0.0)),
            total_time_limit * 0.25,
        )
        if relocation_secondary
        else 0.0
    )
    resource_reserve = (
        min(
            float(getattr(config, "RESOURCE_OPTIMIZATION_RESERVED_SECONDS", 0.0)),
            total_time_limit * 0.2,
        )
        if resource_requested
        else 0.0
    )
    primary_time_limit = max(
        0.001,
        total_time_limit - relocation_reserve - resource_reserve,
    )

    model.Params.TimeLimit = primary_time_limit
    if relocation_secondary:
        model.Params.MIPGap = float(
            getattr(config, "LEXICOGRAPHIC_PRIMARY_MIP_GAP", 0.0)
        )
    model.setObjective(total_system_cost, GRB.MINIMIZE)
    candidate_limit = max(1, int(getattr(config, "STAGE_ONE_CONFIGURATION_LIMIT", 1)))
    if candidate_limit > 1:
        model.Params.PoolSearchMode = 2
        model.Params.PoolSolutions = candidate_limit
        model.Params.PoolGap = 0.0
    _optimize(model, config)
    primary_stage = _solver_metrics(model)
    primary_stage["objective_name"] = "system_cost"
    metadata: dict[str, Any] = {
        "objective_hierarchy": [
            "system_cost",
            *(["relocation_count"] if relocation_secondary else []),
            *(["shared_resource_capacity"] if resource_requested else []),
        ],
        "primary_stage": primary_stage,
        "relocation_secondary_requested": relocation_secondary,
    }
    primary_snapshots: list[dict[str, Any]] = []
    if model.SolCount:
        pool_count = min(candidate_limit, int(model.SolCount))
        for solution_number in range(pool_count):
            model.Params.SolutionNumber = solution_number
            snapshot = _capture_variable_snapshot(
                snapshot_groups,
                pool_solution=candidate_limit > 1,
            )
            move_count = sum(
                value
                for key, value in snapshot["z"].items()
                if key[0] != key[1]
            )
            primary_snapshots.append(
                {
                    "candidate_id": solution_number + 1,
                    "system_cost": _clean_float(
                        model.PoolObjVal if candidate_limit > 1 else model.ObjVal
                    ),
                    "relocation_count": _clean_float(move_count),
                    "snapshot": snapshot,
                }
            )
        model.Params.SolutionNumber = 0
    metadata["stage_one_configuration_count"] = len(primary_snapshots)
    model.Params.PoolSearchMode = 0

    if not model.SolCount:
        metadata["secondary_skip_reason"] = "primary_stage_has_no_incumbent"
        return metadata, primary_snapshots

    primary_value = float(total_system_cost.getValue())
    primary_tolerance = float(
        getattr(config, "RELOCATION_PRIMARY_COST_TOLERANCE", 1e-4)
    )
    metadata["primary_cost_ceiling"] = primary_value + primary_tolerance
    metadata["primary_cost_tolerance"] = primary_tolerance

    if model.Status != GRB.OPTIMAL:
        metadata["secondary_skip_reason"] = (
            "primary_system_cost_not_proven_optimal"
        )
        return metadata, primary_snapshots

    if relocation_secondary or resource_requested:
        model.addConstr(
            total_system_cost <= primary_value + primary_tolerance,
            name="preserve_primary_system_cost",
        )

    relocation_stage_optimal = not relocation_secondary
    if relocation_secondary:
        remaining = max(0.001, total_time_limit - (monotonic() - solve_started))
        reserved_for_resource = min(resource_reserve, remaining * 0.25)
        model.Params.TimeLimit = max(0.001, remaining - reserved_for_resource)
        model.Params.MIPGap = 0.0
        model.setObjective(total_move_count, GRB.MINIMIZE)
        _optimize(model, config)
        relocation_stage = _solver_metrics(model)
        relocation_stage["objective_name"] = "relocation_count"
        metadata["relocation_stage"] = relocation_stage
        relocation_stage_optimal = model.Status == GRB.OPTIMAL
        if model.SolCount:
            minimum_moves = float(total_move_count.getValue())
            metadata["minimum_relocation_count"] = _clean_float(minimum_moves)
            if relocation_stage_optimal and resource_requested:
                model.addConstr(
                    total_move_count <= round(minimum_moves) + 1e-6,
                    name="preserve_minimum_relocation_count",
                )

    if resource_requested and relocation_stage_optimal:
        remaining = max(0.001, total_time_limit - (monotonic() - solve_started))
        model.Params.TimeLimit = remaining
        model.Params.MIPGap = 0.0
        model.setObjective(total_resource_capacity, GRB.MINIMIZE)
        _optimize(model, config)
        resource_stage = _solver_metrics(model)
        resource_stage["objective_name"] = "shared_resource_capacity"
        metadata["resource_stage"] = resource_stage
    elif resource_requested:
        metadata["resource_stage_skip_reason"] = (
            "relocation_stage_not_proven_optimal"
        )

    return metadata, primary_snapshots


def _extract_solution(
    model,
    instance,
    w,
    z,
    v,
    f,
    purchase_cost,
    reconfiguration_cost,
    relocation_cost,
    congestion_cost,
    handling_cost,
    resource_capacity,
    optimization_metadata,
    moves_by_period,
    primary_snapshots,
) -> RMSSolution:
    """Gurobi 변수값을 output.py가 저장하기 쉬운 row list로 변환한다."""
    status_name = {
        GRB.OPTIMAL: "OPTIMAL",
        GRB.TIME_LIMIT: "TIME_LIMIT",
        GRB.INFEASIBLE: "INFEASIBLE",
        GRB.INF_OR_UNBD: "INF_OR_UNBD",
        GRB.USER_OBJ_LIMIT: "USER_OBJ_LIMIT",
    }.get(model.Status, str(model.Status))
    summary: dict[str, Any] = {
        "problem_name": instance.problem_name,
        "formulation": "machine_lifecycle_network",
        "strengthening_profile": optimization_metadata.get("strengthening_profile", "network"),
        "strengthening": optimization_metadata.get("strengthening", {}),
        "lp_relaxation": bool(optimization_metadata.get("lp_relaxation", False)),
        "relocation_policy": optimization_metadata.get("relocation_policy", {}),
        "status": int(model.Status),
        "status_name": status_name,
        "periods": instance.periods,
        "operations": instance.operations,
        "model_size": {
            "variables": int(model.NumVars),
            "binary_variables": int(model.NumBinVars),
            "integer_variables": int(model.NumIntVars),
            "continuous_variables": int(model.NumVars - model.NumIntVars),
            "constraints": int(model.NumConstrs),
        },
    }

    if not model.SolCount:
        summary.update(
            {
                "runtime_seconds": float(model.Runtime),
                "solution_count": 0,
                "node_count": float(model.NodeCount),
            }
        )
        return RMSSolution(summary=summary)

    objective = _clean_float(
        purchase_cost.getValue()
        + reconfiguration_cost.getValue()
        + relocation_cost.getValue()
        + congestion_cost.getValue()
        + handling_cost.getValue()
    )
    cost_breakdown = {
        "purchase_cost": _clean_float(purchase_cost.getValue()),
        "reconfiguration_cost": _clean_float(reconfiguration_cost.getValue()),
        "relocation_cost": _clean_float(relocation_cost.getValue()),
        "relocation_congestion_cost": _clean_float(congestion_cost.getValue()),
        "material_handling_cost": _clean_float(handling_cost.getValue()),
        "total_objective": objective,
    }
    summary.update(
        {
            "objective": objective,
            "runtime_seconds": float(model.Runtime),
            "solution_count": int(model.SolCount),
            "node_count": float(model.NodeCount),
        }
    )
    primary = optimization_metadata.get("primary_stage", {})
    relocation_stage = optimization_metadata.get("relocation_stage")
    resource_stage = optimization_metadata.get("resource_stage")
    relocation_requested = bool(
        optimization_metadata.get("relocation_secondary_requested", False)
    )
    resource_requested = resource_capacity is not None
    required_stages = [primary]
    if relocation_requested:
        required_stages.append(relocation_stage or {})
    if resource_requested:
        required_stages.append(resource_stage or {})
    lexicographic_optimal = all(
        stage.get("status") == GRB.OPTIMAL for stage in required_stages
    )
    completed_stages = [
        stage for stage in (primary, relocation_stage, resource_stage) if stage
    ]
    final_stage = completed_stages[-1] if completed_stages else {}
    overall_status = (
        GRB.OPTIMAL
        if lexicographic_optimal
        else final_stage.get("status", model.Status)
    )
    overall_status_name = {
        GRB.OPTIMAL: "OPTIMAL",
        GRB.TIME_LIMIT: "TIME_LIMIT",
        GRB.INFEASIBLE: "INFEASIBLE",
        GRB.INF_OR_UNBD: "INF_OR_UNBD",
    }.get(overall_status, str(overall_status))
    primary_bound = float(primary.get("best_bound", objective))
    primary_objective = float(primary.get("objective", objective))
    fixed_resource_capacity = bool(instance.shared_resource_capacity)
    posthoc_resource_count = bool(
        instance.resource_requirement and not fixed_resource_capacity
    )
    hierarchy = optimization_metadata.get("objective_hierarchy", ["system_cost"])
    summary.update(
        {
            "status": int(overall_status),
            "status_name": overall_status_name,
            "runtime_seconds": sum(
                float(stage.get("runtime_seconds", 0.0))
                for stage in completed_stages
            ),
            "node_count": sum(
                float(stage.get("node_count", 0.0))
                for stage in completed_stages
            ),
            "optimization_mode": "lexicographic_" + "_then_".join(hierarchy),
            "objective_hierarchy": hierarchy,
            "primary_stage": primary,
            "relocation_stage": relocation_stage,
            "resource_stage": resource_stage,
            "primary_cost_ceiling": _clean_float(
                optimization_metadata.get("primary_cost_ceiling", objective)
            ),
            "primary_cost_tolerance": optimization_metadata.get(
                "primary_cost_tolerance", 0.0
            ),
            "minimum_relocation_count": optimization_metadata.get(
                "minimum_relocation_count"
            ),
            "lexicographic_optimal": lexicographic_optimal,
            "secondary_skip_reason": optimization_metadata.get(
                "secondary_skip_reason"
            ),
            "upper_bound": primary_objective,
            "lower_bound": _clean_float(primary_bound),
            "absolute_gap": _clean_float(primary_objective - primary_bound),
            "mip_gap": float(primary.get("mip_gap", 0.0)),
            "resource_counting_mode": (
                "optimized_decision_variable"
                if resource_requested
                else "fixed_capacity"
                if fixed_resource_capacity
                else "posthoc_peak_usage_from_selected_solution"
                if posthoc_resource_count
                else "disabled"
            ),
            "optimality_note": (
                "Every requested objective priority was proven optimal."
                if lexicographic_optimal
                else "At least one requested objective priority was not proven optimal."
            ),
        }
    )

    purchased = []
    first_period = instance.periods[0]
    for (p, j, l, t), var in sorted(w.items()):
        if t == first_period and var.X > 0.5:
            purchased.append({"location": p, "machine": instance.machine[j], "configuration": j, "initial_operation": l, "purchase_cost": instance.cost[j]})

    flow_by_node = {(p, l, t): var.X for (p, l, t), var in v.items()}
    states = []
    for (p, j, l, t), var in sorted(w.items(), key=lambda item: (item[0][3], item[0][0], item[0][1], item[0][2])):
        if var.X > 0.5:
            states.append({"period": t, "location": p, "machine": instance.machine[j], "configuration": j, "operation": l, "flow": round(flow_by_node.get((p, l, t), 0.0), 6)})

    reconfigs = []
    relocations = []
    for (p_prev, p_next, j_prev, l_prev, j_next, l_next, t), var in sorted(
        z.items(),
        key=lambda item: (item[0][6], item[0][0], item[0][1], item[0][2], item[0][4]),
    ):
        if var.X <= 0.5:
            continue
        if j_prev != j_next:
            reconfigs.append({"period": t, "location": p_next, "from_location": p_prev, "to_location": p_next, "from_machine": instance.machine[j_prev], "from_configuration": j_prev, "to_machine": instance.machine[j_next], "to_configuration": j_next, "operation": l_next, "reconfiguration_cost": instance.reconfiguration_cost[j_prev, j_next]})
        if p_prev != p_next:
            policy = optimization_metadata["relocation_policy"]
            distance = instance.distance[p_prev, p_next]
            relocations.append({"period": t, "from_location": p_prev, "to_location": p_next, "from_machine": instance.machine[j_prev], "from_configuration": j_prev, "to_machine": instance.machine[j_next], "to_configuration": j_next, "operation": l_next, "distance": distance, "direct_relocation_cost": _clean_float(policy["distance_cost"] * distance + policy["fixed_cost"])})

    summary["relocation_count"] = len(relocations)
    summary["relocation_count_by_period"] = {
        str(t): _clean_float(expression.getValue()) for t, expression in moves_by_period.items()
    }

    flows = []
    for (p, left, q, right, t), var in sorted(f.items(), key=lambda item: (item[0][4], item[0][0], item[0][2])):
        if var.X > 1e-6:
            distance = instance.distance[p, q]
            mhc = instance.parameters["material_handling_cost"]
            flows.append({"period": t, "from_location": p, "from_operation": left, "to_location": q, "to_operation": right, "flow": round(var.X, 6), "distance": distance, "mhc": mhc, "flow_cost": round(var.X * distance * mhc, 6)})

    resource_usage = []
    shared_resource_capacities = []
    resources = (
        sorted(
            set(instance.shared_resource_capacity)
            | {resource for _, resource in instance.resource_requirement}
        )
        if resource_capacity is not None or not instance.shared_resource_capacity
        else sorted(instance.shared_resource_capacity)
    )
    usage_by_resource_period: dict[tuple[int, int], float] = {}
    for resource in resources:
        for t in instance.periods:
            usage = sum(
                instance.resource_requirement[j, resource] * var.X
                for (p, j, l, period), var in w.items()
                if period == t and (j, resource) in instance.resource_requirement
            )
            usage_by_resource_period[resource, t] = usage

    for resource in resources:
        peak_usage = max(usage_by_resource_period[resource, t] for t in instance.periods)
        if resource_capacity is not None:
            capacity = float(resource_capacity[resource].X)
            capacity_basis = "optimized_decision_variable"
        elif resource in instance.shared_resource_capacity:
            capacity = float(instance.shared_resource_capacity[resource])
            capacity_basis = "fixed_input_capacity"
        else:
            capacity = float(peak_usage)
            capacity_basis = "posthoc_peak_usage"
        shared_resource_capacities.append(
            {
                "resource": resource,
                "required_capacity": _clean_float(capacity),
                "peak_usage_in_solution": _clean_float(peak_usage),
                "capacity_minus_peak": _clean_float(capacity - peak_usage),
                "capacity_basis": capacity_basis,
                "system_solution_proven_optimal": bool(
                    summary.get("status_name") == "OPTIMAL"
                    if resource_capacity is None
                    else summary.get("lexicographic_optimal", False)
                ),
                "proven_lexicographic_optimal": bool(
                    resource_capacity is not None and summary.get("lexicographic_optimal", False)
                ),
            }
        )
        for t in instance.periods:
            usage = usage_by_resource_period[resource, t]
            resource_usage.append(
                {
                    "period": t,
                    "resource": resource,
                    "usage": round(usage, 6),
                    "capacity": capacity,
                    "slack": round(capacity - usage, 6),
                }
            )

    if resource_capacity is not None:
        summary["optimized_shared_resource_total"] = _clean_float(
            sum(row["required_capacity"] for row in shared_resource_capacities)
        )
        summary["peak_required_resource_total_for_solution"] = _clean_float(
            sum(row["peak_usage_in_solution"] for row in shared_resource_capacities)
        )
    elif instance.resource_requirement and not instance.shared_resource_capacity:
        summary["posthoc_shared_resource_total"] = _clean_float(
            sum(row["required_capacity"] for row in shared_resource_capacities)
        )

    primary_snapshot = primary_snapshots[0]["snapshot"] if primary_snapshots else {}
    stage_one_rows = _extract_snapshot_rows(
        instance,
        primary_snapshot,
        optimization_metadata.get("relocation_policy", {}),
    )

    stage_one_candidates = []
    for candidate in primary_snapshots:
        candidate_rows = _extract_snapshot_rows(
            instance,
            candidate["snapshot"],
            optimization_metadata.get("relocation_policy", {}),
        )
        stage_one_candidates.append(
            {
                "candidate_id": candidate["candidate_id"],
                "system_cost": candidate["system_cost"],
                "relocation_count": candidate["relocation_count"],
                **candidate_rows,
            }
        )

    return RMSSolution(
        summary=summary,
        purchased_machines=purchased,
        machine_states=states,
        reconfigurations=reconfigs,
        relocations=relocations,
        material_flows=flows,
        resource_usage=resource_usage,
        shared_resource_capacities=shared_resource_capacities,
        cost_breakdown=cost_breakdown,
        stage_one_purchased_machines=stage_one_rows["purchased_machines"],
        stage_one_machine_states=stage_one_rows["machine_states"],
        stage_one_reconfigurations=stage_one_rows["reconfigurations"],
        stage_one_relocations=stage_one_rows["relocations"],
        stage_one_material_flows=stage_one_rows["material_flows"],
        stage_one_candidates=stage_one_candidates,
    )


def _extract_snapshot_rows(
    instance,
    snapshot: dict[str, dict[Any, float]],
    relocation_policy: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Convert frozen stage-1 variable values to the stable output row schema."""
    if not snapshot:
        return {
            "purchased_machines": [],
            "machine_states": [],
            "reconfigurations": [],
            "relocations": [],
            "material_flows": [],
        }

    w_values = snapshot["w"]
    z_values = snapshot["z"]
    v_values = snapshot["v"]
    f_values = snapshot["f"]
    first_period = instance.periods[0]
    flow_by_node = dict(v_values)

    purchased = []
    states = []
    for (p, j, l, t), value in sorted(
        w_values.items(), key=lambda item: (item[0][3], item[0][0], item[0][1], item[0][2])
    ):
        if value <= 0.5:
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

    reconfigs = []
    relocations = []
    for key, value in sorted(
        z_values.items(),
        key=lambda item: (item[0][6], item[0][0], item[0][1], item[0][2], item[0][4]),
    ):
        if value <= 0.5:
            continue
        p_prev, p_next, j_prev, _l_prev, j_next, l_next, t = key
        if j_prev != j_next:
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
                    "reconfiguration_cost": instance.reconfiguration_cost[j_prev, j_next],
                }
            )
        if p_prev != p_next:
            distance = instance.distance[p_prev, p_next]
            relocations.append(
                {
                    "period": t,
                    "from_location": p_prev,
                    "to_location": p_next,
                    "from_machine": instance.machine[j_prev],
                    "from_configuration": j_prev,
                    "to_machine": instance.machine[j_next],
                    "to_configuration": j_next,
                    "operation": l_next,
                    "distance": distance,
                    "direct_relocation_cost": _clean_float(
                        relocation_policy.get("distance_cost", 0.0) * distance
                        + relocation_policy.get("fixed_cost", 0.0)
                    ),
                }
            )

    flows = []
    for (p, left, q, right, t), value in sorted(
        f_values.items(), key=lambda item: (item[0][4], item[0][0], item[0][2])
    ):
        if value <= 1e-6:
            continue
        distance = instance.distance[p, q]
        mhc = instance.parameters["material_handling_cost"]
        flows.append(
            {
                "period": t,
                "from_location": p,
                "from_operation": left,
                "to_location": q,
                "to_operation": right,
                "flow": round(value, 6),
                "distance": distance,
                "mhc": mhc,
                "flow_cost": round(value * distance * mhc, 6),
            }
        )

    return {
        "purchased_machines": purchased,
        "machine_states": states,
        "reconfigurations": reconfigs,
        "relocations": relocations,
        "material_flows": flows,
    }


def _clean_float(value: float, integer_tolerance: float = 1e-3) -> float:
    """Gurobi numerical noise를 사람이 읽기 좋은 값으로 정리한다."""
    value = float(value)
    nearest_integer = round(value)
    if abs(value - nearest_integer) <= integer_tolerance:
        return float(nearest_integer)
    return round(value, 6)


def _solver_metrics(model) -> dict[str, Any]:
    """각 최적화 단계의 상태와 bound를 다음 단계 전에 보존한다."""
    status_name = {
        GRB.OPTIMAL: "OPTIMAL",
        GRB.TIME_LIMIT: "TIME_LIMIT",
        GRB.INFEASIBLE: "INFEASIBLE",
        GRB.INF_OR_UNBD: "INF_OR_UNBD",
        GRB.USER_OBJ_LIMIT: "USER_OBJ_LIMIT",
    }.get(model.Status, str(model.Status))
    metrics: dict[str, Any] = {
        "status": int(model.Status),
        "status_name": status_name,
        "runtime_seconds": float(model.Runtime),
        "solution_count": int(model.SolCount),
        "node_count": float(model.NodeCount),
    }
    if model.SolCount:
        metrics.update(
            {
                "objective": _clean_float(model.ObjVal),
                "best_bound": _clean_float(model.ObjBound),
                "mip_gap": float(model.MIPGap) if model.IsMIP else 0.0,
            }
        )
    return metrics


def _optimize(model, config) -> None:
    """Run Gurobi with an optional read-only progress callback."""
    recorder = getattr(config, "PROGRESS_RECORDER", None)
    if recorder is None:
        model.optimize()
        return
    model.optimize(recorder)
    recorder.finish(model)
