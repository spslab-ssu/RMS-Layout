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
│   │   └── parameters.csv       # MHC, add/remove module cost 등 scalar parameter
│   └── multi_part/              # 메인논문 Example 2 다중부품 데이터
│       ├── locations.csv
│       ├── configurations.csv
│       ├── production_rates.csv
│       ├── demands.csv
│       └── parameters.csv
│
├── Src/
│   ├── __init__.py
│   ├── data.py          # ① CSV 입력 + MILP parameter 전처리
│   ├── milp.py          # ② Gurobi MILP 모델 생성 및 solve
│   ├── output.py        # ③ 해를 CSV/JSON 결과 파일로 저장
│   └── visualize.py     # ④ 결과 CSV를 layout 이미지로 시각화
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
| 모델 | `Src/milp.py` | Gurobi MILP 생성 및 solve | 구매/상태/재구성/flow 변수와 제약 정의 |
| 출력 | `Src/output.py` | 결과 CSV/JSON 저장 | 결과 schema 고정 |
| 시각화 | `Src/visualize.py` | period별 layout 이미지 생성 | Figure 2 스타일 결과 확인 |

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

---

## 6. 단일/다중부품 통합 방식

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
- stochastic demand
- robust layout
- part-specific flow tracking
- sensitivity analysis용 데이터 생성

초기에는 `Src/milp.py` 하나에서 옵션 형태로 확장합니다.  
코드가 커지고 모델 간 차이가 명확해지면 그때 `milp_adaptive.py`, `milp_shared_resource.py`처럼 분리합니다.
