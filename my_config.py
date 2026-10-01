# -*- coding: utf-8 -*-
"""지금까지 쓴 실험 설정 기록.

실제로 코드가 읽는 설정은 config.py 다. 이 파일은 config.py 에서 덜어낸
설정들을 "무엇을 어떤 값으로 돌렸고 그래서 뭐가 나왔는지"와 함께 남겨둔
기록이다. 다시 쓸 일이 생기면 필요한 줄만 config.py 로 옮기면 된다.
(아래 값은 전부 코드의 기본값과 같거나, 기본값으로 두면 꺼지는 설정이다.
 그래서 config.py 에서 빠져도 동작이 바뀌지 않는다.)

데이터셋은 config.py 의 PROBLEM_NAME 으로 고른다.
  single_part   Saffar Example 1 단일부품
  multi_part    Saffar Example 2 다중부품 (20슬롯, 4기간, 부품 A/B/C)
  youssef_2007  Youssef & ElMaraghy 2007 (20슬롯, 4기간, 부품 A/B)
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


# ===========================================================================
#  1. adaptive layout — config.py 에 남긴 것 + 덜어낸 것
# ===========================================================================
# ADAPTIVE_MODE 의 세 번째 값. config.py 에는 off / joint 만 남겼다.
#   "separate" : 한 기간에 이동과 재구성을 동시에 못 한다 (둘 중 하나만)
ADAPTIVE_MODE = "off"

# 이동비 = 구매가 C_j * (ALPHA + BETA * 거리 D_kp)
#   ALPHA : 거리와 무관한 1회 고정비 (분해/크레인/재조립). 기계값 대비 비율
#   BETA  : 거리 1칸당 추가비. 기계값 대비 비율
#   둘 다 0이면 이동이 공짜 -> 이득의 상한(최대 몇 %까지 가능한지)을 본다
# 실측 손익분기는 ALPHA = 0.069 부근 (기계값의 약 7%), BETA = ALPHA/5 권장.
# 주의: ALPHA 를 키웠는데 이득이 되레 커지는 결과가 나오면 비수렴 artifact 다.
#       같은 해를 여러 ALPHA 에 교차대입(envelope)해서 UB(a) = min_k(N_k + a*M_k)
#       로 걸러야 한다. 안 걸렀을 때 0.01 -> 0.02 에서 92 -> 228 로 뒤집혔다.
ALPHA = 0.0
BETA = 0.0

# 이동비를 "거리당 정액"으로 계산할 때만 숫자를 넣는다 (ALPHA/BETA 대신 적용).
#   None : 위의 C_j(ALPHA + BETA*D) 식을 쓴다  <- 기본
#   숫자 : 이동비 = MOVE_COST_FLAT * 거리. 기계값과 무관해진다
MOVE_COST_FLAT = None

# (S) 강화식 — configuration 단위 기계 보존 등식. 식 (19)는 이걸 j 에 대해 합한 것.
#   새 변수 없이 s, y, w 만으로 쓰며 최적해를 자르지 않는다.
#   multi_part 에서 w 의 LP bound: 제외 30,186.3 -> 포함 33,841.7 (z 와 동일한 값)
#   600초 gap:                     제외 11.22%   -> z 는 2.30%
#   발표자료에서는 제외했다. z 모형을 쓰기로 했으므로 w 의 LP 가 약한 편이 낫다.
SAFFAR_BALANCE_EQ = False

# w(이동), y(재구성)를 이진으로 선언할지.
#   True  : 논문 원형대로 이진  <- 기본
#   False : 연속. 모델은 가벼워지지만 정수해 보장은 별도 확인이 필요하다
SAFFAR_W_BINARY = True


# ===========================================================================
#  2. 모듈 단가
# ===========================================================================
# config.py 는 PROBLEM_DIR/module_costs.csv 를 가리킨다. 파일이 없으면
# parameters.csv 의 전역 add/remove_module_cost 를 쓴다.
#   multi_part, single_part : module_costs.csv 없음 -> 전역 단가
#   youssef_2007           : module_costs.csv.off 로 꺼져 있다. 이 파일이
#                            논문의 실제 단가(add 280 / remove 140)이고,
#                            꺼진 상태에서는 전역 50/25 가 적용된다.
# z/w 비교 실험은 아래처럼 .off 를 직접 가리켜서 논문 단가로 돌렸다.
MODULE_COST_FILE = BASE_DIR / "Data" / "youssef_2007" / "module_costs.csv.off"


# ===========================================================================
#  3. 솔버 보조 설정
# ===========================================================================
# 긴 solve 를 이어받을 때 쓴다. 해를 Gurobi MIP start 로 넣는다.
#   run_one.py 가 해를 Result/run_one/<id>_<엔진>_<모드>_solution/ 에 저장한다.
#   주의: BOM 만 있는 빈 CSV 는 warm_start 파서를 깨뜨리니 지우고 넣어야 한다.
#   warm start + MIP_GAP 0.03 으로 이어 돌려서 최대 이득 4.3% 까지 봤다.
USE_WARM_START = False
WARM_START_DIR = None

# warm start objective 보다 나쁜 해를 탐색에서 아예 제외할 때만 쓴다.
USE_OBJECTIVE_CUTOFF = False
OBJECTIVE_CUTOFF = None

# Gurobi MIPFocus. None 이면 기본값.
#   1 = 좋은 해를 빨리 찾기, 2 = 최적성 증명, 3 = bound 끌어올리기
MIP_FOCUS = None

# 최소 기계대수 cut, 구매 고정. 둘 다 디버깅/대조군용.
USE_MIN_MACHINE_CUTS = False
FIXED_PURCHASES = None


# ===========================================================================
#  4. 모형 변형 (대조군용)
# ===========================================================================
# 재구성 금지. False 면 기계는 구매한 configuration 을 끝까지 유지한다.
ALLOW_RECONFIGURATION = True

# 논문 식 (2)는 부등식(위치별 상태 수 <= 구매 여부). True 면 등식(Σs = Σx)으로 강화.
# 최적값은 같고 LP relaxation 만 달라진다. 기본은 논문 원형(False).
STATE_EQUALS_PURCHASE = False

# 대안 라우트가 파트당 1개뿐이어도 λ(라우트 배분 비율) 경로로 모델을 만든다.
# λ=1 이라 결과는 같아야 한다 (동일성 확인용).
FORCE_ROUTE_LAMBDA = False

# network 모형의 arc 변수를 이진으로 둘지.
NETWORK_BINARY_ARCS = True


# ===========================================================================
#  5. 공유자원 (2026-07-24 이후 중단 — 이제 안 쓴다)
# ===========================================================================
#   "off"      : 자원 제약 없음 (기준, S1)
#   "fixed"    : shared_resources.csv 의 Cap 을 상수 상한으로 (S2)
#   "variable" : Cap_r 을 정수 결정변수로 두고 비용 최소 후 ΣCap_r 최소화 (S3)
# single_part 결과: S1/S3 = 22,910 / S2 = 24,347 (+6.3%) / S3 최소 ΣCap = 76
# variable 은 CSV 독립 + lexicographic + OPTIMAL 이라야 신뢰할 수 있다.
SHARED_RESOURCE_MODE = "off"
USE_SHARED_RESOURCES = False
SHARED_RESOURCE_FILE = None
RESOURCE_REQUIREMENT_FILE = None

# variable 모드에서 모듈별 Cap_r 상한. {모듈ID: 상한개수}, None 이면 상한 없음.
CAP_UPPER_BOUNDS = {}

# variable 모드 lexicographic 2단계의 단계별 시간(초). STAGE2 가 None 이면 TIME_LIMIT.
STAGE1_TIME_LIMIT = None
STAGE2_TIME_LIMIT = None

# variable 모드에서 2단계(ΣCap 최소화)를 할지. False 면 비용만 최소화하는 대조군.
MINIMIZE_SIZING = True


# ===========================================================================
#  6. 실험에서 알아낸 것 (자세한 내용은 아래 문서)
#     docs/experiment_results/2026-09-29_adaptive/README.md
#     docs/formulations/model_w.html, model_z.html
# ===========================================================================
# - 흐름 역전(부품들이 서로 반대 방향으로 흐름)이 이득의 필수조건이다. 최대 3.74%.
# - 위치 특화는 충돌이 있을 때만 이득을 증폭한다. 최대 6.87%.
# - c_mh, 제품군 수, 도크 형태는 거의 무효다. U자 도크가 제일 나은데도 0.7% 미만.
# - 2공정 루프는 MHC 기하 하한에 여유 0으로 딱 붙는다. 이동 이득이 구조적으로 0.
#   (Z_D, Z_E, C_LP2 세 번 재현, 전부 OPTIMAL/OPTIMAL)
# - R_layers_12 의 2.05% 는 제품 구조가 아니라 부하 불균형(280 <-> 520, 1.86배)에서
#   온다. 부하를 맞추면(W_bal12) 이득이 정확히 0 이다.
# - 20슬롯은 솔버 한계다. off 최적값은 12슬롯과 같은데(15,595) joint 가 개선을
#   못 찾는다. z 엔진으로 바꾸면 0 -> 0.76% 를 회복한다.
# - 목표였던 "20슬롯 + 다품종 + 반복 sequence + ALPHA/BETA 에서 2% 이상"은 미달.
#   최고 0.67%(F_5p_20). 2% 는 부하 불균형과 적은 슬롯 수를 요구하는데 목표 조건이
#   그 둘을 지운다. 조건이 서로 상충한다.
