# ============================================================
# RMS Dynamic Layout Design - Multi-Part Example 2
# Manual-data Gurobi implementation
#
# Based on:
# Saffar et al. (2025), Section 3.3.2
# "Example 2: RMS layout design for a part family"
#
# 핵심:
# - CSV 사용 안 함
# - 논문 Table 2, Table 3, Figure 3 데이터를 코드 내부에 수기 입력
# - 논문 수식 (1)~(16)의 의미를 반영
# - 논문 reported solution 36,006과 비교
#
# 필요:
# pip install gurobipy
# ============================================================

import gurobipy as gp
from gurobipy import GRB


# ============================================================
# 0. Solver settings
# ============================================================

TIME_LIMIT_SECONDS = 25000  # 2시간
MIP_GAP = 1e-4

PAPER_PURCHASE_COST = 19270
PAPER_RECONFIG_COST = 1900
PAPER_MHC_COST = 14836
PAPER_TOTAL_COST = 36006


# ============================================================
# 1. Basic sets and parameters
# ============================================================

PERIODS = [1, 2, 3, 4]

# 논문 Figure 3 기준: 1~20은 RMT 설치 가능 위치, 21=Start, 22=End
REAL_LOCS = list(range(1, 21))
START_LOC = 21
END_LOC = 22

START_OP = "START"
END_OP = "END"

# 논문 Example 2에서 필요한 실제 operation
REAL_OPS = [2, 8, 11, 12, 17]

# 비용 파라미터
MHC = 4
ADD_MODULE_COST = 50
REMOVE_MODULE_COST = 25


# ============================================================
# 2. Manual location data from Figure 3
# ============================================================

# Figure 3의 각 위치에 표시된 좌표를 그대로 반영
coords = {
    1: (0, 0),  2: (1, 0),  3: (2, 0),  4: (3, 0),  5: (4, 0),
    6: (0, 1),  7: (1, 1),  8: (2, 1),  9: (3, 1),  10: (4, 1),
    11: (0, 2), 12: (1, 2), 13: (2, 2), 14: (3, 2), 15: (4, 2),
    16: (0, 3), 17: (1, 3), 18: (2, 3), 19: (3, 3), 20: (4, 3),

    # Figure 3의 입구/출구
    21: (-2, 1.5),
    22: (6, 1.5),
}

def manhattan(p, q):
    x1, y1 = coords[p]
    x2, y2 = coords[q]
    return abs(x1 - x2) + abs(y1 - y2)


# ============================================================
# 3. Manual RMT configuration data from Table 2
# ============================================================

# 표기:
# M1C1 = Machine 1, configuration 1
# 논문 표의 mc^i_j 또는 mc_i_j 표기를 Python용으로 단순화
#
# rate: {operation: production_rate}
# aux: auxiliary modules
# basic: basic modules

