# -*- coding: utf-8 -*-
"""Saffar식 adaptive layout — 논문 정식화(Src/milp.py)에 이동 이진변수 w만 추가한 모델.

network 모델(Src/milp_network.py)도, z 통합전이 인코딩(Src/milp_adaptive.py)도 쓰지 않는다.
논문 식 (1)~(16)의 x, s, y를 전부 유지하고 w_kpjt 하나만 더한다.

논문 대비 변경 (아티팩트 956JknKPwDFV1RTXsXaZiG 3절):
  삭제 (2)  : 상태의 구매위치 영구귀속  -> (19)가 대체
  신규 (18a): 도착 등록   Win_pjt <= sigma_pjt            (joint: + Yout)
  신규 (18b): 출발 조건   Wout_kjt <= sigma_kj(t-1)       (도착지 합산형)
  신규 (19) : 기계 보존   점유변화 = 이동유입 - 이동유출   (등식 = 폐기 불가)
  수정 (1)  : 이동비 항 + C_j(alpha + beta*D_kp) * w
  수정 (4') : s_pjl1 = x_pjl (등식)
  수정 (5)->(20): 이동 유입항 Win 추가
  수정 (7)->(7') : joint에서만 Win 추가
  유지 (3) (6) (8)~(15)
선택 (S): config 단위 보존 등식 — 새 변수 없이 LP를 z 수준으로 강화.

플래그: ADAPTIVE_MODE(off/separate/joint), ALPHA, BETA,
       SAFFAR_BALANCE_EQ((S) on/off), SAFFAR_W_BINARY(w,y 이진/연속)
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import gurobipy as gp
from gurobipy import GRB

from Src.milp import (
    RMSSolution,
    _clean_float,
    _solver_metrics,
    _compute_lp_relaxation_bound,
    _apply_gurobi_params,
)
from Src.route_alternatives import add_route_demand_constraints, route_shares
from Src.warm_start import apply_warm_start


def solve_milp(instance, config) -> RMSSolution:
    mode = str(getattr(config, "ADAPTIVE_MODE", "off")).lower()
    if mode not in {"off", "separate", "joint"}:
        raise ValueError(f"ADAPTIVE_MODE must be off/separate/joint, got {mode!r}")
    alpha = float(getattr(config, "ALPHA", 0.0))
    beta = float(getattr(config, "BETA", 0.0))
    use_S = bool(getattr(config, "SAFFAR_BALANCE_EQ", False))
    w_binary = bool(getattr(config, "SAFFAR_W_BINARY", True))

    model = gp.Model("saffar_w_" + str(instance.problem_name) + "_" + mode)
    model.Params.TimeLimit = config.TIME_LIMIT
    model.Params.MIPGap = config.MIP_GAP
    if hasattr(config, "OUTPUT_FLAG"):
        model.Params.OutputFlag = int(config.OUTPUT_FLAG)
    mip_focus = getattr(config, "MIP_FOCUS", None)
    if mip_focus is not None:
        model.Params.MIPFocus = int(mip_focus)
    _apply_gurobi_params(model, config)

    P = instance.install_locations
    J = instance.configurations
    L = instance.operations
    T = instance.periods
    F = instance.feasible_pairs
    first_t, later_ts = T[0], T[1:]

    by_config: dict[str, list[int]] = defaultdict(list)
    by_op: dict[int, list[str]] = defaultdict(list)
    for j, l in F:
        by_config[j].append(l)
        by_op[l].append(j)

    # ---- 변수 (논문 x, s, y + 신규 w) ----
    x_keys = [(p, j, l) for p in P for (j, l) in F]
    s_keys = [(p, j, l, t) for p in P for (j, l) in F for t in T]
    y_keys = [
        (p, jp, jn, l, t)
        for p in P
        for jp in J
        for (jn, l) in F
        for t in later_ts
        if jp != jn and (jp, jn) in instance.reconfiguration_cost
    ]
    w_keys = (
        []
        if mode == "off"
        else [
            (k, p, j, t)
            for k in P
            for p in P
            if k != p
            for j in J
            for t in later_ts
        ]
    )
    v_keys = [(p, l, t) for p in P for l in L for t in T]
    flow_keys = _build_flow_keys(instance, P, T)

    vt = GRB.BINARY if w_binary else GRB.CONTINUOUS
    x = model.addVars(x_keys, vtype=GRB.BINARY, name="x")
    s = model.addVars(s_keys, vtype=GRB.BINARY, name="s")
    y = model.addVars(y_keys, lb=0.0, ub=1.0, vtype=vt, name="y")
    w = model.addVars(w_keys, lb=0.0, ub=1.0, vtype=vt, name="w")
    v = model.addVars(v_keys, lb=0.0, name="v")
    f = model.addVars(flow_keys, lb=0.0, name="f")

    # ---- 약식 기호 ----
    def sigma(p, j, t):
        """위치 p에 config j 기계가 있으면 1 (op에 대한 합)."""
        return gp.quicksum(s[p, j, l, t] for l in by_config[j])

    def occ(p, t):
        """위치 p의 점유."""
        return gp.quicksum(s[p, j, l, t] for (j, l) in F)

    def Win(p, j, t):
        """config j를 달고 p로 들어온 이동."""
        if mode == "off":
            return gp.LinExpr(0.0)
        return gp.quicksum(w[k, p, j, t] for k in P if k != p)

    def Wout(p, j, t):
        """config j를 달고 p에서 나간 이동."""
        if mode == "off":
            return gp.LinExpr(0.0)
        return gp.quicksum(w[p, q, j, t] for q in P if q != p)

    def Yin(p, j, l, t):
        """다른 config에서 (j, l)로 재구성."""
        return gp.quicksum(y[p, jp, j, l, t] for jp in J if (p, jp, j, l, t) in y)

    def Yout(p, j, t):
        """config j에서 다른 config로 재구성."""
        return gp.quicksum(y[p, j, jn, l, t] for (jn, l) in F if (p, j, jn, l, t) in y)

    # ---- 제약 ----
    for p in P:
        model.addConstr(gp.quicksum(x[p, j, l] for (j, l) in F) <= 1, name="buy_once[%s]" % p)
        for t in T:
            model.addConstr(occ(p, t) <= 1, name="eq3_occupancy[%s,%s]" % (p, t))          # (3)

    for (p, j, l) in x_keys:                                                               # (4')
        model.addConstr(s[p, j, l, first_t] == x[p, j, l], name="eq4_init[%s,%s,%s]" % (p, j, l))

    for p in P:
        for (j, l) in F:
            for t in later_ts:
                model.addConstr(                                                           # (20) = (5)+Win
                    s[p, j, l, t] <= sigma(p, j, t - 1) + Yin(p, j, l, t) + Win(p, j, t),
                    name="eq20_transition[%s,%s,%s,%s]" % (p, j, l, t),
                )
                model.addConstr(                                                           # (6)
                    Yin(p, j, l, t) <= s[p, j, l, t],
                    name="eq6_y_link[%s,%s,%s,%s]" % (p, j, l, t),
                )

    for (p, jp, jn, l, t) in y_keys:                                                       # (7)/(7')
        rhs = sigma(p, jp, t - 1)
        if mode == "joint":
            rhs = rhs + Win(p, jp, t)
        model.addConstr(y[p, jp, jn, l, t] <= rhs, name="eq7_y_pre[%s,%s,%s,%s,%s]" % (p, jp, jn, l, t))

    if mode != "off":
        for p in P:
            for j in J:
                for t in later_ts:
                    rhs = sigma(p, j, t)                                                   # (18a)/(18a')
                    if mode == "joint":
                        rhs = rhs + Yout(p, j, t)
                    model.addConstr(Win(p, j, t) <= rhs, name="eq18a_arrive[%s,%s,%s]" % (p, j, t))
                    model.addConstr(                                                       # (18b)
                        Wout(p, j, t) <= sigma(p, j, t - 1),
                        name="eq18b_depart[%s,%s,%s]" % (p, j, t),
                    )

    for p in P:                                                                            # (19)
        for t in later_ts:
            model.addConstr(
                occ(p, t) - occ(p, t - 1)
                == gp.quicksum(Win(p, j, t) for j in J) - gp.quicksum(Wout(p, j, t) for j in J),
                name="eq19_conserve[%s,%s]" % (p, t),
            )

    n_S = 0
    if use_S:                                                                              # (S) 선택
        for p in P:
            for j in J:
                for t in later_ts:
                    model.addConstr(
                        sigma(p, j, t)
                        == sigma(p, j, t - 1)
                        - Wout(p, j, t)
                        + Win(p, j, t)
                        - Yout(p, j, t)
                        + gp.quicksum(Yin(p, j, l, t) for l in by_config[j]),
                        name="eqS_balance[%s,%s,%s]" % (p, j, t),
                    )
                    n_S += 1

    # ---- 흐름층 (8)~(15): 논문/base와 동일 ----
    for p in P:
        for l in L:
            for t in T:
                model.addConstr(
                    v[p, l, t]
                    <= gp.quicksum(instance.production_rate[j, l] * s[p, j, l, t] for j in by_op[l]),
                    name="eq8_capacity[%s,%s,%s]" % (p, l, t),
                )

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
                model.addConstr(gp.quicksum(f[k] for k in incoming[p, l, t]) == v[p, l, t])
                model.addConstr(gp.quicksum(f[k] for k in outgoing[p, l, t]) == v[p, l, t])

    lam = add_route_demand_constraints(
        model,
        instance,
        flow_keys,
        f,
        force_lambda=bool(getattr(config, "FORCE_ROUTE_LAMBDA", False)),
    )

    # ---- 목적함수 (1) ----
    purchase_cost = gp.quicksum(instance.cost[j] * x[p, j, l] for (p, j, l) in x_keys)
    reconfiguration_cost = gp.quicksum(
        instance.reconfiguration_cost[jp, jn] * y[p, jp, jn, l, t] for (p, jp, jn, l, t) in y_keys
    )
    # MOVE_COST_FLAT가 주어지면 이동비를 (단가 x 거리)로 계산한다 — 서훈 모델과 같은 정의.
    _flat = getattr(config, "MOVE_COST_FLAT", None)
    move_cost = gp.quicksum(
        (float(_flat) * instance.distance[k, p] if _flat is not None
         else instance.cost[j] * (alpha + beta * instance.distance[k, p])) * w[k, p, j, t]
        for (k, p, j, t) in w_keys
    )
    handling_cost = gp.quicksum(
        instance.parameters["material_handling_cost"]
        * instance.distance[p, q]
        * f[p, left, q, right, t]
        for (p, left, q, right, t) in flow_keys
    )
    model.setObjective(
        purchase_cost + reconfiguration_cost + move_cost + handling_cost, GRB.MINIMIZE
    )

    lp_bound, lp_seconds = _compute_lp_relaxation_bound(model, config)

    # off 해를 MIP start로 넣으면 joint는 반드시 off 이하가 된다 (off 해는 joint에서도 실행가능).
    if bool(getattr(config, "USE_WARM_START", False)):
        wdir = getattr(config, "WARM_START_DIR", None)
        if wdir is not None:
            assigned = apply_warm_start({"x": x, "s": s, "y": y, "v": v, "f": f}, wdir)
            print("    warm start 적용: %s" % (assigned,), flush=True)

    model.optimize()

    sol = _extract(
        model, instance, x, s, y, w, v, f,
        purchase_cost, reconfiguration_cost, move_cost, handling_cost,
        lp_bound, lp_seconds, mode, alpha, beta, use_S, w_binary, n_S,
    )
    if lam is not None and model.SolCount:
        sol.summary["route_shares"] = route_shares(instance, lam)
    return sol


def _build_flow_keys(instance, P, T):
    """base(Src/milp.py)와 동일한 material flow key."""
    keys = []
    for t in T:
        for left, right in instance.route_arcs:
            if instance.arc_demand.get((t, left, right), 0.0) <= 0:
                continue
            froms = [instance.start_location] if left == instance.start_operation else P
            tos = [instance.end_location] if right == instance.end_operation else P
            for p in froms:
                for q in tos:
                    if p != q:
                        keys.append((p, left, q, right, t))
    return keys


def _extract(model, instance, x, s, y, w, v, f,
             purchase_cost, reconfiguration_cost, move_cost, handling_cost,
             lp_bound, lp_seconds, mode, alpha, beta, use_S, w_binary, n_S) -> RMSSolution:
    status_name = {
        GRB.OPTIMAL: "OPTIMAL",
        GRB.TIME_LIMIT: "TIME_LIMIT",
        GRB.INFEASIBLE: "INFEASIBLE",
        GRB.INF_OR_UNBD: "INF_OR_UNBD",
        GRB.SUBOPTIMAL: "SUBOPTIMAL",
    }.get(model.Status, str(model.Status))
    summary: dict[str, Any] = {
        "problem_name": instance.problem_name,
        "model_type": "saffar_w",
        "adaptive_mode": mode,
        "alpha": alpha,
        "beta": beta,
        "balance_eq_S": use_S,
        "w_binary": w_binary,
        "num_S_rows": n_S,
        "status": int(model.Status),
        "status_name": status_name,
        "periods": instance.periods,
        "operations": instance.operations,
    }
    summary.update(_solver_metrics(model))
    summary["lp_relaxation_bound"] = lp_bound
    summary["lp_relaxation_seconds"] = lp_seconds
    if not model.SolCount:
        return RMSSolution(summary=summary)

    cb = {
        "purchase_cost": _clean_float(purchase_cost.getValue()),
        "reconfiguration_cost": _clean_float(reconfiguration_cost.getValue()),
        "material_handling_cost": _clean_float(handling_cost.getValue()),
        "relocation_cost": _clean_float(move_cost.getValue() if len(w) else 0.0),
    }
    cb["total_objective"] = _clean_float(sum(cb.values()))
    summary["objective"] = cb["total_objective"]

    purchased = [
        {"location": p, "machine": instance.machine[j], "configuration": j,
         "initial_operation": l, "purchase_cost": instance.cost[j]}
        for (p, j, l), var in sorted(x.items()) if var.X > 0.5
    ]
    flow_by_node = {(p, l, t): var.X for (p, l, t), var in v.items()}
    states = [
        {"period": t, "location": p, "machine": instance.machine[j], "configuration": j,
         "operation": l, "flow": round(flow_by_node.get((p, l, t), 0.0), 6)}
        for (p, j, l, t), var in sorted(s.items(), key=lambda i: (i[0][3], i[0][0]))
        if var.X > 0.5
    ]
    reconfigs = [
        {"period": t, "location": p, "from_configuration": jp, "to_configuration": jn,
         "from_machine": instance.machine[jp], "to_machine": instance.machine[jn],
         "operation": l, "reconfiguration_cost": instance.reconfiguration_cost[jp, jn]}
        for (p, jp, jn, l, t), var in sorted(y.items(), key=lambda i: (i[0][4], i[0][0]))
        if var.X > 0.5
    ]
    relocations = [
        {"period": t, "from_location": k, "to_location": p, "configuration": j,
         "machine": instance.machine[j], "distance": instance.distance[k, p],
         "relocation_cost": round(instance.cost[j] * (alpha + beta * instance.distance[k, p]), 6)}
        for (k, p, j, t), var in sorted(w.items(), key=lambda i: (i[0][3], i[0][0]))
        if var.X > 0.5
    ]
    flows = []
    for (p, left, q, right, t), var in sorted(f.items(), key=lambda i: (i[0][4], i[0][0])):
        if var.X > 1e-6:
            d = instance.distance[p, q]
            c = instance.parameters["material_handling_cost"]
            flows.append({"period": t, "from_location": p, "from_operation": left,
                          "to_location": q, "to_operation": right, "flow": round(var.X, 6),
                          "distance": d, "mhc": c, "flow_cost": round(var.X * d * c, 6)})

    summary["n_relocations"] = len(relocations)
    summary["n_reconfigurations"] = len(reconfigs)
    summary["n_machines"] = len(purchased)
    # joint에서 한 경계에 이동과 재구성을 함께 한 건 수
    reloc_arrivals = {(r["to_location"], r["configuration"], r["period"]) for r in relocations}
    summary["n_move_and_reconfig"] = sum(
        1 for rc in reconfigs
        if (rc["location"], rc["from_configuration"], rc["period"]) in reloc_arrivals
    )
    return RMSSolution(
        summary=summary, purchased_machines=purchased, machine_states=states,
        reconfigurations=reconfigs, material_flows=flows,
        cost_breakdown=cb, relocations=relocations,
    )
