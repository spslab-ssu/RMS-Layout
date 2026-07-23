# RMS Layout 연구 코드

> 이 폴더는 **RMS Layout 연구용 최적화 코드**입니다.  


---

## 1. 한눈에 보는 디렉토리 구조

```text
RMS_Layout/
├── main.py              # 진입점: 전체 단계를 순서대로 호출만 함
├── config.py            # 데이터셋 선택, solver 옵션, 공통 상수 설정
├── requirements.txt     # Python package 의존성
├── README.md            # 프로젝트 개요, 실행 방법, 구조 설명
├── SEQUENCE.md          # 실행 시퀀스와 파일별 역할 상세 설명
├── .gitignore           # Git에서 제외할 생성 파일 목록
│
├── Data/
│   ├── generate_data.py         # 논문 재현용 CSV 데이터 생성/복사
│   ├── single_part/             # 메인논문 Example 1 단일부품 데이터
│   │   ├── locations.csv        # 위치 좌표, start/end, install location 정보
│   │   ├── configurations.csv   # RMT configuration, 비용, module 정보
│   │   ├── production_rates.csv # configuration별 operation 생산률
│   │   ├── demands.csv          # part별 period demand와 operation sequence
│   │   ├── parameters.csv       # MHC, add/remove module cost 등 scalar parameter
│   │   ├── shared_resources.csv # shared resource별 보유량
│   │   └── resource_requirements.csv # configuration별 shared resource 요구 여부
│   └── multi_part/              # 메인논문 Example 2 다중부품 데이터
│       ├── locations.csv
│       ├── configurations.csv
│       ├── production_rates.csv
│       ├── demands.csv
│       ├── parameters.csv
│       ├── shared_resources.csv
│       ├── resource_requirements.csv
│       └── warm_start_paper/    # 논문 Figure 4 기반 multi-part warm start CSV
│
├── Src/
│   ├── __init__.py
│   ├── data.py          # ① CSV 입력 + MILP parameter 전처리
│   ├── milp.py          # ② Gurobi MILP 모델 생성 및 solve
│   ├── output.py        # ③ 해를 CSV/JSON 결과 파일로 저장
│   ├── warm_start.py    # ④ 기존 해 CSV를 Gurobi MIP start로 적용
│   └── visualize.py     # ⑤ 결과 CSV를 layout 이미지로 시각화
│
├── experiments/
│   └── shared_resource_sensitivity.py # shared resource capacity 민감도 분석
│
└── Result/              # 실행 결과 CSV, summary, figure 저장
```

> `Result/`는 실행할 때 생성되는 산출물입니다. GitHub에는 기본적으로 올리지 않습니다.

---

## 2. 데이터 흐름

```text
설정          데이터 입력/전처리            MILP 모델             결과 저장             시각화
config.py -> Src/data.py        ->    Src/milp.py   ->   Src/output.py  ->  Src/visualize.py
            RMSInstance              RMSSolution        Result/*.csv       Result/figures/*.png
```

각 단계는 앞 단계의 결과만 입력으로 받습니다.

예를 들어 `Src/milp.py`는 CSV 파일명을 직접 알 필요가 없습니다.  
`Src/data.py`가 CSV를 읽고 `RMSInstance` 객체를 만들어주면, 모델 코드는 그 객체의 속성만 사용합니다.

이렇게 나누면 CSV 형식이 바뀌어도 `Src/data.py`만 수정하면 되고, MILP 수식이 바뀌어도 `Src/milp.py`만 수정하면 됩니다.

---

## 3. 코드 읽는 순서

처음 코드를 보는 사람은 아래 순서대로 보면 됩니다.

1. **`README.md`**  
   전체 구조, 실행 흐름, 실행 방법을 먼저 확인합니다.

2. **`main.py`**  
   가장 먼저 볼 코드입니다.  
   `load_instance -> solve_milp -> save_solution -> draw_layouts` 순서만 보면 전체 흐름이 파악됩니다.