configs = {
    # --------------------
    # M1
    # --------------------
    "M1C1": {
        "machine": "M1",
        "cost": 750,
        "basic": {1, 5},
        "aux": {13, 17, 21, 22},
        "rate": {4: 14, 8: 12, 12: 8, 16: 18},
    },
    "M1C2": {
        "machine": "M1",
        "cost": 955,
        "basic": {1, 5},
        "aux": {12, 13, 15, 20, 21},
        "rate": {5: 15, 9: 20, 18: 16},
    },
    "M1C3": {
        "machine": "M1",
        "cost": 1025,
        "basic": {1, 5},
        "aux": {11, 17, 18, 20, 21},
        "rate": {3: 20, 7: 15, 16: 25},
    },
    "M1C4": {
        "machine": "M1",
        "cost": 840,
        "basic": {1, 5},
        "aux": {15, 17, 18},
        "rate": {10: 15, 18: 12},
    },

    # --------------------
    # M2
    # --------------------
    "M2C1": {
        "machine": "M2",
        "cost": 1215,
        "basic": {2, 4, 8},
        "aux": {11, 13, 16, 22, 24},
        "rate": {1: 14, 6: 15, 12: 12, 20: 20},
    },
    "M2C2": {
        "machine": "M2",
        "cost": 910,
        "basic": {2, 4, 8},
        "aux": {14, 16, 19},
        "rate": {2: 15, 13: 14, 15: 15},
    },
    "M2C3": {
        "machine": "M2",
        "cost": 1140,
        "basic": {2, 4, 8},
        "aux": {13, 19, 24},
        "rate": {3: 25, 8: 18, 11: 25, 17: 20},
    },
    "M2C4": {
        "machine": "M2",
        "cost": 1350,
        "basic": {2, 4, 8},
        "aux": {11, 13, 15, 18, 24},
        "rate": {2: 20, 5: 20, 7: 18, 14: 24},
    },
    "M2C5": {
        "machine": "M2",
        "cost": 1050,
        "basic": {2, 4, 8},
        "aux": {11, 14, 18},
        "rate": {4: 18, 13: 20, 18: 14, 20: 15},
    },

    # --------------------
    # M3
    # --------------------
    "M3C1": {
        "machine": "M3",
        "cost": 780,
        "basic": {3, 5, 7},
        "aux": {11, 12, 14, 16, 18},
        "rate": {2: 12, 9: 15, 12: 10, 17: 10},
    },
    "M3C2": {
        "machine": "M3",
        "cost": 1825,
        "basic": {3, 5, 7},
        "aux": {12, 13, 14, 17, 19, 20},
        "rate": {1: 30, 4: 26, 8: 24, 11: 24, 15: 20, 17: 35, 19: 15},
    },

    # --------------------
    # M4
    # --------------------
    "M4C1": {
        "machine": "M4",
        "cost": 1350,
        "basic": {4, 9},
        "aux": {18, 23},
        "rate": {6: 25, 10: 30, 18: 25},
    },
    "M4C2": {
        "machine": "M4",
        "cost": 1500,
        "basic": {4, 9},
        "aux": {11, 15, 18, 20, 21},
        "rate": {1: 25, 12: 22, 17: 30, 20: 26},
    },
    "M4C3": {
        "machine": "M4",
        "cost": 1400,
        "basic": {4, 9},
        "aux": {13, 14, 17, 18},
        "rate": {2: 18, 4: 25, 8: 16, 13: 22, 16: 28, 19: 20},
    },

    # --------------------
    # M5
    # --------------------
    "M5C1": {
        "machine": "M5",
        "cost": 900,
        "basic": {3, 6, 10},
        "aux": {20, 22},
        "rate": {1: 16, 7: 15, 11: 15, 14: 18, 18: 18},
    },
    "M5C2": {
        "machine": "M5",
        "cost": 1175,
        "basic": {3, 6, 10},
        "aux": {16, 17, 19, 20, 25},
        "rate": {3: 24, 5: 20, 10: 25, 17: 24, 20: 20},
    },
    "M5C3": {
        "machine": "M5",
        "cost": 1230,
        "basic": {3, 6, 10},
        "aux": {11, 12, 13, 15, 22},
        "rate": {4: 24, 9: 30, 15: 18},
    },
    "M5C4": {
        "machine": "M5",
        "cost": 1175,
        "basic": {3, 6, 10},
        "aux": {20, 22, 24},
        "rate": {1: 20, 6: 22, 7: 14, 14: 20, 16: 16, 19: 18},
    },
}

CFG_IDS = list(configs.keys())

def can_process(cfg, op):
    return op in configs[cfg]["rate"]

def capacity(cfg, op):
    return configs[cfg]["rate"].get(op, 0)

def reconfig_cost(cfg_from, cfg_to):
    """
    논문 r_jj':
    같은 machine type 내부에서 configuration 변경 가능.
    비용 = 추가 auxiliary module 수 * 50 + 제거 auxiliary module 수 * 25
    """
    if configs[cfg_from]["machine"] != configs[cfg_to]["machine"]:
        return None

    old_aux = configs[cfg_from]["aux"]
    new_aux = configs[cfg_to]["aux"]

    add_count = len(new_aux - old_aux)
    remove_count = len(old_aux - new_aux)

    return ADD_MODULE_COST * add_count + REMOVE_MODULE_COST * remove_count


# ============================================================
# 4. Manual multi-part demand from Table 3
# ============================================================

part_demand = {
    "A": {1: 20, 2: 30, 3: 15, 4: 0},
    "B": {1: 50, 2: 60, 3: 45, 4: 30},
    "C": {1: 0,  2: 20, 3: 40, 4: 60},
}

