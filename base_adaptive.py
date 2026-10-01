# -*- coding: utf-8 -*-
"""base_adaptive.py — Saffar 원형 MILP + 기계 이동(relocation) 이진변수 w.

Saffar, Moghaddam & Huang (2025), IJPR 63(17) 의 식 (1)-(16) 을 그대로 두고
이동 이진변수 w_{kpjt} 하나만 추가한 정식화다. 논문의 x, s, y 를 전부 유지한다.
network 모형도, z 통합전이 인코딩도 쓰지 않는다.

논문 대비 변경
  삭제 (2)   : 상태의 구매위치 영구귀속            -> (19) 가 대체
  수정 (4')  : s_{pjl1} = x_{pjl}  (등식으로 강화)
  수정 (5)->(20): 이동 유입항 추가
  수정 (7)->(7'): joint 에서만 이동 유입항 추가
  신규 (18a) : 도착 등록   sum_k w_{kpjt} <= sum_l s_{pjlt}      (joint: + 재구성 유출)
  신규 (18b) : 출발 조건   sum_q w_{kqjt} <= sum_l s_{kjl(t-1)}
  신규 (19)  : 기계 보존   점유 변화 = 이동 유입 - 이동 유출   (등식 = 폐기 불가)
  수정 (1)   : 목적함수에 이동비 + C_j(alpha + beta*D_{kp}) * w
  유지 (3) (6) (8)~(15)
  선택 (S)   : config 단위 보존 등식. 새 변수 없이 LP 를 강하게 만든다(최적해를 자르지 않음).

이동 정책 (config.ADAPTIVE_MODE)
  off      : w 를 만들지 않는다. 논문 원형과 동치.
  separate : 이동과 재구성을 같은 기간에 함께 하지 못한다.
  joint    : 이동 + 재구성 동시 허용.

플래그 (config 모듈의 속성으로 읽는다)
  ADAPTIVE_MODE        "off" | "separate" | "joint"
  ALPHA, BETA          이동비 = C_j * (ALPHA + BETA * D_kp)
  MOVE_COST_FLAT       None 이 아니면 이동비 = MOVE_COST_FLAT * D_kp (거리 비례 단가)
  SAFFAR_BALANCE_EQ    (S) 강화식 사용 여부
  SAFFAR_W_BINARY      w, y 를 이진으로 선언할지 (False 면 연속)
  TIME_LIMIT, MIP_GAP, MIP_FOCUS, OUTPUT_FLAG, GUROBI_PARAMS
  USE_WARM_START, WARM_START_DIR

사용
    from Src.data import load_instance
    import config, base_adaptive
    inst = load_instance(config)
    sol  = base_adaptive.solve_milp(inst, config)
    print(sol.summary["objective"])

이 파일 하나에 모델이 완결되어 있다. 외부에서 받는 것은 load_instance 가 만든
instance 객체뿐이고, warm start 는 선택 의존이다.
"""
from __future__ import annotations

import math
import time
from collections import defaultdict
from types import SimpleNamespace
from dataclasses import dataclass, field
from typing import Any

import gurobipy as gp
from gurobipy import GRB

try:                                  # warm start 는 선택 기능
    from Src.warm_start import apply_warm_start
except Exception:                     # noqa: BLE001
    apply_warm_start = None


# =============================================================================
#  공용 헬퍼 (Src/milp.py 에서 인라인)
# =============================================================================
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
    relocations: list[dict[str, Any]] = field(default_factory=list)


def _clean_float(value: float, integer_tolerance: float = 1e-3) -> float:
    """Gurobi numerical noise를 사람이 읽기 좋은 값으로 정리한다."""
    value = float(value)
    nearest_integer = round(value)
    if abs(value - nearest_integer) <= integer_tolerance:
        return float(nearest_integer)
    return round(value, 6)