3. **`config.py`**  
   어떤 문제를 풀지, 어떤 데이터 폴더를 쓸지, Gurobi 옵션이 무엇인지 확인합니다.

4. **`Data/*.csv`**  
   모델의 원시 입력 데이터입니다.  
   single/multi는 같은 파일 schema를 사용합니다.

5. **`Src/data.py`**  
   CSV가 모델용 parameter로 바뀌는 과정입니다.  
   여기서 `RMSInstance`가 만들어집니다.

6. **`Src/milp.py`**  
   핵심 최적화 모델입니다.  
   변수, 제약식, 목적함수, 해 추출이 들어 있습니다.

7. **`Src/output.py`**  
   Gurobi 해가 어떤 CSV/JSON으로 저장되는지 확인합니다.

8. **`Src/visualize.py`**  
   저장된 결과를 period별 layout 그림으로 변환합니다.

---

## 4. 각 파일의 책임

| 단계 | 파일 | 책임 | 핵심 포인트 |
|---|---|---|---|
| 조립 | `main.py` | 전체 실행 순서 호출 | 계산 로직 없이 모듈만 연결 |
| 설정 | `config.py` | 데이터셋, 경로, solver 옵션 정의 | `PROBLEM_NAME`만 바꿔 single/multi 선택 |
| 입력 생성 | `Data/generate_data.py` | 논문 재현용 CSV 생성/복사 | 기존 검증 데이터를 새 구조로 이동 |
| 데이터 | `Src/data.py` | CSV 읽기 및 MILP parameter화 | `RMSInstance` 생성, single/multi 표준화 |
| 모델 | `Src/milp.py` | Gurobi MILP 생성 및 solve | 구매/상태/재구성/flow/shared resource 제약 정의 |
| 모델 | `Src/milp_network.py` | time-expanded network reformulation | 같은 문제를 machine lifecycle path로 재표현 |
| 실행 | `run_network.py` | network model 별도 실행 | `main.py`와 분리해 협업 충돌 최소화 |
| 출력 | `Src/output.py` | 결과 CSV/JSON 저장 | 결과 schema 고정 |
| Warm start | `Src/warm_start.py` | 기존 해 CSV를 Gurobi MIP start로 주입 | multi-part 논문 해 기반 warm start 선택 적용 |
| 시각화 | `Src/visualize.py` | period별 layout 이미지 생성 | Figure 2 스타일 결과 확인 |
| 실험 | `experiments/shared_resource_sensitivity.py` | shared resource 보유량 민감도 분석 | infeasible 경계와 비용 안정화 구간 확인 |

---

## 5. 입력 데이터 설명

### `locations.csv`

위치 좌표와 위치 유형을 저장합니다.

```text
location,x,y,type
1,0,0,install
...
17,-2,1.5,start
18,5,1.5,end
```

- `install`: RMT 설치 가능 위치
- `start`: inbound dummy location
- `end`: outbound dummy location

### `configurations.csv`

RMT configuration 정보입니다.

주요 컬럼:

- `machine`: machine type
- `configuration`: configuration id
- `op1` ~ `op20`: 해당 operation 생산률. 빈 칸이면 수행 불가
- `cost`: 구매비
- `basic_modules`: basic module set
- `auxiliary_modules`: auxiliary module set

### `production_rates.csv`

configuration별 operation 생산률을 long format으로 저장합니다.

```text
machine,configuration,operation,production_rate
M5,mc52,5,20
```

MILP에서는 이 파일을 주로 사용합니다.

### `demands.csv`

part별 period demand와 operation sequence를 저장합니다.

```text
part,period1,period2,period3,period4,operation_sequence
A,50,60,80,100,5>1>17
```

다중부품도 같은 형식입니다.

### `parameters.csv`

모델 scalar parameter입니다.

```text
parameter,value
period_count,4
material_handling_cost,4
start_location,17
end_location,18
add_module_cost,50
remove_module_cost,25
```

### `shared_resources.csv`