part_routes = {
    "A": [2, 12, 17],
    "B": [2, 12, 11],
    "C": [2, 12, 11, 8],
}

PARTS = list(part_routes.keys())

# operation별 필요 생산능력 d_l^t 계산
op_demand = {op: {t: 0 for t in PERIODS} for op in REAL_OPS}

for part in PARTS:
    for t in PERIODS:
        d = part_demand[part][t]
        for op in part_routes[part]:
            op_demand[op][t] += d

print("\n=== Part routes ===")
for part in PARTS:
    print(f"Part {part}: {' -> '.join(map(str, part_routes[part]))}")

print("\n=== Operation demand d_l^t ===")
for op in REAL_OPS:
    print(f"Operation {op}: {op_demand[op]}")

# Table 4 검증
expected_op_demand = {
    2:  {1: 70, 2: 110, 3: 100, 4: 90},
    12: {1: 70, 2: 110, 3: 100, 4: 90},
    17: {1: 20, 2: 30,  3: 15,  4: 0},
    11: {1: 50, 2: 80,  3: 85,  4: 90},
    8:  {1: 0,  2: 20,  3: 40,  4: 60},
}

print("\n=== Table 4 check ===")
for op, expected in expected_op_demand.items():
    actual = op_demand[op]
    print(f"Operation {op}: actual={actual}, expected={expected}")
    for t in PERIODS:
        if actual[t] != expected[t]:
            raise ValueError(f"Table 4 mismatch: op={op}, t={t}, actual={actual[t]}, expected={expected[t]}")

print("Table 4 demand check passed.")


# ============================================================
# 5. q_ll^t direct predecessor arcs
# ============================================================

# 논문 q_ll^t = 1인 경우에만 material flow 가능.
# Example 2에서는 Part A/B/C의 route에서 직접 연결된 operation만 허용.
arcs = set()

for part, route in part_routes.items():
    arcs.add((START_OP, route[0]))

    for i in range(len(route) - 1):
        arcs.add((route[i], route[i + 1]))

    arcs.add((route[-1], END_OP))

arcs = sorted(arcs, key=lambda a: (str(a[0]), str(a[1])))

print("\n=== Direct predecessor arcs ===")
for a, b in arcs:
    print(f"{a} -> {b}")


# ============================================================
# 6. Build Gurobi model
# ============================================================

model = gp.Model("RMS_MultiPart_ManualData_Example2")

model.Params.OutputFlag = 1
model.Params.TimeLimit = TIME_LIMIT_SECONDS
model.Params.MIPGap = MIP_GAP

# 논문에서 v, inter-RMT flow는 integer variable
FLOW_TYPE = GRB.INTEGER


# ============================================================
# 7. Decision variables
# ============================================================

# x[p,j,l,t]
# 논문 표기에는 x_pjl로 되어 있으나,
# 3.3.2와 Table 6에서 2기 신규 구매가 존재하므로 구현에서는 t를 포함.
x = {}

# s[p,j,l,t]
s = {}

# y[p,j_from,j_to,l,t]
y = {}

# v[p,l,t]
v = {}

# f[p,l,q,k,t]
f = {}


# x, s
for p in REAL_LOCS:
    for cfg in CFG_IDS:
        for op in REAL_OPS:
            if can_process(cfg, op):
                for t in PERIODS:
                    x[p, cfg, op, t] = model.addVar(
                        vtype=GRB.BINARY,
                        name=f"x[{p},{cfg},{op},{t}]"
                    )

                    s[p, cfg, op, t] = model.addVar(
                        vtype=GRB.BINARY,
                        name=f"s[{p},{cfg},{op},{t}]"
                    )

# y
for p in REAL_LOCS:
    for cfg_from in CFG_IDS:
        for cfg_to in CFG_IDS:
            if cfg_from == cfg_to:
                continue

            rc = reconfig_cost(cfg_from, cfg_to)
            if rc is None:
                continue

            for op in REAL_OPS:
                if can_process(cfg_to, op):
                    for t in PERIODS:
                        if t == 1:
                            continue

                        y[p, cfg_from, cfg_to, op, t] = model.addVar(
                            vtype=GRB.BINARY,
                            name=f"y[{p},{cfg_from}->{cfg_to},{op},{t}]"
                        )

