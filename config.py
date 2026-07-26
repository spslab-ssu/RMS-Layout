from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "Data"

# 실행할 데이터셋을 선택한다.
# - "single_part": 메인논문 Example 1 단일부품 문제
# - "multi_part": 메인논문 Example 2 다중부품 문제
PROBLEM_NAME = "single_part"
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

# adaptive layout: 기간 경계에서 기계 relocation(이동) 허용 정책. (milp_adaptive에서 사용)
#   "off"      : 위치 고정 (base와 동등)
#   "separate" : 이동이면 config 유지, 재구성이면 제자리 (동시 금지)
#   "joint"    : 이동 + 재구성 동시 허용
ADAPTIVE_MODE = "off"
# 이동비 = 구매가 C_j * (ALPHA + BETA * 거리 D_kp)
ALPHA = 0.0
BETA = 0.0

# dummy start/end operation id. 실제 operation과 충돌하지 않게 둔다.
START_OPERATION = 0
END_OPERATION = 999