shared resource별 보유량을 저장합니다. `config.USE_SHARED_RESOURCES=True`일 때만 MILP 제약으로 사용합니다.

```text
resource,capacity
13,5
16,5
```

### `resource_requirements.csv`

각 configuration이 어떤 shared resource를 요구하는지 저장합니다.

```text
configuration,resource,amount
mc11,13,1
mc11,17,1
```

### `warm_start_paper/`

multi-part 문제에서 논문 Figure 4 기반 해를 Gurobi MIP start로 넣기 위한 CSV 묶음입니다.
`config.PROBLEM_NAME="multi_part"`와 `config.USE_WARM_START=True`로 설정하면 사용됩니다.

---

## 6. Shared Resource 민감도 분석

shared resource 보유량은 너무 작으면 infeasible이 되고, 너무 크면 resource sharing 제약이 사실상 사라집니다.
따라서 `experiments/shared_resource_sensitivity.py`로 single/multi를 같은 기준에서 반복 실행해 적정 구간을 찾습니다.

resource별 capacity를 모두 같은 값으로 두고 최소 feasible level을 찾는 기본 실행:

```bash
python3 experiments/shared_resource_sensitivity.py \
  --problems single_part multi_part \
  --mode uniform \
  --levels 0,1,2,3,4,5,6,8,10,12,15,20 \
  --time-limit 60 \
  --mip-gap 0.05
```

현재 CSV의 capacity를 기준으로 배율만 바꾸는 실행:

```bash
python3 experiments/shared_resource_sensitivity.py \
  --problems single_part multi_part \
  --mode scale \
  --levels 0.25,0.5,0.75,1.0,1.25,1.5,2.0 \
  --time-limit 60 \
  --mip-gap 0.05
```

결과는 기본적으로 `Result/sensitivity/shared_resource_sensitivity.csv`에 저장됩니다.
판단 기준은 먼저 `status_name`으로 feasible 여부를 보고, feasible 구간에서는 `objective`, `max_utilization`, `binding_resource_period_count`, `min_slack`을 함께 봅니다.

---

## 7. 단일/다중부품 통합 방식

현재 구조에서는 단일부품과 다중부품 MILP를 분리하지 않습니다.

이유는 다음과 같습니다.

- layout 위치 선택 수식은 동일합니다.
- RMT 구매, state, reconfiguration 수식은 동일합니다.
- capacity 제약도 동일합니다.
- material flow 구조도 operation arc 기준으로 보면 동일합니다.
- 차이는 part 수와 route/demand 집계 방식뿐입니다.

따라서 `Src/data.py`에서 다음과 같이 전처리합니다.

```text
part별 demand + operation sequence
        ↓
period별 route arc demand
        ↓
arc_demand[(t, left_operation, right_operation)]
```

예를 들어 단일부품은 다음 route만 있습니다.

```text
A: START -> 5 -> 1 -> 17 -> END
```

다중부품은 여러 route를 모두 arc demand로 합칩니다.

```text
A: START -> 2 -> 12 -> 17 -> END
B: START -> 2 -> 12 -> 11 -> END
C: START -> 2 -> 12 -> 11 -> 8 -> END
```

MILP는 part 개수를 직접 보지 않고, 집계된 arc demand만 사용합니다.

---

## 7. MILP 모델 개요

### 주요 변수

```text
x[p,j,l]
```

위치 `p`에 configuration `j`의 RMT를 구매하고 초기 operation `l` 상태로 두면 1.

```text
s[p,j,l,t]
```

period `t`에 위치 `p`의 RMT가 configuration `j`로 operation `l`을 수행하면 1.

```text
y[p,j_prev,j_next,l,t]
```

period `t` 시작 시 위치 `p`의 RMT가 `j_prev`에서 `j_next`로 재구성되고 operation `l`을 수행하면 1.

```text
v[p,l,t]
```

period `t`에 위치 `p`에서 operation `l`을 처리하는 총 flow.