# v for real locations
for p in REAL_LOCS:
    for op in REAL_OPS:
        for t in PERIODS:
            v[p, op, t] = model.addVar(
                vtype=FLOW_TYPE,
                lb=0,
                name=f"v[{p},{op},{t}]"
            )

# dummy start/end v
for t in PERIODS:
    v[START_LOC, START_OP, t] = model.addVar(
        vtype=FLOW_TYPE,
        lb=0,
        name=f"v[{START_LOC},{START_OP},{t}]"
    )

    v[END_LOC, END_OP, t] = model.addVar(
        vtype=FLOW_TYPE,
        lb=0,
        name=f"v[{END_LOC},{END_OP},{t}]"
    )

# f variables only for allowed arcs
for t in PERIODS:
    for op1, op2 in arcs:
        from_locs = [START_LOC] if op1 == START_OP else REAL_LOCS
        to_locs = [END_LOC] if op2 == END_OP else REAL_LOCS

        for p in from_locs:
            for q in to_locs:
                f[p, op1, q, op2, t] = model.addVar(
                    vtype=FLOW_TYPE,
                    lb=0,
                    name=f"f[{p},{op1}->{q},{op2},{t}]"
                )

model.update()


# ============================================================
# 8. Objective function - Eq. (1)
# ============================================================

purchase_cost_expr = gp.quicksum(
    configs[cfg]["cost"] * xvar
    for (p, cfg, op, t), xvar in x.items()
)

reconfig_cost_expr = gp.quicksum(
    reconfig_cost(cfg_from, cfg_to) * yvar
    for (p, cfg_from, cfg_to, op, t), yvar in y.items()
)

mhc_cost_expr = gp.quicksum(
    MHC * manhattan(p, q) * fvar
    for (p, op1, q, op2, t), fvar in f.items()
)

model.setObjective(
    purchase_cost_expr + reconfig_cost_expr + mhc_cost_expr,
    GRB.MINIMIZE
)


# ============================================================
# 9. Constraints
# ============================================================

# ------------------------------------------------------------
# Eq. (2) adjusted:
# s_pjlt <= sum_{tau<=t} sum_j' sum_l' x_pj'l'tau
#
# p 위치의 RMT 상태가 존재하려면, 해당 period까지 그 위치에 RMT가 구매되어야 함.
# ------------------------------------------------------------
for (p, cfg, op, t), svar in s.items():
    purchased_until_t = gp.quicksum(
        x[p2, cfg2, op2, tau]
        for (p2, cfg2, op2, tau) in x
        if p2 == p and tau <= t
    )

    model.addConstr(
        svar <= purchased_until_t,
        name=f"Eq2_state_requires_purchase[{p},{cfg},{op},{t}]"
    )


# ------------------------------------------------------------
# Eq. (3):
# sum_j sum_l s_pjlt <= 1
#
# 한 위치 p는 한 period t에 하나의 configuration/operation만 수행 가능.
# ------------------------------------------------------------
for p in REAL_LOCS:
    for t in PERIODS:
        model.addConstr(
            gp.quicksum(
                s[p2, cfg, op, t2]
                for (p2, cfg, op, t2) in s
                if p2 == p and t2 == t
            ) <= 1,
            name=f"Eq3_one_state[{p},{t}]"
        )


# ------------------------------------------------------------
# Location uniqueness:
# 한 위치에는 전체 계획기간 동안 최대 하나의 RMT만 설치.
# ------------------------------------------------------------
for p in REAL_LOCS:
    model.addConstr(
        gp.quicksum(
            x[p2, cfg, op, t]
            for (p2, cfg, op, t) in x
            if p2 == p
        ) <= 1,
        name=f"One_RMT_per_location[{p}]"
    )


# ------------------------------------------------------------
# Eq. (4) extended:
# x_pjlt <= s_pjlt
#
# t기에 구매된 RMT는 t기에 해당 state로 활성화.
# ------------------------------------------------------------
for (p, cfg, op, t), xvar in x.items():
    model.addConstr(
        xvar <= s[p, cfg, op, t],
        name=f"Eq4_purchase_active[{p},{cfg},{op},{t}]"
    )


