# RMS Layout 실행 시퀀스와 파일별 역할

이 문서는 RMS Layout 코드가 어떤 순서로 실행되는지, 각 파일이 어떤 책임을 갖는지 자세히 설명합니다.

V2GRO의 README처럼, 이 문서는 **코드를 처음 보는 사람이 어떤 순서로 읽고 수정해야 하는지**를 알려주는 안내서입니다.

---

## 1. 핵심 설계 원칙

```text
main.py는 조립만 한다.
데이터 처리는 data.py가 한다.
모델 수식은 milp.py가 한다.
결과 저장은 output.py가 한다.
그림은 visualize.py가 한다.
```

즉, 한 파일이 여러 책임을 동시에 갖지 않도록 합니다.

기존 연구 코드에서 자주 생기는 문제는 하나의 긴 script 안에 다음 내용이 모두 섞이는 것입니다.

```text
CSV 읽기 + parameter 계산 + Gurobi 변수 생성 + 제약식 + 결과 저장 + 그림 생성
```

이 구조는 빠르게 실험할 때는 편하지만, 협업하거나 GitHub로 관리하기 시작하면 수정 충돌이 많아집니다.  
그래서 RMS_Layout에서는 V2GRO처럼 실행 단계를 나눕니다.

---

## 2. 전체 실행 흐름

```text
main.py
  ↓
config.py
  ↓
Src/data.py
  ↓
Src/milp.py
  ↓
Src/output.py
  ↓
Src/visualize.py
  ↓
Result/
```

더 자세히 쓰면 다음과 같습니다.

```text
config.py
  - PROBLEM_NAME = single_part / multi_part
  - 파일 경로, solver 옵션 지정

Src/data.py
  - Data/<PROBLEM_NAME>/*.csv 읽기
  - RMSInstance 생성

Src/milp.py
  - RMSInstance를 받아 Gurobi 모델 생성
  - 최적화 수행
  - RMSSolution 생성

Src/output.py
  - RMSSolution을 CSV/JSON으로 저장

Src/visualize.py
  - 저장된 CSV를 읽어서 layout figure 생성
```

---

## 3. `main.py`

### 역할

전체 실행 순서를 호출합니다.

### 책임

- 설정 모듈 import
- instance 생성 호출
- MILP solve 호출
- 결과 저장 호출
- 시각화 호출

### 하지 않는 일

- CSV 직접 읽기
- Gurobi 변수 직접 만들기
- 결과 CSV 직접 쓰기
- 그림 직접 그리기

### 코드 흐름

```python
instance = load_instance(config)
solution = solve_milp(instance, config)
save_solution(solution, config.RESULT_DIR)
draw_layouts(config.RESULT_DIR, instance)
```

이 네 줄이 전체 프로젝트의 실행 시퀀스입니다.

---

## 4. `config.py`

### 역할

실험 하나를 정의합니다.

### 주요 값

```python
PROBLEM_NAME = "single_part"
```

어떤 데이터셋을 풀지 정합니다.

```python
TIME_LIMIT = 3600
MIP_GAP = 0.0
```

Gurobi solve 옵션입니다.

```python
SAME_MACHINE_RECONFIG_ONLY = True
```

같은 machine type 안에서만 configuration 변경을 허용합니다.

```python
START_OPERATION = 0
END_OPERATION = 999
```

dummy start/end operation 번호입니다.

### 문제 전환 방법

단일부품:

```python
PROBLEM_NAME = "single_part"
```

다중부품:

```python
PROBLEM_NAME = "multi_part"
```

---

## 5. `Data/generate_data.py`

### 역할

논문 재현용 입력 CSV를 준비합니다.

현재는 기존 `implementation/data`의 검증된 CSV를 새 구조로 복사합니다.

```bash
python Data/generate_data.py
```

실행 후 다음 폴더가 채워집니다.

```text
Data/single_part/
Data/multi_part/
```

### 나중에 추가할 수 있는 기능

- random RMT configuration 생성
- random demand scenario 생성
- sensitivity analysis용 demand 배수 생성
- location 수가 다른 layout 생성
- 논문 Table 2 스타일 데이터 자동 생성

---

## 6. `Data/` CSV schema

### `locations.csv`

위치 정보를 저장합니다.

```text
location,x,y,type
1,0,0,install
17,-2,1.5,start
18,5,1.5,end
```

`type`은 다음 중 하나입니다.

```text
install
start
end
```

### `configurations.csv`

configuration 정보입니다.

주요 컬럼:

```text
machine
configuration
op1 ... op20
cost
basic_modules
auxiliary_modules
```

이 파일은 사람이 보기 좋은 wide format입니다.

### `production_rates.csv`

MILP가 실제로 쓰는 production rate 파일입니다.

```text
machine,configuration,operation,production_rate
M5,mc52,5,20
```

### `demands.csv`

part demand와 route입니다.

```text
part,period1,period2,period3,period4,operation_sequence
A,50,60,80,100,5>1>17
```

### `parameters.csv`

scalar parameter입니다.

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

## 7. `Src/data.py`

### 역할

CSV를 읽어서 MILP가 바로 사용할 수 있는 `RMSInstance`로 변환합니다.

### 주요 처리