```text
f[p,l,q,l2,t]
```

period `t`에 위치 `p`의 operation `l`에서 위치 `q`의 operation `l2`로 이동하는 material flow.

### 목적함수

```text
min 구매비 + 재구성비 + material handling cost
```

### 주요 제약

- 위치 하나에는 최대 하나의 RMT만 설치
- 구매된 RMT는 각 period에 하나의 state를 가짐
- 첫 period state는 구매 결정과 연결
- 이후 period state는 configuration 유지 또는 재구성으로만 가능
- 처리량은 configuration별 production rate 이하
- 각 RMT에서 incoming flow = processing flow = outgoing flow
- route arc별 총 flow는 demand와 같음

---

## 8. 실행 방법

상위 연구 폴더의 공용 가상환경을 사용합니다.

```bash
cd /Users/miles/Documents/02_학부연구생
source .venv/bin/activate
cd 01_RMS/03_Development/RMS_Layout
pip install -r requirements.txt
```

논문 재현 데이터를 생성/복사합니다.

```bash
python Data/generate_data.py
```

단일부품 문제를 풉니다.

```bash
python main.py
```

다중부품 문제를 풀려면 `config.py`에서 다음 값을 바꿉니다.

```python
PROBLEM_NAME = "multi_part"
```

그리고 다시 실행합니다.

```bash
python main.py
```

---

## 9. 결과 파일

실행 후 `Result/`에 다음 파일이 생성됩니다.

```text
solution_summary.json       # solver status, objective, runtime, gap
cost_breakdown.csv          # 구매비, 재구성비, MHC, 총 목적함수값
purchased_machines.csv      # 구매된 RMT와 초기 configuration/operation
machine_states.csv          # period별 위치/configuration/operation/flow
reconfigurations.csv        # period별 configuration 변경 내역
material_flows.csv          # arc별 material flow와 flow cost
figures/layout_period_1.png
figures/layout_period_2.png
figures/layout_period_3.png
figures/layout_period_4.png
figures/layout_all_periods.png
```

---

## 10. GitHub 관리 원칙

Git에 올릴 파일:

```text
main.py
config.py
requirements.txt
README.md
SEQUENCE.md
Data/*.csv
Data/generate_data.py
Src/*.py
```

Git에서 제외할 파일:

```text
Result*/
__pycache__/
.DS_Store
*.lp
*.log
*.ilp
```

`Result/`는 실행할 때 다시 만들 수 있는 산출물이므로 기본적으로 commit하지 않습니다.

---

## 11. 확장 방향

현재 기본 모델이 안정되면 다음 기능을 추가할 수 있습니다.

- adaptive layout
- shared resource
- network reformulation
- stochastic demand
- robust layout
- part-specific flow tracking
- sensitivity analysis용 데이터 생성

`network reformulation`은 문제를 바꾸는 확장이 아니라 같은 RMS layout 문제를 다른 수식으로 푸는 모델 개선입니다.  
기존 base 모델은 `python3 main.py`로 실행하고, network 모델은 `python3 run_network.py`로 별도 실행합니다.

실행 후 `Result/solution_summary.json`에는 formulation 비교용 지표가 함께 저장됩니다.

- `lp_relaxation_bound`: MIP solve 전 별도로 푼 pure LP relaxation bound
- `best_bound`: Gurobi가 최종적으로 증명한 best bound
- `mip_gap`: incumbent와 best bound의 gap
- `runtime_seconds`: solve 시간
- `node_count`: branch-and-bound node 수
- `num_vars`, `num_constraints`: 모델 크기
- `simplex_iterations`: simplex iteration 수

초기에는 `Src/milp.py`와 `Src/milp_network.py`를 분리해 두고, shared resource처럼 두 모델에 공통으로 들어가는 제약은 같은 output schema로 비교합니다.  
adaptive layout처럼 문제 자체가 바뀌는 확장은 별도 파일(`milp_adaptive.py`)로 분리하는 것이 좋습니다.