# ------------------------------------------------------------
# Eq. (5) adjusted:
# s_pjlt <= sum_l' s_pjl'(t-1) + sum_j' y_pj'jlt + x_pjlt
#
# t>1의 state는
# 1) 동일 configuration 유지
# 2) 재구성
# 3) 신규 구매
# 중 하나로만 가능.
# ------------------------------------------------------------
for (p, cfg, op, t), svar in s.items():
    if t == 1:
        continue

    prev_same_cfg = gp.quicksum(
        s[p, cfg, prev_op, t - 1]
        for prev_op in REAL_OPS
        if (p, cfg, prev_op, t - 1) in s
    )

    reconfig_into_cfg = gp.quicksum(
        y[p, cfg_from, cfg, op, t]
        for cfg_from in CFG_IDS
        if (p, cfg_from, cfg, op, t) in y
    )

    purchase_now = x[p, cfg, op, t]

    model.addConstr(
        svar <= prev_same_cfg + reconfig_into_cfg + purchase_now,
        name=f"Eq5_state_transition[{p},{cfg},{op},{t}]"
    )


# ------------------------------------------------------------
# Eq. (6):
# sum_j' y_pj'jlt <= s_pjlt
#
# 재구성되어 들어온 target state는 실제로 활성화되어야 함.
# ------------------------------------------------------------
for (p, cfg, op, t), svar in s.items():
    if t == 1:
        continue

    reconfig_into_cfg = gp.quicksum(
        y[p, cfg_from, cfg, op, t]
        for cfg_from in CFG_IDS
        if (p, cfg_from, cfg, op, t) in y
    )

    model.addConstr(
        reconfig_into_cfg <= svar,
        name=f"Eq6_reconfig_requires_state[{p},{cfg},{op},{t}]"
    )


# ------------------------------------------------------------
# Eq. (7):
# y_pj'jlt <= sum_l' s_pj'l'(t-1)
#
# 이전 period에 cfg_from 상태였을 때만 cfg_to로 재구성 가능.
# ------------------------------------------------------------
for (p, cfg_from, cfg_to, op, t), yvar in y.items():
    prev_from_state = gp.quicksum(
        s[p, cfg_from, prev_op, t - 1]
        for prev_op in REAL_OPS
        if (p, cfg_from, prev_op, t - 1) in s
    )

    model.addConstr(
        yvar <= prev_from_state,
        name=f"Eq7_reconfig_from_previous[{p},{cfg_from},{cfg_to},{op},{t}]"
    )


# ------------------------------------------------------------
# Eq. (8):
# v_plt <= sum_j s_pjlt B_jl
#
# 해당 RMT의 flow는 configuration별 생산능력을 초과할 수 없음.
# ------------------------------------------------------------
for p in REAL_LOCS:
    for op in REAL_OPS:
        for t in PERIODS:
            model.addConstr(
                v[p, op, t] <= gp.quicksum(
                    capacity(cfg, op) * s[p, cfg, op, t]
                    for cfg in CFG_IDS
                    if (p, cfg, op, t) in s
                ),
                name=f"Eq8_capacity[{p},{op},{t}]"
            )


# ------------------------------------------------------------
# Eq. (9):
# sum_p v_plt >= d_l^t
#
# operation별 총 처리량이 Table 4 수요 이상이어야 함.
# ------------------------------------------------------------
for op in REAL_OPS:
    for t in PERIODS:
        model.addConstr(
            gp.quicksum(v[p, op, t] for p in REAL_LOCS) >= op_demand[op][t],
            name=f"Eq9_demand[{op},{t}]"
        )


# ------------------------------------------------------------
# Eq. (10), Eq. (11):
# f <= outgoing node flow
# f <= incoming node flow
#
# q_lk^t = 1인 arc만 f 변수를 만들었으므로,
# q_lk^t가 0인 flow는 애초에 존재하지 않음.
# ------------------------------------------------------------
for (p, op1, q, op2, t), fvar in f.items():

    if p != START_LOC:
        model.addConstr(
            fvar <= v[p, op1, t],
            name=f"Eq10_flow_leaving[{p},{op1},{q},{op2},{t}]"
        )

    if q != END_LOC:
        model.addConstr(
            fvar <= v[q, op2, t],
            name=f"Eq11_flow_entering[{p},{op1},{q},{op2},{t}]"
        )


