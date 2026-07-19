from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "Data"
RESULT_DIR = BASE_DIR / "Result"

# 실행할 데이터셋을 선택한다.
# - "single_part": 메인논문 Example 1 단일부품 문제
# - "multi_part": 메인논문 Example 2 다중부품 문제
PROBLEM_NAME = "multi_part"
PROBLEM_DIR = DATA_DIR / PROBLEM_NAME

LOCATION_FILE = PROBLEM_DIR / "locations.csv"
CONFIGURATION_FILE = PROBLEM_DIR / "configurations.csv"
PRODUCTION_RATE_FILE = PROBLEM_DIR / "production_rates.csv"
DEMAND_FILE = PROBLEM_DIR / "demands.csv"
PARAMETER_FILE = PROBLEM_DIR / "parameters.csv"
SHARED_RESOURCE_FILE = PROBLEM_DIR / "shared_resources.csv"
RESOURCE_REQUIREMENT_FILE = PROBLEM_DIR / "resource_requirements.csv"

TIME_LIMIT = 3600
# 0.001 = 0.1% relative MIP gap
MIP_GAP = 0.001

# 논문 Example에서는 같은 machine type 안에서만 configuration 변경을 허용한다.
SAME_MACHINE_RECONFIG_ONLY = True

# 논문 Figure 4 해에서 역산한 최소 shared resource 용량을 고정 제약으로 사용한다.
USE_SHARED_RESOURCES = True

# True이면 shared_resources.csv의 capacity 값은 후보 resource 목록으로만 사용하고,
# resource별 최소 보유량을 MILP 정수 의사결정변수로 최적화한다.
# 1순위: 구매비 + 재구성비 + 물류비, 2순위: 총 shared resource 수.
OPTIMIZE_SHARED_RESOURCE_CAPACITY = False

# 선택된 멀티파트 해에서 resource별 최대 동시사용량을 CSV로 저장한다.
COUNT_SHARED_RESOURCES_AFTER_SOLVE = True

# resource 하나를 1개 줄이는 민감도 분석의 scenario별 최대 시간.
SENSITIVITY_TIME_LIMIT = 300

# 총 TIME_LIMIT 안에서 최소한 이 시간은 2단계 shared resource 수 최소화에 남긴다.
# 1단계가 일찍 끝나면 남은 시간을 모두 2단계가 사용한다.
RESOURCE_OPTIMIZATION_RESERVED_SECONDS = 120

# dummy start/end operation id. 실제 operation과 충돌하지 않게 둔다.
START_OPERATION = 0
END_OPERATION = 999