1. `parameters.csv` 읽기
2. `locations.csv` 읽기
3. `configurations.csv` 읽기
4. `production_rates.csv` 읽기
5. `demands.csv` 읽기
6. install/start/end 위치 구분
7. feasible `(configuration, operation)` pair 생성
8. Manhattan distance 계산
9. module 차이 기반 reconfiguration cost 계산
10. part route를 route arc demand로 집계

### 중요한 설계

단일부품과 다중부품을 분리하지 않습니다.

```text
single part = part가 1개인 multi part
```

예를 들어 단일부품은 다음 route 하나만 있습니다.

```text
A: 5 -> 1 -> 17
```

이를 dummy start/end를 붙여 다음 arc로 바꿉니다.

```text
0 -> 5
5 -> 1
1 -> 17
17 -> 999
```

다중부품은 각 part의 route를 모두 arc로 바꾸고 period별 demand를 합산합니다.

최종적으로 모델은 다음 parameter만 봅니다.

```python
arc_demand[(period, left_operation, right_operation)] = required_flow
```

---

## 8. `Src/milp.py`

### 역할

Gurobi MILP 모델을 만들고 풉니다.

### 주요 변수

```text
x[p,j,l]
```

위치 `p`에 configuration `j` RMT를 구매하고 초기 operation `l`로 두면 1.

```text
s[p,j,l,t]
```

period `t`에 위치 `p`의 RMT가 configuration `j`로 operation `l`을 수행하면 1.

```text
y[p,j_prev,j_next,l,t]
```

period `t` 시작 시 위치 `p`의 RMT가 `j_prev`에서 `j_next`로 재구성되면 1.

```text
v[p,l,t]
```

위치 `p`에서 operation `l`을 처리하는 총 flow.

```text
f[p,l,q,l2,t]
```

위치 `p`의 operation `l`에서 위치 `q`의 operation `l2`로 이동하는 material flow.

### 목적함수

```text
min purchase_cost + reconfiguration_cost + material_handling_cost
```

### 주요 제약

- 위치 하나에는 최대 하나의 RMT만 설치
- 구매된 RMT는 매 period 하나의 state를 가짐
- period 1의 state는 구매 결정과 동일
- period 2 이후 state는 configuration 유지 또는 재구성으로만 가능
- operation 처리 flow는 production rate capacity 이하
- 각 RMT의 incoming flow = processing flow = outgoing flow
- route arc별 총 flow = 해당 period demand

### 결과 추출

Gurobi 변수값은 `RMSSolution` 객체로 변환됩니다.

`RMSSolution`은 다음 내용을 담습니다.

```text
summary
purchased_machines
machine_states
reconfigurations
material_flows
cost_breakdown
```

---

## 9. `Src/output.py`

### 역할

`RMSSolution`을 파일로 저장합니다.

### 생성 파일

```text
solution_summary.json
cost_breakdown.csv
purchased_machines.csv
machine_states.csv
reconfigurations.csv
material_flows.csv
```

### 설계 포인트

결과 파일 이름을 고정합니다.

그래야 `visualize.py`와 추후 분석 코드가 항상 같은 파일명을 보고 작동할 수 있습니다.

---

## 10. `Src/visualize.py`

### 역할

결과 CSV를 읽어 period별 layout 그림을 생성합니다.

### 생성 파일

```text
Result/figures/layout_period_1.png
Result/figures/layout_period_2.png
Result/figures/layout_period_3.png
Result/figures/layout_period_4.png
Result/figures/layout_all_periods.png
```

### 그림 해석

- 흰색 실선 박스: 설치되어 있고 configuration 유지 중인 RMT
- 회색 박스: 해당 period에 재구성된 RMT
- 점선 박스: 비어 있는 location
- 화살표: material flow
- 화살표 숫자: flow amount

---

## 11. 현재 검증 상태

### 단일부품

`PROBLEM_NAME = "single_part"` 기준으로 정상 실행됩니다.

확인된 결과:

```text
objective = 22910.0
gap = 0.0
```

### 다중부품

`PROBLEM_NAME = "multi_part"` 기준으로 모델 생성과 solve가 정상 작동합니다.

테스트에서는 120초 제한 내 feasible solution과 figure 생성까지 확인했습니다.  
다만 120초 제한에서는 최적성 증명까지 완료되지 않았습니다.

---

## 12. 수정할 때 기준

### 데이터 CSV 형식이 바뀌면

```text
Src/data.py 수정
```

### MILP 수식이 바뀌면

```text
Src/milp.py 수정
```

### 결과 파일 컬럼을 바꾸면

```text
Src/output.py 수정
Src/visualize.py도 같이 확인
```

### 그림 스타일을 바꾸면

```text
Src/visualize.py 수정
```

### 실험 옵션을 바꾸면

```text
config.py 수정
```

---

## 13. 확장 방향

현재 구조를 유지하면서 다음 확장을 추가할 수 있습니다.

```text
adaptive layout
shared resource
stochastic demand
robust layout
part-specific flow tracking
```

처음에는 `config.py`에 옵션을 추가하고 `Src/milp.py`에서 조건부 제약을 추가하는 방식이 단순합니다.

나중에 모델이 커지면 다음처럼 분리할 수 있습니다.

```text
Src/milp.py
Src/milp_adaptive.py
Src/milp_shared_resource.py
```