# ------------------------------------------------------------
# Eq. (12), Eq. (13):
# 실제 RMT node에 대해 incoming = v, outgoing = v
#
# 즉 incoming = outgoing = total flow.
# ------------------------------------------------------------
for p in REAL_LOCS:
    for op in REAL_OPS:
        for t in PERIODS:

            incoming = gp.quicksum(
                f[fp, fop, tq, top, tt]
                for (fp, fop, tq, top, tt) in f
                if tt == t and tq == p and top == op
            )

            outgoing = gp.quicksum(
                f[fp, fop, tq, top, tt]
                for (fp, fop, tq, top, tt) in f
                if tt == t and fp == p and fop == op
            )

            model.addConstr(
                incoming == v[p, op, t],
                name=f"Eq12_incoming_equals_v[{p},{op},{t}]"
            )

            model.addConstr(
                outgoing == v[p, op, t],
                name=f"Eq13_outgoing_equals_v[{p},{op},{t}]"
            )


# ------------------------------------------------------------
# Dummy START
#
# Example 2에서는 모든 part의 첫 operation이 2.
# START outgoing = operation 2의 총수요.
# ------------------------------------------------------------
first_ops = set(route[0] for route in part_routes.values())

if len(first_ops) != 1:
    raise ValueError("Example 2에서는 모든 part의 첫 operation이 동일해야 합니다.")

FIRST_OP = list(first_ops)[0]

for t in PERIODS:
    start_outgoing = gp.quicksum(
        f[fp, fop, tq, top, tt]
        for (fp, fop, tq, top, tt) in f
        if tt == t and fp == START_LOC and fop == START_OP
    )

    model.addConstr(
        start_outgoing == op_demand[FIRST_OP][t],
        name=f"Start_flow[{t}]"
    )

    model.addConstr(
        v[START_LOC, START_OP, t] == start_outgoing,
        name=f"Start_v_link[{t}]"
    )


# ------------------------------------------------------------
# Eq. (14) Dummy END
#
# END incoming = 완제품 총량 = operation 2의 총수요.
# v_END = END incoming.
# ------------------------------------------------------------
for t in PERIODS:
    end_incoming = gp.quicksum(
        f[fp, fop, tq, top, tt]
        for (fp, fop, tq, top, tt) in f
        if tt == t and tq == END_LOC and top == END_OP
    )

    model.addConstr(
        end_incoming == op_demand[FIRST_OP][t],
        name=f"End_flow[{t}]"
    )

    model.addConstr(
        v[END_LOC, END_OP, t] == end_incoming,
        name=f"Eq14_end_v_link[{t}]"
    )


# Eq. (15), Eq. (16)
# 변수 domain은 addVar에서 지정:
# v, f >= 0 integer
# x, s, y binary


# ============================================================
# 10. Optimize
# ============================================================

model.update()

print("\n=== Model size ===")
print("Variables   :", model.NumVars)
print("Constraints :", model.NumConstrs)
print("Time limit  :", model.Params.TimeLimit, "seconds")

model.optimize()


# ============================================================
# 11. Results
# ============================================================

print("\n=== Solver Status ===")
print("Status code:", model.Status)

if model.Status == GRB.OPTIMAL:
    print("Status: OPTIMAL")
elif model.Status == GRB.TIME_LIMIT:
    print("Status: TIME_LIMIT")
elif model.Status == GRB.INFEASIBLE:
    print("Status: INFEASIBLE")
elif model.Status == GRB.UNBOUNDED:
    print("Status: UNBOUNDED")
else:
    print("Status: OTHER")

if model.SolCount == 0:
    print("\nNo feasible solution found.")
    if model.Status == GRB.INFEASIBLE:
        model.computeIIS()
        model.write("rms_manual_multipart_iis.ilp")
        print("IIS file written: rms_manual_multipart_iis.ilp")
    raise SystemExit


purchase_cost_value = purchase_cost_expr.getValue()
reconfig_cost_value = reconfig_cost_expr.getValue()
mhc_cost_value = mhc_cost_expr.getValue()
total_cost_value = model.ObjVal

