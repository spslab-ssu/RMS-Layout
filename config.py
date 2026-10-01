from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "Data"

# 실행할 데이터셋을 선택한다. Data/ 아래 폴더명이다.
# - "single_part"  : 메인논문 Example 1 단일부품 문제
# - "multi_part"   : 메인논문 Example 2 다중부품 문제 (20슬롯, 4기간)
# - "youssef_2007" : Youssef & ElMaraghy 2007 데이터 (20슬롯, 4기간)
PROBLEM_NAME = "multi_part"
PROBLEM_DIR = DATA_DIR / PROBLEM_NAME

TIME_LIMIT = 600
MIP_GAP = 0.0

# adaptive layout: 기간 경계에서 기계 relocation(이동) 허용 정책. (milp_adaptive에서 사용)
#   "off"      : 위치 고정 (base와 동등)
#   "joint"    : 이동 + 재구성 동시 허용
ADAPTIVE_MODE = "off"
# 이동비 = 구매가 C_j * (ALPHA + BETA * 거리 D_kp)
ALPHA = 0.0
BETA = 0.0


# ===========================================================================
#  아래는 위 설정에서 자동으로 만들어진다. 건드리지 않아도 된다.
# ===========================================================================
# 결과는 문제별로 나누어 저장한다. (예: Result/single_part, Result/multi_part)
RESULT_DIR = BASE_DIR / "Result" / PROBLEM_NAME

LOCATION_FILE = PROBLEM_DIR / "locations.csv"
CONFIGURATION_FILE = PROBLEM_DIR / "configurations.csv"
PRODUCTION_RATE_FILE = PROBLEM_DIR / "production_rates.csv"
DEMAND_FILE = PROBLEM_DIR / "demands.csv"
PARAMETER_FILE = PROBLEM_DIR / "parameters.csv"
# module별 재구성 단가 파일 (선택). 파일이 있으면 재구성비를 module별 단가로 계산하고,
# 없으면 parameters.csv의 전역 add/remove_module_cost를 사용한다.
MODULE_COST_FILE = PROBLEM_DIR / "module_costs.csv"

# dummy start/end operation id. 실제 operation과 충돌하지 않게 둔다.
START_OPERATION = 0
END_OPERATION = 999

# 재구성은 같은 machine type 안에서만 허용한다. (논문 Example 가정, M1 -> M2 불가)
SAME_MACHINE_RECONFIG_ONLY = True

# 공유자원(shared resource)은 쓰지 않는다.
SHARED_RESOURCE_MODE = "off"

# LP relaxation bound를 함께 기록한다. (MIP 전에 LP를 한 번 더 푸는 시간이 추가된다)
COMPUTE_LP_RELAXATION_BOUND = True

OUTPUT_FLAG = 1                 # Gurobi 로그 출력. 0이면 조용히
GUROBI_PARAMS = {"Seed": 0}     # 재현성을 위해 seed 고정
