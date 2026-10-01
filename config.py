from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "Data"

# 실행할 데이터셋을 선택한다. Data/ 아래 폴더명이다.
# - "single_part"  : Saffar Example 1 단일부품
# - "multi_part"   : Saffar Example 2 다중부품 (20슬롯, 4기간)
# - "youssef_2007" : Youssef & ElMaraghy 2007 데이터 (20슬롯, 4기간)
PROBLEM_NAME = "multi_part"
PROBLEM_DIR = DATA_DIR / PROBLEM_NAME

# 결과는 문제별로 나누어 저장한다. (예: Result/single_part, Result/multi_part)
RESULT_DIR = BASE_DIR / "Result" / PROBLEM_NAME

LOCATION_FILE = PROBLEM_DIR / "locations.csv"
CONFIGURATION_FILE = PROBLEM_DIR / "configurations.csv"
PRODUCTION_RATE_FILE = PROBLEM_DIR / "production_rates.csv"
DEMAND_FILE = PROBLEM_DIR / "demands.csv"
PARAMETER_FILE = PROBLEM_DIR / "parameters.csv"
SHARED_RESOURCE_FILE = PROBLEM_DIR / "shared_resources.csv"
RESOURCE_REQUIREMENT_FILE = PROBLEM_DIR / "resource_requirements.csv"
# module별 재구성 단가 파일 (선택). 파일이 있으면 재구성비를 module별 단가로 계산하고,
# 없으면 기존처럼 parameters.csv의 전역 add/remove_module_cost를 사용한다.
MODULE_COST_FILE = PROBLEM_DIR / "module_costs.csv"

TIME_LIMIT = 100
MIP_GAP = 0.0

# formulation 비교용 pure LP relaxation bound를 기록할지 여부.
# True이면 MIP solve 전에 LP relaxation을 한 번 더 풀기 때문에 실행시간이 추가된다.
COMPUTE_LP_RELAXATION_BOUND = True

# 논문 Figure 4 등 기존 해를 Gurobi MIP start로 넣을지 여부.
# multi_part에서 논문 해를 기준으로 시작하려면 아래 두 값을 켠다.
USE_WARM_START = False
WARM_START_DIR = PROBLEM_DIR / "warm_start_paper"

# warm start objective보다 나쁜 해를 탐색에서 제외하고 싶을 때만 사용한다.
USE_OBJECTIVE_CUTOFF = False
OBJECTIVE_CUTOFF = None

# 대안 라우트가 파트당 1개뿐이어도 λ(라우트 배분 비율) 경로로 모델을 만든다. λ≡1이라 결과는 동일해야 함(동일성 확인용).
FORCE_ROUTE_LAMBDA = False

# 재구성(configuration 변경) 허용 여부. False면 기계는 구매한 configuration을 끝까지 유지한다.
ALLOW_RECONFIGURATION = True

# 논문 식 (2)는 부등식(위치별 상태 수 <= 구매 여부). True로 두면 등식(Σs = Σx)으로 강화한다.
# 최적값은 같고 LP relaxation만 달라진다. 기본은 논문 원형(False).
STATE_EQUALS_PURCHASE = False

# 논문 Example에서는 같은 machine type 안에서만 configuration 변경을 허용한다.
# M1 -> M2 불가
SAME_MACHINE_RECONFIG_ONLY = True

# auxiliary module을 한정된 shared resource로 볼지 여부. (하위호환용 플래그)
USE_SHARED_RESOURCES = False

# shared resource를 모델에서 어떻게 다룰지 선택한다.
#   "off"      : 자원 제약 없음 (기준 문제, S1)
#   "fixed"    : shared_resources.csv의 Cap을 상수 상한으로 사용 (S2)
#   "variable" : Cap_r을 정수 결정변수로 두고, 비용 최소 후 ΣCap_r을 최소화 (최소 사이징, S3)
# SHARED_RESOURCE_MODE가 지정되면 USE_SHARED_RESOURCES보다 우선한다.
SHARED_RESOURCE_MODE = "variable"

# variable 모드에서 각 auxiliary module의 Cap_r 상한을 개별로 낮춘다. {모듈ID: 상한개수}
#   - 여기 없는 모듈은 상한이 안 걸린다(자유 = 위치 수까지).
#   - None이면 상한 없음(진짜 최소 사이징 탐색, S3).
#   - 아래 값은 min-cost(22,910) 최소 사이징(총 76)으로 고정 → 빠른 확인용 실험.
CAP_UPPER_BOUNDS = {
}

