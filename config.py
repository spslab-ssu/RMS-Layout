from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "Data"

LOCATION_DIR = DATA_DIR / "locations"
RMT_TABLE_DIR = DATA_DIR / "rmt_tables"
PARAMETER_DIR = DATA_DIR / "parameters"
DEMAND_DIR = DATA_DIR / "demands"
SHARED_RESOURCE_DIR = DATA_DIR / "shared_resources"
WARM_START_BASE_DIR = DATA_DIR / "warm_starts"

# 실행할 문제와 입력 조합을 선택한다.
# - PROBLEM_TYPE: "single_part" / "multi_part"
# - LOCATION_NAME: "layout_18" / "layout_22"
# - RMT_TABLE_NAME: "table_1" / "table_2"
# - DEMAND_NAME: "demand_1" / "demand_2" / ...
PROBLEM_TYPE = "single_part"
LOCATION_NAME = "layout_22"
RMT_TABLE_NAME = "table_2"
DEMAND_NAME = "demand_2"
PARAMETER_NAME = PROBLEM_TYPE
SHARED_RESOURCE_NAME = "shared_resources_2"
RESOURCE_CAPACITY_NAME = "resource_capacities_2"

# 기존 코드 호환용 이름. 내부 모델에서는 problem_name으로 사용한다.
PROBLEM_NAME = PROBLEM_TYPE

RESULT_DIR = BASE_DIR / "Result" / PROBLEM_TYPE / RMT_TABLE_NAME / DEMAND_NAME

LOCATION_FILE = LOCATION_DIR / f"{LOCATION_NAME}.csv"
CONFIGURATION_FILE = RMT_TABLE_DIR / RMT_TABLE_NAME / "configurations.csv"
PRODUCTION_RATE_FILE = RMT_TABLE_DIR / RMT_TABLE_NAME / "production_rates.csv"
DEMAND_FILE = DEMAND_DIR / PROBLEM_TYPE / f"{DEMAND_NAME}.csv"
PARAMETER_FILE = PARAMETER_DIR / f"{PARAMETER_NAME}.csv"
SHARED_RESOURCE_FILE = SHARED_RESOURCE_DIR / f"{SHARED_RESOURCE_NAME}.csv"
RESOURCE_CAPACITY_FILE = SHARED_RESOURCE_DIR / f"{RESOURCE_CAPACITY_NAME}.csv"
RESOURCE_REQUIREMENT_FILE = RMT_TABLE_DIR / RMT_TABLE_NAME / "resource_requirements.csv"

TIME_LIMIT = 100
MIP_GAP = 0.0

# formulation 비교용 pure LP relaxation bound를 기록할지 여부.
# True이면 MIP solve 전에 LP relaxation을 한 번 더 풀기 때문에 실행시간이 추가된다.
COMPUTE_LP_RELAXATION_BOUND = True

# 논문 Figure 4 등 기존 해를 Gurobi MIP start로 넣을지 여부.
# multi_part에서 논문 해를 기준으로 시작하려면 아래 두 값을 켠다.
USE_WARM_START = False
WARM_START_NAME = "paper_table_1"
WARM_START_DIR = WARM_START_BASE_DIR / PROBLEM_TYPE / WARM_START_NAME

# warm start objective보다 나쁜 해를 탐색에서 제외하고 싶을 때만 사용한다.
USE_OBJECTIVE_CUTOFF = False
OBJECTIVE_CUTOFF = None

# 논문 Example에서는 같은 machine type 안에서만 configuration 변경을 허용한다.
# M1 -> M2 불가
SAME_MACHINE_RECONFIG_ONLY = True

# auxiliary module을 한정된 shared resource로 볼지 여부.
USE_SHARED_RESOURCES = False

# dummy start/end operation id. 실제 operation과 충돌하지 않게 둔다.
START_OPERATION = 0
END_OPERATION = 999
