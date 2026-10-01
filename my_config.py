# -*- coding: utf-8 -*-
"""실험 설정 — base_adaptive.py 용.

이 파일의 값만 바꾸면 된다.

실행:  python base_adaptive.py
"""
from pathlib import Path


# ===========================================================================
#  1. 데이터
# ===========================================================================
#   "youssef" : Youssef & ElMaraghy 2007   (20슬롯, 4기간, 부품 A·B)
#   "saffar"  : Saffar Example 2 다중부품   (20슬롯, 4기간, 부품 A·B·C)
#   "single"  : Saffar Example 1 단일부품
DATA = "youssef"


# ===========================================================================
#  2. 솔버
# ===========================================================================
TIME_LIMIT = 600        # 초
MIP_GAP = 0.0           # 0 이면 최적 증명까지. 0.03 이면 gap 3% 에서 멈춘다


# ===========================================================================
#  3. adaptive layout
# ===========================================================================
#   "off"      : 위치 고정 (논문 원형)
#   "separate" : 이동과 재구성을 같은 기간에 함께 하지 못함
#   "joint"    : 이동 + 재구성 동시 허용
ADAPTIVE_MODE = "off"

# 이동비 = 기계값 C_j x (ALPHA + BETA x 거리)
#   둘 다 0 이면 이동이 공짜 -> 이득의 상한을 본다
ALPHA = 0.0
BETA = 0.0


# ===========================================================================
#  아래는 위 설정에서 자동으로 만들어진다. 건드리지 않아도 된다.
# ===========================================================================
_FOLDER = {"youssef": "youssef_2007", "saffar": "multi_part", "single": "single_part"}
if DATA not in _FOLDER:
    raise ValueError("DATA 는 %s 중 하나여야 한다 (지금: %r)" % (list(_FOLDER), DATA))

BASE_DIR = Path(__file__).resolve().parent
PROBLEM_NAME = _FOLDER[DATA]
PROBLEM_DIR = BASE_DIR / "Data" / PROBLEM_NAME
RESULT_DIR = BASE_DIR / "Result" / PROBLEM_NAME

LOCATION_FILE = PROBLEM_DIR / "locations.csv"
CONFIGURATION_FILE = PROBLEM_DIR / "configurations.csv"
PRODUCTION_RATE_FILE = PROBLEM_DIR / "production_rates.csv"
DEMAND_FILE = PROBLEM_DIR / "demands.csv"
PARAMETER_FILE = PROBLEM_DIR / "parameters.csv"
SHARED_RESOURCE_FILE = PROBLEM_DIR / "shared_resources.csv"
RESOURCE_REQUIREMENT_FILE = PROBLEM_DIR / "resource_requirements.csv"
MODULE_COST_FILE = PROBLEM_DIR / "module_costs.csv"

# 더미 start/end operation id. 실제 operation 번호와 겹치지 않게 둔다.
START_OPERATION = 0
END_OPERATION = 999

# 재구성은 같은 machine type 안에서만 (논문 Example 가정)
ALLOW_RECONFIGURATION = True
SAME_MACHINE_RECONFIG_ONLY = True

# 이동비는 위의 ALPHA/BETA 식을 쓴다. 숫자를 넣으면 거리당 정액으로 바뀐다.
MOVE_COST_FLAT = None

# (S) 강화식 미사용, w·y 이진 선언 — 논문 원형에 가까운 설정
SAFFAR_BALANCE_EQ = False
SAFFAR_W_BINARY = True

# 공유자원은 쓰지 않는다
SHARED_RESOURCE_MODE = "off"
USE_SHARED_RESOURCES = False

# LP relaxation bound 를 함께 기록한다 (MIP 전에 LP 를 한 번 더 푼다)
COMPUTE_LP_RELAXATION_BOUND = True

OUTPUT_FLAG = 1                 # Gurobi 로그 표시 (0 이면 조용히)
MIP_FOCUS = None                # 1 = 해 찾기, 2 = 최적성 증명, 3 = bound
GUROBI_PARAMS = {"Seed": 0}
