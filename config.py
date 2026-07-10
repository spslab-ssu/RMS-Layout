from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "Data"

# 실행할 데이터셋을 선택한다.
# - "single_part": 메인논문 Example 1 단일부품 문제
# - "multi_part": 메인논문 Example 2 다중부품 문제
PROBLEM_NAME = "multi_part"
PROBLEM_DIR = DATA_DIR / PROBLEM_NAME

# 결과는 문제별로 나누어 저장한다. (예: Result/single_part, Result/multi_part)
RESULT_DIR = BASE_DIR / "Result" / PROBLEM_NAME

LOCATION_FILE = PROBLEM_DIR / "locations.csv"
CONFIGURATION_FILE = PROBLEM_DIR / "configurations.csv"
PRODUCTION_RATE_FILE = PROBLEM_DIR / "production_rates.csv"
DEMAND_FILE = PROBLEM_DIR / "demands.csv"
PARAMETER_FILE = PROBLEM_DIR / "parameters.csv"
# 공유 auxiliary module capacity. 파일이 없으면 제약 없이(무제한) 동작한다.
MODULE_CAPACITY_FILE = PROBLEM_DIR / "module_capacities.csv"

TIME_LIMIT = 600
MIP_GAP = 0.0

# 논문 Example에서는 같은 machine type 안에서만 configuration 변경을 허용한다.
# M1 -> M2 불가
SAME_MACHINE_RECONFIG_ONLY = True

# dummy start/end operation id. 실제 operation과 충돌하지 않게 둔다.
START_OPERATION = 0
END_OPERATION = 999
