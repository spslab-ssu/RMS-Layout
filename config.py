from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "Data"
RESULT_DIR = BASE_DIR / "Result"

# 실행할 데이터셋을 선택한다.
# - "single_part": 메인논문 Example 1 단일부품 문제
# - "multi_part": 메인논문 Example 2 다중부품 문제
PROBLEM_NAME = "single_part"
PROBLEM_DIR = DATA_DIR / PROBLEM_NAME

LOCATION_FILE = PROBLEM_DIR / "locations.csv"
CONFIGURATION_FILE = PROBLEM_DIR / "configurations.csv"
PRODUCTION_RATE_FILE = PROBLEM_DIR / "production_rates.csv"
DEMAND_FILE = PROBLEM_DIR / "demands.csv"
PARAMETER_FILE = PROBLEM_DIR / "parameters.csv"
SHARED_RESOURCE_FILE = PROBLEM_DIR / "shared_resources.csv"
RESOURCE_REQUIREMENT_FILE = PROBLEM_DIR / "resource_requirements.csv"

TIME_LIMIT = 600
MIP_GAP = 0.0

# 논문 Figure 4 등 기존 해를 Gurobi MIP start로 넣을지 여부.
# multi_part에서 논문 해를 기준으로 시작하려면 아래 두 값을 켠다.
USE_WARM_START = False
WARM_START_DIR = PROBLEM_DIR / "warm_start_paper"

# warm start objective보다 나쁜 해를 탐색에서 제외하고 싶을 때만 사용한다.
USE_OBJECTIVE_CUTOFF = False
OBJECTIVE_CUTOFF = None

# 논문 Example에서는 같은 machine type 안에서만 configuration 변경을 허용한다.
SAME_MACHINE_RECONFIG_ONLY = True

# auxiliary module을 한정된 shared resource로 볼지 여부.
USE_SHARED_RESOURCES = False

# dummy start/end operation id. 실제 operation과 충돌하지 않게 둔다.
START_OPERATION = 0
END_OPERATION = 999
