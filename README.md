# RMS Layout 연구 코드

> 이 폴더는 **RMS Layout 연구용 최적화 코드**입니다.  


---

## 1. 한눈에 보는 디렉토리 구조

```text
RMS-Layout/
├── main.py              # base MILP 실행 진입점
├── run_network.py       # time-expanded network model 실행 진입점
├── run_network_adaptive.py # full adaptive network model 실행 진입점
├── config.py            # 입력 조합과 solver 옵션 설정
├── README.md
├── SEQUENCE.md
│
├── Data/
│   ├── generate_data.py
│   ├── locations/               # layout 좌표만 관리
│   │   ├── layout_18.csv
│   │   ├── layout_22.csv
│   │   ├── layout_23_3x7.csv
│   │   ├── layout_26.csv
│   │   └── layout_30.csv
│   ├── rmt_tables/              # RMT configuration table만 관리
│   │   ├── table_1/
│   │   │   ├── configurations.csv
│   │   │   ├── production_rates.csv
│   │   │   └── resource_requirements.csv
│   │   ├── table_2/
│   │   │   ├── configurations.csv
│   │   │   ├── production_rates.csv
│   │   │   └── resource_requirements.csv
│   │   └── table_3/
│   │       ├── configurations.csv
│   │       ├── production_rates.csv
│   │       └── resource_requirements.csv
│   ├── parameters/              # single/multi 공통 모델 파라미터
│   │   ├── single_part.csv
│   │   └── multi_part.csv
│   ├── demands/                 # 문제 유형별 demand scenario
│   │   ├── single_part/
│   │   │   ├── demand_1.csv
│   │   │   └── demand_2.csv
│   │   └── multi_part/
│   │       └── demand_1.csv
│   ├── shared_resources/        # shared resource 보유량
│   │   ├── shared_resources_1.csv
│   │   ├── resource_capacities_1.csv
│   │   ├── shared_resources_2.csv
│   │   └── resource_capacities_2.csv
│   └── warm_starts/
│       └── multi_part/paper_table_1/
│
├── Src/
│   ├── data/loader.py
│   ├── models/milp.py
│   ├── models/milp_network.py
│   ├── models/network_adaptive.py
│   ├── models/adaptive_shared_resource.py
│   ├── io/output.py
│   ├── viz/visualize.py
│   └── warm_start/mip_start.py
│
├── experiments/
└── Result/                       # 실행 결과. GitHub 제외
```

> `Result/`, `__pycache__/`, `.DS_Store`는 생성 산출물이므로 GitHub에는 올리지 않습니다.

실행 결과는 모델별로 분리해서 저장합니다. 같은 `table/demand` 조합을 여러 모델로 풀어도 CSV가 서로 덮어쓰이지 않습니다.

```text
Result/<problem_type>/<rmt_table>/<demand>/base/
Result/<problem_type>/<rmt_table>/<demand>/network/
Result/<problem_type>/<rmt_table>/<demand>/network_adaptive/
```

`solution_summary.json`의 `cost_consistency.difference`가 `0.0`이면 `cost_breakdown.csv`, `material_flows.csv`, `reconfigurations.csv`, `purchased_machines.csv`의 비용 합계가 objective와 일치한다는 뜻입니다.

## 2. 데이터 흐름

```text
설정          데이터 입력/전처리            MILP 모델             결과 저장             시각화
config.py -> Src/data/loader.py  ->  Src/models/milp.py  ->  Src/io/output.py  ->  Src/viz/visualize.py
            RMSInstance              RMSSolution        Result/<model>/*.csv  Result/<model>/figures/*.png
```

각 단계는 앞 단계의 결과만 입력으로 받습니다.

예를 들어 `Src/models/milp.py`는 CSV 파일명을 직접 알 필요가 없습니다.  
`Src/data/loader.py`가 CSV를 읽고 `RMSInstance` 객체를 만들어주면, 모델 코드는 그 객체의 속성만 사용합니다.

이렇게 나누면 CSV 형식이 바뀌어도 `Src/data/loader.py`만 수정하면 되고, MILP 수식이 바뀌어도 `Src/models/milp.py`만 수정하면 됩니다.

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

4. **`Data/locations`, `Data/rmt_tables`, `Data/demands`, `Data/parameters`, `Data/shared_resources`**  
   모델의 원시 입력 데이터입니다.  
   dataset은 문제별 schema를 공유하고, RMT table은 `Data/rmt_tables`에서 공통으로 사용합니다.