print("\n=== Gurobi Solution: Manual Multi-Part Example 2 ===")
print(f"Purchase cost        : {purchase_cost_value:,.0f}")
print(f"Reconfiguration cost : {reconfig_cost_value:,.0f}")
print(f"Material handling    : {mhc_cost_value:,.0f}")
print(f"Total cost           : {total_cost_value:,.0f}")

print("\n=== Paper reported solution ===")
print(f"Purchase cost        : {PAPER_PURCHASE_COST:,.0f}")
print(f"Reconfiguration cost : {PAPER_RECONFIG_COST:,.0f}")
print(f"Material handling    : {PAPER_MHC_COST:,.0f}")
print(f"Total cost           : {PAPER_TOTAL_COST:,.0f}")

print("\n=== Difference: Gurobi - Paper ===")
print(f"Purchase diff        : {purchase_cost_value - PAPER_PURCHASE_COST:,.0f}")
print(f"Reconfiguration diff : {reconfig_cost_value - PAPER_RECONFIG_COST:,.0f}")
print(f"Material handling diff: {mhc_cost_value - PAPER_MHC_COST:,.0f}")
print(f"Total diff           : {total_cost_value - PAPER_TOTAL_COST:,.0f}")

if model.Status == GRB.TIME_LIMIT:
    print("\n=== Time-limit information ===")
    print(f"Best incumbent objective : {model.ObjVal:,.4f}")
    print(f"Best bound               : {model.ObjBound:,.4f}")
    print(f"MIP gap                  : {model.MIPGap:.6f}")


# ============================================================
# 12. Detailed results
# ============================================================

print("\n=== Purchased RMTs x[p,cfg,op,t] ===")
purchased = []

for (p, cfg, op, t), var in x.items():
    if var.X > 0.5:
        purchased.append((t, p, cfg, op, configs[cfg]["cost"]))

for row in sorted(purchased):
    print(row)

print(f"Number of purchased RMTs: {len(purchased)}")


print("\n=== Purchase cost by period ===")
for t in PERIODS:
    cost_t = sum(cost for (tt, p, cfg, op, cost) in purchased if tt == t)
    print(f"Period {t}: {cost_t:,.0f}")


print("\n=== Reconfigurations y[p,cfg_from,cfg_to,op,t] ===")
reconfigs = []

for (p, cfg_from, cfg_to, op, t), var in y.items():
    if var.X > 0.5:
        cost = reconfig_cost(cfg_from, cfg_to)
        reconfigs.append((t, p, cfg_from, cfg_to, op, cost))

for row in sorted(reconfigs):
    print(row)

print(f"Number of reconfigurations: {len(reconfigs)}")


print("\n=== Reconfiguration cost by period ===")
for t in PERIODS:
    cost_t = sum(cost for (tt, p, cf, ct, op, cost) in reconfigs if tt == t)
    print(f"Period {t}: {cost_t:,.0f}")


print("\n=== Active states s[p,cfg,op,t] by period ===")
states = []

for (p, cfg, op, t), var in s.items():
    if var.X > 0.5:
        states.append((t, p, cfg, op))

for t in PERIODS:
    print(f"\nPeriod {t}")
    for row in sorted([r for r in states if r[0] == t]):
        print(row)


print("\n=== Operation load check ===")
for t in PERIODS:
    print(f"\nPeriod {t}")
    for op in REAL_OPS:
        actual = sum(v[p, op, t].X for p in REAL_LOCS)
        required = op_demand[op][t]
        print(f"Operation {op}: required={required:.0f}, actual={actual:.0f}")


print("\n=== Nonzero operation-level flows f[p,op1,q,op2,t] ===")
flows = []

for (p, op1, q, op2, t), var in f.items():
    if var.X > 1e-6:
        amount = var.X
        dist = manhattan(p, q)
        cost = amount * dist * MHC
        flows.append((t, p, op1, q, op2, amount, dist, cost))

for t in PERIODS:
    print(f"\nPeriod {t}")
    period_mhc = 0
    for row in sorted([r for r in flows if r[0] == t]):
        _, p, op1, q, op2, amount, dist, cost = row
        period_mhc += cost
        print(
            f"{p}({op1}) -> {q}({op2}) | "
            f"flow={amount:.0f}, dist={dist:.2f}, cost={cost:.0f}"
        )
    print(f"Material handling cost in Period {t}: {period_mhc:,.0f}")