from __future__ import annotations

"""Adaptive layout + shared-resource MILP for the RMS layout project.

이 파일은 기존 `Src/milp.py`를 직접 수정하지 않고, 논문 개선 아이디어를
실험하기 위한 별도 모델입니다. 기존 모델의 좋은 점은 유지하되, 아래 한계를
보완하는 방향으로 작성했습니다.

기존 재현 코드에서 논문 개선 포인트로 볼 수 있는 부분:
1. layout이 정적입니다. 한 번 구매된 RMT는 특정 location에 묶여 있고,
   period별 수요 변화에 따라 설비를 옮기는 adaptive layout이 없습니다.
2. multi-part flow가 operation arc demand로 집계되어 part identity가 사라집니다.
   이 파일도 기본 호환성을 위해 집계 flow를 쓰지만, 논문 개선 방향으로는
   part-specific multi-commodity flow를 추가하는 것이 좋습니다.
3. reconfiguration, 이동, 생산, material handling에 필요한 공유 자원
   예: 작업자, setup team, AGV, controller, module inventory가 무한하다고 봅니다.
4. 같은 period에 여러 RMT가 동시에 재구성되어도 crew/bay capacity 제한이 없습니다.
5. 문서와 주석의 한글 인코딩이 깨져 있어 연구 재현성 관점에서 정리가 필요합니다.

새로 추가한 모델링 아이디어:
- RMT를 asset index k로 추적합니다. 따라서 같은 RMT가 period마다 다른 location에
  배치될 수 있고, 이동 비용 및 이동 자원 제약을 걸 수 있습니다.
- configuration change와 location move를 분리합니다.
- shared resource capacity를 config 속성으로 선택적으로 추가할 수 있습니다.
- module inventory 제약을 통해 auxiliary/basic module의 공유 재고 한계를 표현합니다.

config.py에 선택적으로 넣을 수 있는 예시는 아래와 같습니다.

    MAX_RMT_ASSETS = 16
    MOVE_COST_PER_DISTANCE = 30.0
    MAX_RECONFIGURATIONS_PER_PERIOD = {2: 4, 3: 4, 4: 4}
    MAX_MOVES_PER_PERIOD = {2: 3, 3: 3, 4: 3}

    SHARED_RESOURCE_CAPACITY = {
        "operator_hours": {1: 120, 2: 120, 3: 120, 4: 120},
        "agv_distance": {1: 900, 2: 900, 3: 900, 4: 900},
        "setup_team_hours": {1: 0, 2: 16, 3: 16, 4: 16},
    }
    PROCESS_RESOURCE_USE = {
        (5, "operator_hours"): 0.08,      # operation 5 flow 1단위당 작업자 시간
        (1, "operator_hours"): 0.06,
        (17, "operator_hours"): 0.05,
    }
    HANDLING_RESOURCE_DISTANCE_USE = {
        "agv_distance": 1.0,              # flow * distance가 AGV distance를 소비
    }
    RECONFIG_RESOURCE_USE = {
        ("*", "*", "setup_team_hours"): 1.0,
    }
    SHARED_MODULE_STOCK = {
        20: {1: 6, 2: 6, 3: 6, 4: 6},     # module 20은 동시에 6개까지만 사용
        22: 5,                            # 모든 period에 5개
    }

사용 방법:
    from Src.data import load_instance
    from RMS_chatgpt_like_loader import solve_adaptive_shared_resource_milp

`RMS-chatgpt` 폴더명에는 하이픈이 있어 일반 import package로 쓰기는 어렵습니다.
실제 프로젝트에 붙일 때는 이 파일을 `Src/milp_adaptive_shared_resource.py`로
복사하거나, importlib로 파일 경로를 로드하면 됩니다.
"""

from collections import defaultdict
from typing import Any

import gurobipy as gp
from gurobipy import GRB

from Src.milp import RMSSolution