def _safe_model_attr(model, name: str):
    """status에 따라 존재하지 않을 수 있는 Gurobi attribute를 안전하게 읽는다."""
    try:
        value = getattr(model, name)
    except (AttributeError, gp.GurobiError):
        return None
    if value in {GRB.INFINITY, -GRB.INFINITY} or (isinstance(value, float) and math.isinf(value)):
        return None  # incumbent가 없으면 MIPGap이 inf로 나온다
    return _clean_float(value)


def _apply_gurobi_params(model, config) -> None:
    """config.GUROBI_PARAMS의 임의 Gurobi 파라미터를 그대로 전달한다.

    실험 기록용으로 유용한 것들:
      LogFile  : Gurobi 로그를 파일로도 남긴다(bound 궤적 보존).
      SolFiles : 개선된 incumbent가 나올 때마다 .sol 파일로 저장한다(중간 layout 보존).
    """
    params = getattr(config, "GUROBI_PARAMS", None)
    if not params:
        return
    for name, value in params.items():
        model.setParam(name, value)


def _solver_metrics(model) -> dict[str, float | int | None]:
    """formulation 비교에 필요한 Gurobi solve 지표를 summary에 기록한다."""
    metrics: dict[str, float | int | None] = {
        "runtime_seconds": float(model.Runtime),
        "num_vars": int(model.NumVars),
        "num_constraints": int(model.NumConstrs),
        "num_binary_vars": int(model.NumBinVars),
        "num_integer_vars": int(model.NumIntVars),
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


def _compute_lp_relaxation_bound(model, config) -> tuple[float | None, float | None]:
    """선택적으로 pure LP relaxation bound와 그 LP를 푸는 데 걸린 시간을 계산한다.

    MIP solve 전에 별도 relaxation model을 한 번 풀기 때문에 큰 instance에서는
    시간이 추가로 든다. 필요할 때만 config.COMPUTE_LP_RELAXATION_BOUND=True로 켠다.
    반환값은 (bound, seconds)이며, 계산하지 않으면 (None, None)이다.
    """
    if not bool(getattr(config, "COMPUTE_LP_RELAXATION_BOUND", False)):
        return None, None
    model.update()
    relaxation = model.relax()
    relaxation.Params.OutputFlag = 0
    relaxation.optimize()
    seconds = float(relaxation.Runtime)
    if relaxation.Status != GRB.OPTIMAL:
        return None, seconds
    return _clean_float(relaxation.ObjVal), seconds


# ===========================================================================
#  라우트 수요 제약 (Src/route_alternatives.py 에서 인라인)
# ===========================================================================
def add_route_demand_constraints(model, instance, flow_keys, f, force_lambda: bool = False):
    """arc별 수요 등식을 추가하고, 대안 라우트가 있으면(또는 force_lambda) λ 변수 dict를, 없으면 None을 반환한다.

    force_lambda=True는 대안이 파트당 1개뿐이어도 λ 경로를 강제한다(λ≡1이 되어 결과는 동일해야 함 — 동일성 확인용).
    """
    flows_by_arc_t: dict[tuple[int, int, int], list] = defaultdict(list)
    for key in flow_keys:
        _p, left, _q, right, t = key
        flows_by_arc_t[(left, right, t)].append(key)

    periods = instance.periods
    if not getattr(instance, "has_route_alternatives", False) and not force_lambda:
        for t in periods:
            for left, right in instance.route_arcs:
                required = instance.arc_demand.get((t, left, right), 0.0)
                if required <= 0:
                    continue
                arc_flow = gp.quicksum(f[key] for key in flows_by_arc_t[(left, right, t)])
                model.addConstr(arc_flow == required, name=f"arc_demand[{t},{left},{right}]")
        return None

    part_routes = instance.part_routes
    part_demand = instance.part_demand

    def demand_of(part: str, t: int) -> float:
        return float(part_demand.get((part, t), 0.0))

    arc_members: dict[tuple[int, int], list[tuple[str, int]]] = defaultdict(list)
    for part, routes in part_routes.items():
        for k, route in enumerate(routes):
            for arc in zip(route[:-1], route[1:]):
                arc_members[arc].append((part, k))

    lam_keys = [
        (part, k, t)
        for part, routes in part_routes.items()
        for k in range(len(routes))
        for t in periods
        if demand_of(part, t) > 0
    ]
    lam = model.addVars(lam_keys, lb=0.0, ub=1.0, name="lam")

    # 파트별 배분 비율 합 = 1 (수요가 있는 기간만)
    for part, routes in part_routes.items():
        for t in periods:
            if demand_of(part, t) <= 0:
                continue
            model.addConstr(
                gp.quicksum(lam[part, k, t] for k in range(len(routes))) == 1.0,
                name=f"route_mix[{part},{t}]",
            )

    # arc별 흐름 == 그 arc를 지나는 대안들의 (수요 × λ) 합
    for t in periods:
        for left, right in instance.route_arcs:
            members = [(part, k) for part, k in arc_members.get((left, right), []) if demand_of(part, t) > 0]
            if not members:
                continue
            arc_flow = gp.quicksum(f[key] for key in flows_by_arc_t[(left, right, t)])
            required = gp.quicksum(demand_of(part, t) * lam[part, k, t] for part, k in members)
            model.addConstr(arc_flow == required, name=f"arc_demand[{t},{left},{right}]")
    return lam


def route_shares(instance, lam) -> list[dict[str, Any]]:
    """해에서 λ > 0인 (파트, 대안, 기간)을 사람이 읽기 좋은 row list로 만든다."""
    if lam is None:
        return []
    rows: list[dict[str, Any]] = []
    for (part, k, t), var in sorted(lam.items(), key=lambda item: (item[0][0], item[0][2], item[0][1])):
        if var.X > 1e-6:
            route = instance.part_routes[part][k]
            demand = float(instance.part_demand.get((part, t), 0.0))
            rows.append({
                "part": part,
                "period": t,
                "alternative": k,
                "route": ">".join(str(op) for op in route[1:-1]),
                "share": round(float(var.X), 4),
                "flow": round(float(var.X) * demand, 4),
            })
    return rows


# ===========================================================================
#  모델
# ===========================================================================
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
        if wdir is not None and apply_warm_start is not None:
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


# ===========================================================================
#  단독 실행 진입점
# ===========================================================================
def _cli() -> int:
    """python base_adaptive.py [데이터셋] [모드] [시간제한] [--alpha A] [--beta B] [--save DIR]

    예)
      python base_adaptive.py                              multi_part, off, 600초
      python base_adaptive.py youssef_2007 joint 300
      python base_adaptive.py multi_part joint 600 --alpha 0.02 --beta 0.004
      python base_adaptive.py youssef_2007 joint 300 --save Result/my_run
    """
    import argparse
    import sys
    from pathlib import Path as _Path

    ap = argparse.ArgumentParser(description="Saffar 원형 + 이동 이진변수 w 정식화")
    ap.add_argument("dataset", nargs="?", default=None, help="Data/ 아래 폴더명 (기본: config.PROBLEM_NAME)")
    ap.add_argument("mode", nargs="?", default=None, choices=["off", "separate", "joint"],
                    help="이동 정책 (기본: config.ADAPTIVE_MODE)")
    ap.add_argument("time_limit", nargs="?", type=int, default=None, help="초 (기본: config.TIME_LIMIT)")
    ap.add_argument("--alpha", type=float, default=None, help="이동비 고정 계수")
    ap.add_argument("--beta", type=float, default=None, help="이동비 거리 계수")
    ap.add_argument("--flat", type=float, default=None, help="거리당 단가로 이동비 계산 (alpha/beta 대신)")
    ap.add_argument("--gap", type=float, default=None, help="MIPGap 목표 (예 0.03)")
    ap.add_argument("--balance-eq", action="store_true", help="(S) 강화식 사용")
    ap.add_argument("--save", default=None, help="해를 저장할 폴더")
    args = ap.parse_args()

    cfg_mod = None
    for name in ("my_config", "config"):          # my_config.py 가 있으면 그것을 쓴다
        try:
            cfg_mod = __import__(name)
            print("설정 파일: %s.py" % name)
            break
        except ImportError:
            continue
    if cfg_mod is None:
        print("my_config.py 또는 config.py 를 찾을 수 없다. 저장소 루트에서 실행하라.",
              file=sys.stderr)
        return 1
    from Src.data import load_instance

    cfg = SimpleNamespace(**{k: getattr(cfg_mod, k) for k in dir(cfg_mod) if k.isupper()})
    if args.dataset:
        base = _Path(getattr(cfg_mod, "BASE_DIR", _Path(__file__).resolve().parent)) / "Data" / args.dataset
        if not base.exists():
            print("데이터셋 폴더가 없다: %s" % base, file=sys.stderr)
            return 1
        cfg.PROBLEM_NAME = args.dataset
        for key, fn in [("LOCATION_FILE", "locations.csv"), ("CONFIGURATION_FILE", "configurations.csv"),
                        ("PRODUCTION_RATE_FILE", "production_rates.csv"), ("DEMAND_FILE", "demands.csv"),
                        ("PARAMETER_FILE", "parameters.csv"), ("SHARED_RESOURCE_FILE", "shared_resources.csv"),
                        ("RESOURCE_REQUIREMENT_FILE", "resource_requirements.csv"),
                        ("MODULE_COST_FILE", "module_costs.csv")]:
            setattr(cfg, key, base / fn)
    if args.mode:
        cfg.ADAPTIVE_MODE = args.mode
    if args.time_limit:
        cfg.TIME_LIMIT = args.time_limit
    if args.alpha is not None:
        cfg.ALPHA = args.alpha
    if args.beta is not None:
        cfg.BETA = args.beta
    cfg.MOVE_COST_FLAT = args.flat          # None 이면 C_j(alpha + beta*D) 식을 쓴다
    if args.gap is not None:
        cfg.MIP_GAP = args.gap
    cfg.SAFFAR_BALANCE_EQ = args.balance_eq

    print("데이터 %s | 모드 %s | 시간제한 %ss | alpha %s beta %s%s"
          % (cfg.PROBLEM_NAME, cfg.ADAPTIVE_MODE, cfg.TIME_LIMIT,
             getattr(cfg, "ALPHA", 0.0), getattr(cfg, "BETA", 0.0),
             " | (S) 사용" if cfg.SAFFAR_BALANCE_EQ else ""), flush=True)

    instance = load_instance(cfg)
    solution = solve_milp(instance, cfg)
    sm = solution.summary

    print("\n" + "=" * 60)
    print("  상태        %s" % {2:"OPTIMAL",3:"INFEASIBLE",9:"TIME_LIMIT"}.get(sm.get("status"), sm.get("status")))
    print("  목적함수    %s" % sm.get("objective"))
    print("  best bound  %s" % sm.get("best_bound"))
    print("  MIP gap     %s" % sm.get("mip_gap"))
    print("  LP 완화     %s" % sm.get("lp_relaxation_bound"))
    cb = solution.cost_breakdown or {}
    print("  구매 %s / 재구성 %s / 자재취급 %s / 이동 %s"
          % (cb.get("purchase_cost"), cb.get("reconfiguration_cost"),
             cb.get("material_handling_cost"), cb.get("relocation_cost")))
    print("  기계 %s대 / 재구성 %s회 / 이동 %s회"
          % (sm.get("n_machines"), sm.get("n_reconfigurations"), sm.get("n_relocations")))
    print("=" * 60)

    if args.save:
        from Src.output import save_solution
        out = _Path(args.save)
        out.mkdir(parents=True, exist_ok=True)
        save_solution(solution, out)
        print("해 저장:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