5. **`Src/data/loader.py`**  
   CSV가 모델용 parameter로 바뀌는 과정입니다.  
   여기서 `RMSInstance`가 만들어집니다.

6. **`Src/models/milp.py`**  
   핵심 최적화 모델입니다.  
   변수, 제약식, 목적함수, 해 추출이 들어 있습니다.

7. **`Src/io/output.py`**  
   Gurobi 해가 어떤 CSV/JSON으로 저장되는지 확인합니다.

8. **`Src/viz/visualize.py`**  
   저장된 결과를 period별 layout 그림으로 변환합니다.

---

## 4. 각 파일의 책임

| 단계 | 파일 | 책임 | 핵심 포인트 |
|---|---|---|---|
| 조립 | `main.py` | 전체 실행 순서 호출 | 계산 로직 없이 모듈만 연결 |
| 설정 | `config.py` | 데이터셋, 경로, solver 옵션 정의 | `PROBLEM_TYPE`, `LOCATION_NAME`, `RMT_TABLE_NAME`, `DEMAND_NAME`으로 입력 조합 선택 |
| 입력 생성 | `Data/generate_data.py` | 논문 재현용 CSV 생성/복사 | 기존 검증 데이터를 새 구조로 이동 |
| 데이터 | `Src/data/loader.py` | CSV 읽기 및 MILP parameter화 | `RMSInstance` 생성, single/multi 표준화 |
| 모델 | `Src/models/milp.py` | Gurobi MILP 생성 및 solve | 구매/상태/재구성/flow/shared resource 제약 정의 |
| 모델 | `Src/models/milp_network.py` | time-expanded network reformulation | 같은 문제를 machine lifecycle path로 재표현 |
| 모델 | `Src/models/network_adaptive.py` | full adaptive network model | period 사이 RMT location 이동 허용 |
| 실행 | `run_network.py` | network model 별도 실행 | `main.py`와 분리해 협업 충돌 최소화 |
| 출력 | `Src/io/output.py` | 결과 CSV/JSON 저장 | 결과 schema 고정 |
| Warm start | `Src/warm_start/mip_start.py` | 기존 해 CSV를 Gurobi MIP start로 주입 | multi-part 논문 해 기반 warm start 선택 적용 |
| 시각화 | `Src/viz/visualize.py` | period별 layout 이미지 생성 | Figure 2 스타일 결과 확인 |
| 실험 | `experiments/shared_resource_sensitivity.py` | shared resource 보유량 민감도 분석 | infeasible 경계와 비용 안정화 구간 확인 |

---

## 5. 입력 데이터 설명

### 데이터 번호

현재 데이터는 논문명 대신 번호로 관리합니다.

- `1`: 메인논문 데이터. `single_part`, `multi_part` 문제를 포함합니다.
- `2`: `papers/layout/메인논문/유사 데이터 table` 기반 신규 데이터. 현재는 `single_part` 예제를 포함합니다.
- `3`: 유사 데이터 `table 2_1`, `table 2_2`를 메인논문 Table 2 형식으로 정리한 RMT table입니다.

`config.py`에서 `PROBLEM_TYPE`, `LOCATION_NAME`, `RMT_TABLE_NAME`, `DEMAND_NAME`을 바꾸면 실행할 입력 조합을 선택할 수 있습니다.

### `Data/locations/<location_name>.csv`

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

### `Data/rmt_tables/<rmt_table_name>/configurations.csv`

RMT configuration 정보입니다. single/multi 데이터셋에 중복 저장하지 않고 공통 table로 사용합니다.

주요 컬럼:

- `machine`: machine type
- `configuration`: configuration id
- `op1` ~ `op20`: 해당 operation 생산률. 빈 칸이면 수행 불가
- `cost`: 구매비
- `basic_modules`: basic module set
- `auxiliary_modules`: auxiliary module set

### `Data/rmt_tables/<rmt_table_name>/production_rates.csv`

configuration별 operation 생산률을 long format으로 저장합니다.

```text
machine,configuration,operation,production_rate
M5,mc52,5,20
```

MILP에서는 이 파일을 주로 사용합니다.

### `Data/demands/<problem_type>/<demand_name>.csv`

part별 period demand와 operation sequence를 저장합니다.

```text
part,period1,period2,period3,period4,operation_sequence
A,50,60,80,100,5>1>17
```

다중부품도 같은 형식입니다.