# variable 모드(lexicographic 2단계)의 목적별 시간 예산.
#   STAGE1_TIME_LIMIT: 1단계(비용 최소화) 시간(초). 초과하면 최적 증명을 못 했어도
#                      그 시점의 incumbent를 채택하고 2단계(ΣCap 최소화)로 넘어간다.
#                      이때 2단계 결과는 "비용 ≤ incumbent 조건의 최소 Cap"으로 해석해야 한다.
#   STAGE2_TIME_LIMIT: 2단계 시간(초). None이면 TIME_LIMIT을 사용.
#   STAGE1_TIME_LIMIT = None이면 기존 동작(전역 TIME_LIMIT 하나, 1단계가 다 쓰면 2단계 생략).
STAGE1_TIME_LIMIT = 100
STAGE2_TIME_LIMIT = None

# variable 모드에서 2단계(ΣCap 최소화)를 수행할지 여부.
#   True (기본) : 비용 최소화 후 ΣCap을 최소화하는 lexicographic 2단계.
#   False       : 1단계(비용)만 단일 목적으로 푼다. Cap_r은 줄이는 압력을 안 받으므로
#                 "비용만 최소화했을 때 Cap이 어디에 남는지"를 보는 대조군이 된다.
MINIMIZE_SIZING = True

# ===========================================================================
#  adaptive layout — 기간 경계에서 기계 이동(relocation) 허용
#  base_adaptive.py(w 정식화)와 Src/milp_adaptive.py(z 인코딩)가 함께 읽는다.
#  python base_adaptive.py  로 실행하면 아래 값이 그대로 쓰인다.
# ===========================================================================

# 이동 정책
#   "off"      : 위치 고정. 논문 원형과 동등 (이동 변수를 만들지 않는다)
#   "separate" : 이동이면 config 유지, 재구성이면 제자리 (동시 금지)
#   "joint"    : 이동 + 재구성 동시 허용
ADAPTIVE_MODE = "off"

# 이동비 = 구매가 C_j * (ALPHA + BETA * 거리 D_kp)
#   ALPHA : 거리와 무관한 1회 고정비 (분해·크레인·재조립). 기계값 대비 비율.
#   BETA  : 거리 1칸당 추가비. 기계값 대비 비율.
#   둘 다 0이면 이동이 공짜 -> 이득의 상한을 본다.
#   실측 손익분기는 ALPHA = 0.069 부근 (기계값의 약 7%). BETA = ALPHA/5 권장.
ALPHA = 0.0
BETA = 0.0

# 이동비를 "거리당 정액"으로 계산하고 싶을 때만 숫자를 넣는다 (ALPHA/BETA 대신 적용).
#   None  : 위의 C_j(ALPHA + BETA*D) 식을 쓴다  <- 기본
#   숫자  : 이동비 = MOVE_COST_FLAT * 거리. 기계값과 무관해진다.
MOVE_COST_FLAT = None

# (S) 강화식 — configuration 단위 기계 보존 등식.
#   새 변수 없이 s, y, w 만으로 쓰며 최적해를 자르지 않는다.
#   True 로 두면 LP relaxation이 크게 강해진다 (multi_part에서 bound 약 11% 상승).
#   논문 원형에 가깝게 보이려면 False.
SAFFAR_BALANCE_EQ = False

# w(이동), y(재구성)를 이진으로 선언할지.
#   True  : 논문 원형대로 이진 <- 기본
#   False : 연속. 모델은 가벼워지지만 정수해 보장은 별도 확인이 필요하다.
SAFFAR_W_BINARY = True

# ---- 솔버 옵션 ----
# Gurobi MIPFocus. None이면 기본값.
#   1 = 좋은 해를 빨리 찾기, 2 = 최적성 증명, 3 = bound 끌어올리기
MIP_FOCUS = None

# Gurobi 로그를 터미널에 출력할지. 1 = 출력, 0 = 조용히.
OUTPUT_FLAG = 1

# Gurobi 파라미터를 직접 넘기고 싶을 때. 예: {"Seed": 0, "Threads": 8}
GUROBI_PARAMS = {"Seed": 0}

# dummy start/end operation id. 실제 operation과 충돌하지 않게 둔다.
START_OPERATION = 0
END_OPERATION = 999