def solve_adaptive_shared_resource_milp(instance, config) -> RMSSolution:
    """Adaptive layout과 shared resource 제약을 포함한 RMS layout MILP를 푼다.

    기존 `solve_milp(instance, config)`와 같은 `RMSSolution`을 반환하므로,
    `Src/output.py`와 `Src/visualize.py`를 비교적 쉽게 재사용할 수 있다.
    """
    model = gp.Model(f"rms_adaptive_shared_{instance.problem_name}")
    model.Params.TimeLimit = config.TIME_LIMIT
    model.Params.MIPGap = config.MIP_GAP

    P = list(instance.install_locations)
    J = list(instance.configurations)
    L = list(instance.operations)
    T = sorted(instance.periods)
    first_period = T[0]
    previous_period = {current: prev for prev, current in zip(T[:-1], T[1:])}
    feasible_pairs = list(instance.feasible_pairs)
    route_arcs = list(instance.route_arcs)

    # Asset index k는 실제 RMT 한 대를 의미한다. 최대 asset 수는 location 수가 자연스러운 상한이다.
    max_assets = int(getattr(config, "MAX_RMT_ASSETS", len(P)))
    if max_assets < 1:
        raise ValueError("MAX_RMT_ASSETS must be positive.")
    K = list(range(1, max_assets + 1))

    feasible_by_op: dict[int, list[str]] = defaultdict(list)
    feasible_by_config: dict[str, list[int]] = defaultdict(list)
    for j, l in feasible_pairs:
        feasible_by_op[l].append(j)
        feasible_by_config[j].append(l)

    # -----------------------------
    # Variables
    # -----------------------------
    buy = model.addVars(K, vtype=GRB.BINARY, name="buy")

    state_keys = [
        (k, p, j, l, t)
        for k in K
        for p in P
        for (j, l) in feasible_pairs
        for t in T
    ]
    s = model.addVars(state_keys, vtype=GRB.BINARY, name="s")

    location_keys = [(k, p, t) for k in K for p in P for t in T]
    z = model.addVars(location_keys, vtype=GRB.BINARY, name="z")

    config_keys = [(k, j, t) for k in K for j in J for t in T]
    g = model.addVars(config_keys, vtype=GRB.BINARY, name="g")

    reconfig_keys = [
        (k, j_prev, j_next, t)
        for k in K
        for j_prev in J
        for j_next in J
        for t in T
        if t != first_period
        and j_prev != j_next
        and (j_prev, j_next) in instance.reconfiguration_cost
    ]
    y = model.addVars(reconfig_keys, vtype=GRB.BINARY, name="y")

    move_keys = [
        (k, p_prev, p_next, t)
        for k in K
        for p_prev in P
        for p_next in P
        for t in T
        if t != first_period and p_prev != p_next
    ]
    move = model.addVars(move_keys, vtype=GRB.BINARY, name="move")

    v_keys = [(p, l, t) for p in P for l in L for t in T]
    v = model.addVars(v_keys, lb=0.0, name="v")

    flow_keys = _build_flow_keys(instance, P, route_arcs, T)
    f = model.addVars(flow_keys, lb=0.0, name="f")

    # -----------------------------
    # Core adaptive-layout constraints
    # -----------------------------
    # 구매된 asset은 매 period 정확히 하나의 위치/configuration/operation 상태를 갖는다.
    # 구매되지 않은 asset은 모든 상태가 0이다.
    for k in K:
        for t in T:
            model.addConstr(
                gp.quicksum(s[k, p, j, l, t] for p in P for (j, l) in feasible_pairs) == buy[k],
                name=f"one_state_if_bought[{k},{t}]",
            )

    # 같은 location에는 한 period에 최대 한 대의 RMT만 배치된다.
    for p in P:
        for t in T:
            model.addConstr(
                gp.quicksum(z[k, p, t] for k in K) <= 1,
                name=f"one_asset_per_location[{p},{t}]",
            )

    # z[k,p,t]는 asset k가 period t에 location p에 있음을 나타낸다.
    for k in K:
        for p in P:
            for t in T:
                model.addConstr(
                    z[k, p, t]
                    == gp.quicksum(s[k, p, j, l, t] for (j, l) in feasible_pairs),
                    name=f"link_location[{k},{p},{t}]",
                )

    # g[k,j,t]는 asset k가 period t에 configuration j임을 나타낸다.
    for k in K:
        for j in J:
            for t in T:
                model.addConstr(
                    g[k, j, t]
                    == gp.quicksum(
                        s[k, p, j, l, t]
                        for p in P
                        for l in feasible_by_config[j]
                        if (k, p, j, l, t) in s
                    ),
                    name=f"link_configuration[{k},{j},{t}]",
                )

    # 동일한 asset index 간 대칭성을 조금 줄인다. 해는 바뀌지 않고 탐색만 줄이는 목적이다.
    if bool(getattr(config, "BREAK_ASSET_SYMMETRY", True)):
        for k in K[:-1]:
            model.addConstr(buy[k] >= buy[k + 1], name=f"symmetry_buy_order[{k}]")

    _apply_fixed_initial_layout_if_requested(model, s, K, P, feasible_pairs, first_period, config)

    # Configuration 변화가 있으면 y가 1이 된다. 같은 configuration에서 operation만 바뀌는 것은
    # module reconfiguration 없이 가능한 것으로 둔다. setup cost가 필요하면 shared resource나
    # 별도 operation-change 변수를 추가하면 된다.
    for k, j_prev, j_next, t in reconfig_keys:
        prev_t = previous_period[t]
        model.addConstr(y[k, j_prev, j_next, t] >= g[k, j_prev, prev_t] + g[k, j_next, t] - 1)
        model.addConstr(y[k, j_prev, j_next, t] <= g[k, j_prev, prev_t])
        model.addConstr(y[k, j_prev, j_next, t] <= g[k, j_next, t])

    # 현재 configuration은 직전 period에 같은 configuration이었거나,
    # 허용된 reconfiguration arc를 통해 들어온 경우에만 선택될 수 있다.
    # 이 제약이 없으면 same-machine-only 같은 전환 금지가 우회될 수 있다.
    for k in K:
        for t in T:
            if t == first_period:
                continue
            prev_t = previous_period[t]
            for j_next in J:
                model.addConstr(
                    g[k, j_next, t]
                    <= g[k, j_next, prev_t]
                    + gp.quicksum(
                        y[k, j_prev, j_next, t]
                        for j_prev in J
                        if (k, j_prev, j_next, t) in y
                    ),
                    name=f"config_transition[{k},{j_next},{t}]",
                )

    # Location이 바뀌면 move가 1이 된다. 이동 비용과 이동 crew 자원 제약의 기반 변수다.
    for k, p_prev, p_next, t in move_keys:
        prev_t = previous_period[t]
        model.addConstr(move[k, p_prev, p_next, t] >= z[k, p_prev, prev_t] + z[k, p_next, t] - 1)
        model.addConstr(move[k, p_prev, p_next, t] <= z[k, p_prev, prev_t])
        model.addConstr(move[k, p_prev, p_next, t] <= z[k, p_next, t])

    # -----------------------------
    # Capacity and material-flow constraints
    # -----------------------------
    for p in P:
        for l in L:
            for t in T:
                model.addConstr(
                    v[p, l, t]
                    <= gp.quicksum(
                        instance.production_rate[j, l] * s[k, p, j, l, t]
                        for k in K
                        for j in feasible_by_op[l]
                        if (k, p, j, l, t) in s
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

    # 각 operation node에서 들어온 flow = 처리 flow = 나간 flow.
    for p in P:
        for l in L:
            for t in T:
                model.addConstr(gp.quicksum(f[key] for key in incoming[p, l, t]) == v[p, l, t])
                model.addConstr(gp.quicksum(f[key] for key in outgoing[p, l, t]) == v[p, l, t])

    # Route arc별 총 flow는 해당 period의 demand와 같아야 한다.
    for t in T:
        for left, right in route_arcs:
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

    # -----------------------------
    # Shared-resource constraints
    # -----------------------------
    resource_constraint_count = _add_shared_resource_constraints(
        model=model,
        instance=instance,
        config=config,
        K=K,
        P=P,
        T=T,
        feasible_pairs=feasible_pairs,
        s=s,
        y=y,
        move=move,
        v=v,
        f=f,
        flow_keys=flow_keys,
    )
    module_constraint_count = _add_shared_module_stock_constraints(
        model=model,
        instance=instance,
        config=config,
        K=K,
        P=P,
        T=T,
        feasible_pairs=feasible_pairs,
        s=s,
    )
    schedule_constraint_count = _add_period_schedule_limits(
        model=model,
        config=config,
        T=T,
        y=y,
        move=move,
    )

    # -----------------------------
    # Objective
    # -----------------------------
    purchase_cost = gp.quicksum(
        instance.cost[j] * s[k, p, j, l, first_period]
        for k in K
        for p in P
        for (j, l) in feasible_pairs
    )
    reconfiguration_cost = gp.quicksum(
        instance.reconfiguration_cost[j_prev, j_next] * y[k, j_prev, j_next, t]
        for k, j_prev, j_next, t in reconfig_keys
    )
    handling_cost = gp.quicksum(
        instance.parameters["material_handling_cost"]
        * instance.distance[p, q]
        * f[p, left, q, right, t]
        for p, left, q, right, t in flow_keys
    )
    move_cost_per_distance = float(getattr(config, "MOVE_COST_PER_DISTANCE", 0.0))
    adaptive_move_cost = gp.quicksum(
        move_cost_per_distance * instance.distance[p_prev, p_next] * move[k, p_prev, p_next, t]
        for k, p_prev, p_next, t in move_keys
    )

    model.setObjective(
        purchase_cost + reconfiguration_cost + handling_cost + adaptive_move_cost,
        GRB.MINIMIZE,
    )
    model.optimize()

    return _extract_adaptive_solution(
        model=model,
        instance=instance,
        K=K,
        T=T,
        s=s,
        y=y,
        move=move,
        v=v,
        f=f,
        purchase_cost=purchase_cost,
        reconfiguration_cost=reconfiguration_cost,
        handling_cost=handling_cost,
        adaptive_move_cost=adaptive_move_cost,
        resource_constraint_count=resource_constraint_count,
        module_constraint_count=module_constraint_count,
        schedule_constraint_count=schedule_constraint_count,
        move_cost_per_distance=move_cost_per_distance,
    )


def _build_flow_keys(instance, install_locations, route_arcs, periods):
    """기존 모델과 호환되는 aggregate material-flow 변수 index를 만든다."""
    flow_keys = []
    for t in periods:
        for left, right in route_arcs:
            if instance.arc_demand.get((t, left, right), 0.0) <= 0:
                continue
            from_locations = [instance.start_location] if left == instance.start_operation else install_locations
            to_locations = [instance.end_location] if right == instance.end_operation else install_locations
            for p in from_locations:
                for q in to_locations:
                    # 한 location에는 한 대만 둘 수 있으므로 같은 period의 연속 operation을 같은
                    # location에서 처리하는 routing은 여기서 제외한다.
                    if p != q:
                        flow_keys.append((p, left, q, right, t))
    return flow_keys


def _apply_fixed_initial_layout_if_requested(model, s, K, P, feasible_pairs, first_period, config) -> None:
    """기존 check script의 FIXED_PURCHASES를 adaptive 모델에서도 사용할 수 있게 한다."""
    fixed_purchases = getattr(config, "FIXED_PURCHASES", None)
    if fixed_purchases is None:
        return

    feasible_set = set(feasible_pairs)
    fixed_counts: dict[tuple[int, str, int], int] = defaultdict(int)
    for p, j, l in fixed_purchases:
        if p not in P:
            raise ValueError(f"Invalid fixed initial location: {p}")
        if (j, l) not in feasible_set:
            raise ValueError(f"Invalid fixed initial configuration-operation pair: {(j, l)}")
        fixed_counts[(p, j, l)] += 1

    if sum(fixed_counts.values()) > len(K):
        raise ValueError("FIXED_PURCHASES has more machines than MAX_RMT_ASSETS.")

    exact = bool(getattr(config, "ADAPTIVE_FIXED_INITIAL_EXACT", True))
    for p in P:
        for j, l in feasible_pairs:
            required_count = fixed_counts.get((p, j, l), 0)
            if required_count or exact:
                model.addConstr(
                    gp.quicksum(s[k, p, j, l, first_period] for k in K) == required_count,
                    name=f"fixed_initial[{p},{j},{l}]",
                )


def _add_shared_resource_constraints(
    model,
    instance,
    config,
    K,
    P,
    T,
    feasible_pairs,
    s,
    y,
    move,
    v,
    f,
    flow_keys,
) -> int:
    """생산, 재구성, 이동, material handling이 공유 자원을 소비하도록 제한한다."""
    capacities = getattr(config, "SHARED_RESOURCE_CAPACITY", {})
    if not capacities:
        return 0

    count = 0
    for resource in sorted(capacities):
        for t in T:
            capacity = _period_value(capacities[resource], t)
            if capacity is None:
                continue

            terms: list[Any] = []

            # Flow 1단위 처리 시 소비되는 자원: operator hour, energy 등.
            for p in P:
                for l in instance.operations:
                    amount = _process_resource_use(config, l, resource)
                    if amount:
                        terms.append(amount * v[p, l, t])

            # 어떤 machine/configuration이 active이면 소비되는 고정 자원: controller slot 등.
            for k in K:
                for p in P:
                    for j, l in feasible_pairs:
                        amount = _active_resource_use(config, j, l, resource)
                        if amount:
                            terms.append(amount * s[k, p, j, l, t])

            # Reconfiguration 1회당 소비되는 자원: setup team hour, reconfiguration bay 등.
            for key, var in y.items():
                k, j_prev, j_next, current_t = key
                if current_t != t:
                    continue
                amount = _reconfig_resource_use(config, j_prev, j_next, resource)
                if amount:
                    terms.append(amount * var)

            # Layout move 1회 또는 이동 거리당 소비되는 자원: mover, forklift, downtime 등.
            for key, var in move.items():
                k, p_prev, p_next, current_t = key
                if current_t != t:
                    continue
                amount = _move_resource_use(config, instance, p_prev, p_next, resource)
                if amount:
                    terms.append(amount * var)

            # Material handling flow가 소비하는 자원: AGV distance/time 등.
            for key in flow_keys:
                p, left, q, right, current_t = key
                if current_t != t:
                    continue
                amount = _handling_resource_use(config, instance, p, q, resource)
                if amount:
                    terms.append(amount * f[key])

            if terms:
                model.addConstr(
                    gp.quicksum(terms) <= capacity,
                    name=f"shared_resource[{resource},{t}]",
                )
                count += 1

    return count


def _add_shared_module_stock_constraints(model, instance, config, K, P, T, feasible_pairs, s) -> int:
    """Configuration이 요구하는 module을 공유 재고로 제한한다."""
    stock = getattr(config, "SHARED_MODULE_STOCK", getattr(config, "MODULE_STOCK", None))
    if not stock:
        return 0

    module_ids = sorted({module for modules in instance.modules.values() for module in modules})
    count = 0
    for module_id in module_ids:
        for t in T:
            capacity = _module_stock_value(stock, module_id, t)
            if capacity is None:
                continue
            model.addConstr(
                gp.quicksum(
                    s[k, p, j, l, t]
                    for k in K
                    for p in P
                    for (j, l) in feasible_pairs
                    if module_id in instance.modules[j]
                )
                <= capacity,
                name=f"shared_module_stock[{module_id},{t}]",
            )
            count += 1
    return count


def _add_period_schedule_limits(model, config, T, y, move) -> int:
    """Period별 전체 reconfiguration/move 횟수 상한을 선택적으로 건다."""
    count = 0
    max_reconfigs = getattr(config, "MAX_RECONFIGURATIONS_PER_PERIOD", None)
    if max_reconfigs is not None:
        for t in T:
            cap = _period_value(max_reconfigs, t)
            if cap is None:
                continue
            model.addConstr(
                gp.quicksum(var for key, var in y.items() if key[3] == t) <= cap,
                name=f"max_reconfigurations[{t}]",
            )
            count += 1

    max_moves = getattr(config, "MAX_MOVES_PER_PERIOD", None)
    if max_moves is not None:
        for t in T:
            cap = _period_value(max_moves, t)
            if cap is None:
                continue
            model.addConstr(
                gp.quicksum(var for key, var in move.items() if key[3] == t) <= cap,
                name=f"max_moves[{t}]",
            )
            count += 1

    return count


def _extract_adaptive_solution(
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
    handling_cost,
    adaptive_move_cost,
    resource_constraint_count,
    module_constraint_count,
    schedule_constraint_count,
    move_cost_per_distance,
) -> RMSSolution:
    """Gurobi 결과를 기존 output.py가 저장할 수 있는 row list로 변환한다."""
    status_name = _status_name(model.Status)
    summary: dict[str, Any] = {
        "problem_name": instance.problem_name,
        "model_variant": "adaptive_layout_shared_resource",
        "status": int(model.Status),
        "status_name": status_name,
        "periods": instance.periods,
        "operations": instance.operations,
        "resource_constraints": resource_constraint_count,
        "module_stock_constraints": module_constraint_count,
        "schedule_limit_constraints": schedule_constraint_count,
    }

    if not model.SolCount:
        return RMSSolution(summary=summary)

    cost_breakdown = {
        "purchase_cost": float(purchase_cost.getValue()),
        "reconfiguration_cost": float(reconfiguration_cost.getValue()),
        "material_handling_cost": float(handling_cost.getValue()),
        "adaptive_layout_move_cost": float(adaptive_move_cost.getValue()),
        "total_objective": float(model.ObjVal),
    }
    summary.update(
        {
            "objective": float(model.ObjVal),
            "runtime_seconds": float(model.Runtime),
            "mip_gap": float(model.MIPGap) if model.IsMIP else 0.0,
        }
    )

    selected_states: dict[tuple[int, int], dict[str, Any]] = {}
    flow_by_node = {(p, l, t): var.X for (p, l, t), var in v.items()}

    machine_states: list[dict[str, Any]] = []
    for (k, p, j, l, t), var in sorted(s.items(), key=lambda item: (item[0][4], item[0][0], item[0][1])):
        if var.X <= 0.5:
            continue
        row = {
            "period": t,
            "asset": k,
            "location": p,
            "machine": instance.machine[j],
            "configuration": j,
            "operation": l,
            "flow": round(flow_by_node.get((p, l, t), 0.0), 6),
        }
        selected_states[(k, t)] = row
        machine_states.append(row)

    first_period = T[0]
    purchased_machines = []
    for (k, t), row in sorted(selected_states.items()):
        if t != first_period:
            continue
        purchased_machines.append(
            {
                "asset": k,
                "location": row["location"],
                "machine": row["machine"],
                "configuration": row["configuration"],
                "initial_operation": row["operation"],
                "purchase_cost": instance.cost[row["configuration"]],
            }
        )

    layout_changes = []
    for k in K:
        for prev_t, t in zip(T[:-1], T[1:]):
            previous = selected_states.get((k, prev_t))
            current = selected_states.get((k, t))
            if previous is None or current is None:
                continue

            moved = previous["location"] != current["location"]
            reconfigured = previous["configuration"] != current["configuration"]
            if not moved and not reconfigured:
                continue

            move_distance = (
                instance.distance[previous["location"], current["location"]]
                if moved
                else 0.0
            )
            config_cost = (
                instance.reconfiguration_cost.get(
                    (previous["configuration"], current["configuration"]),
                    0.0,
                )
                if reconfigured
                else 0.0
            )
            if moved and reconfigured:
                change_type = "move+reconfigure"
            elif moved:
                change_type = "move"
            else:
                change_type = "reconfigure"

            layout_changes.append(
                {
                    "period": t,
                    "asset": k,
                    "change_type": change_type,
                    "from_location": previous["location"],
                    "to_location": current["location"],
                    "from_machine": previous["machine"],
                    "from_configuration": previous["configuration"],
                    "to_machine": current["machine"],
                    "to_configuration": current["configuration"],
                    "operation": current["operation"],
                    "move_distance": move_distance,
                    "move_cost": round(move_cost_per_distance * move_distance, 6),
                    "reconfiguration_cost": config_cost,
                }
            )

    material_flows = []
    for (p, left, q, right, t), var in sorted(f.items(), key=lambda item: (item[0][4], item[0][0], item[0][2])):
        if var.X <= 1e-6:
            continue
        distance = instance.distance[p, q]
        mhc = instance.parameters["material_handling_cost"]
        material_flows.append(
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

    return RMSSolution(
        summary=summary,
        purchased_machines=purchased_machines,
        machine_states=machine_states,
        reconfigurations=layout_changes,
        material_flows=material_flows,
        cost_breakdown=cost_breakdown,
    )


def _status_name(status: int) -> str:
    return {
        GRB.OPTIMAL: "OPTIMAL",
        GRB.TIME_LIMIT: "TIME_LIMIT",
        GRB.INFEASIBLE: "INFEASIBLE",
        GRB.INF_OR_UNBD: "INF_OR_UNBD",
        GRB.UNBOUNDED: "UNBOUNDED",
    }.get(status, str(status))


def _period_value(value, period: int) -> float | None:
    """scalar 또는 {period: value} 형식을 모두 받는다."""
    if value is None:
        return None
    if isinstance(value, dict):
        for key in (period, str(period), "*", "default"):
            if key in value:
                raw = value[key]
                return None if raw is None else float(raw)
        return None
    return float(value)


def _module_stock_value(stock, module_id: int, period: int) -> float | None:
    """module 재고 입력을 scalar/dict/period-dict로 유연하게 읽는다."""
    if (module_id, period) in stock:
        return None if stock[module_id, period] is None else float(stock[module_id, period])
    if (str(module_id), period) in stock:
        return None if stock[str(module_id), period] is None else float(stock[str(module_id), period])

    raw = None
    if module_id in stock:
        raw = stock[module_id]
    elif str(module_id) in stock:
        raw = stock[str(module_id)]

    return _period_value(raw, period)


def _lookup(mapping, candidates, default: float = 0.0) -> float:
    """wildcard 후보를 순서대로 찾아 resource-use 계수를 반환한다."""
    if not mapping:
        return default
    for key in candidates:
        if key in mapping:
            return float(mapping[key])
    return default


def _process_resource_use(config, operation: int, resource: str) -> float:
    mapping = getattr(config, "PROCESS_RESOURCE_USE", {})
    return _lookup(
        mapping,
        [
            (operation, resource),
            (str(operation), resource),
            ("*", resource),
            resource,
        ],
    )


def _active_resource_use(config, configuration: str, operation: int, resource: str) -> float:
    mapping = getattr(config, "ACTIVE_RESOURCE_USE", {})
    return _lookup(
        mapping,
        [
            (configuration, operation, resource),
            (configuration, str(operation), resource),
            (configuration, "*", resource),
            ("*", operation, resource),
            ("*", str(operation), resource),
            ("*", "*", resource),
            resource,
        ],
    )


def _reconfig_resource_use(config, previous_configuration: str, next_configuration: str, resource: str) -> float:
    mapping = getattr(config, "RECONFIG_RESOURCE_USE", {})
    return _lookup(
        mapping,
        [
            (previous_configuration, next_configuration, resource),
            (previous_configuration, "*", resource),
            ("*", next_configuration, resource),
            ("*", "*", resource),
            resource,
        ],
    )


def _move_resource_use(config, instance, previous_location: int, next_location: int, resource: str) -> float:
    fixed_mapping = getattr(config, "MOVE_RESOURCE_USE", {})
    distance_mapping = getattr(config, "MOVE_RESOURCE_DISTANCE_USE", {})
    fixed_amount = _lookup(
        fixed_mapping,
        [
            (previous_location, next_location, resource),
            (str(previous_location), str(next_location), resource),
            (previous_location, "*", resource),
            ("*", next_location, resource),
            ("*", "*", resource),
            resource,
        ],
    )
    distance_amount = _lookup(
        distance_mapping,
        [
            (previous_location, next_location, resource),
            (str(previous_location), str(next_location), resource),
            (previous_location, "*", resource),
            ("*", next_location, resource),
            ("*", "*", resource),
            resource,
        ],
    )
    return fixed_amount + distance_amount * instance.distance[previous_location, next_location]


def _handling_resource_use(config, instance, from_location: int, to_location: int, resource: str) -> float:
    fixed_mapping = getattr(config, "HANDLING_RESOURCE_USE", {})
    distance_mapping = getattr(config, "HANDLING_RESOURCE_DISTANCE_USE", {})
    fixed_amount = _lookup(
        fixed_mapping,
        [
            (from_location, to_location, resource),
            (str(from_location), str(to_location), resource),
            (from_location, "*", resource),
            ("*", to_location, resource),
            ("*", "*", resource),
            resource,
        ],
    )
    distance_amount = _lookup(
        distance_mapping,
        [
            (from_location, to_location, resource),
            (str(from_location), str(to_location), resource),
            (from_location, "*", resource),
            ("*", to_location, resource),
            ("*", "*", resource),
            resource,
        ],
    )
    return fixed_amount + distance_amount * instance.distance[from_location, to_location]