### `Data/parameters/<problem_type>.csv`

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

### `Data/shared_resources/<shared_resource_name>.csv`

shared resource별 보유량을 저장합니다. `config.USE_SHARED_RESOURCES=True`일 때만 MILP 제약으로 사용합니다.

```text
resource,capacity
13,5
16,5
```

### `Data/rmt_tables/<rmt_table_name>/resource_requirements.csv`

각 configuration이 어떤 shared resource를 요구하는지 저장합니다.

```text
configuration,resource,amount
mc11,13,1
mc11,17,1
```

### `warm_start_paper/`

multi-part 문제에서 논문 Figure 4 기반 해를 Gurobi MIP start로 넣기 위한 CSV 묶음입니다.
`config.PROBLEM_TYPE="multi_part"`, `config.RMT_TABLE_NAME="table_1"`, `config.USE_WARM_START=True`와 `config.USE_WARM_START=True`로 설정하면 사용됩니다.

---

## 6. Shared Resource 민감도 분석

shared resource 보유량은 너무 작으면 infeasible이 되고, 너무 크면 resource sharing 제약이 사실상 사라집니다.
따라서 `experiments/shared_resource_sensitivity.py`로 single/multi를 같은 기준에서 반복 실행해 적정 구간을 찾습니다.

resource별 capacity를 모두 같은 값으로 두고 최소 feasible level을 찾는 기본 실행:

```bash
python3 experiments/shared_resource_sensitivity.py \
  --location-name layout_18 \
  --rmt-table-name table_1 \
  --demand-name demand_1 \
  --shared-resource-name shared_resources_1 \
  --problems single_part multi_part \
  --mode uniform \
  --levels 0,1,2,3,4,5,6,8,10,12,15,20 \
  --time-limit 60 \
  --mip-gap 0.05
```

현재 CSV의 capacity를 기준으로 배율만 바꾸는 실행:

```bash
python3 experiments/shared_resource_sensitivity.py \
  --location-name layout_18 \
  --rmt-table-name table_1 \
  --demand-name demand_1 \
  --shared-resource-name shared_resources_1 \
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

따라서 `Src/data/loader.py`에서 다음과 같이 전처리합니다.

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
cd 01_RMS/03_Development/RMS-Layout
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
PROBLEM_TYPE = "multi_part"
LOCATION_NAME = "layout_22"
RMT_TABLE_NAME = "table_1"
DEMAND_NAME = "demand_1"
```

그리고 다시 실행합니다.

```bash
python main.py
```

---


### Full adaptive network model

`run_network_adaptive.py`는 period 사이 RMT relocation을 허용하는 network model을 실행합니다. 이동 비용은 거리 기반으로 계산합니다.

```python
RELOCATION_COST_PER_DISTANCE = 100.0
RELOCATION_FIXED_COST = 0.0
MAX_RELOCATION_DISTANCE = None
```

`MAX_RELOCATION_DISTANCE = None`이면 모든 위치 이동을 허용하는 full adaptive model입니다. 숫자를 넣으면 period 사이 relocation arc 중 Manhattan distance가 해당 값 이하인 이동만 허용합니다.

```python
MAX_RELOCATION_DISTANCE = 2
```

목적함수에는 기존 구매비, 재구성비, MHC에 `relocation_cost`가 추가됩니다. 결과는 `cost_breakdown.csv`, `cost_by_period.csv`, `cost_detail.csv`에서 확인할 수 있습니다.

거리 제한 민감도 분석은 기존 relocation cost sensitivity 스크립트에 `--distance-limits`를 추가해서 실행합니다.

```bash
python3 experiments/relocation_cost_sensitivity.py \
  --problems single_part \
  --location-name layout_30 \
  --levels 1,10,30 \
  --distance-limits none,0,1,2,3,4 \
  --time-limit 60 \
  --mip-gap 0.05 \
  --output Result/sensitivity/relocation_distance_limit_sensitivity.csv
```

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
Data/locations, Data/rmt_tables, Data/demands, Data/parameters, Data/shared_resources
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

초기에는 `Src/models/milp.py`와 `Src/models/milp_network.py`를 분리해 두고, shared resource처럼 두 모델에 공통으로 들어가는 제약은 같은 output schema로 비교합니다.  
adaptive layout처럼 문제 자체가 바뀌는 확장은 별도 파일(`Src/models/adaptive_shared_resource.py`)로 분리하는 것이 좋습니다.
