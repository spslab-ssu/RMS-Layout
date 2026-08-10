# main 코드 매핑, 검증 근거와 경고

## 기준 스냅샷

- branch: `main`
- commit: `99e660fb8d262451cc361c72f68ff11c301d6021`
- 이 패키지 작성 시 현재 작업 브랜치를 수정하거나 checkout하지 않았다.

## 모델별 코드

| 모델 | main 파일 | 핵심 역할 |
|---|---|---|
| 1 | `Src/models/milp.py` | `x,s,y` 기반 고정위치 MILP |
| 2 | `Src/models/adaptive_shared_resource.py` | 자산 `k`, 위치상태, configuration 전이, 이동변수 기반 실험 모델 |
| 3 | `Src/models/milp_network.py` | 고정위치 time-expanded lifecycle network |
| 4 | `Src/models/network_adaptive.py` | 위치 간 transition arc를 허용한 network |

관련 실행/데이터 코드는 `main_source_snapshot.zip`에 보존했다.

## 소스 읽기 포인트

### Model 1: `Src/models/milp.py`

- `solve`: 약 28행
- `x/s/y` key 구성: 약 43–52행
- 위치당 한 RMT와 초기상태: 약 91–104행
- configuration transition: 약 106–135행
- capacity/material flow: 약 143–181행
- 목적함수: 약 183–194행

### Model 2: `Src/models/adaptive_shared_resource.py`

- asset set과 buy: 약 93–107행
- `s,z,g,y,move`: 약 116–144행
- 자산/위치 점유 및 연결: 약 155–195행
- configuration/position transition: 약 213–238행
- capacity/material flow: 약 240행 이후
- shared-resource 등 선택 확장: 약 290행 이후
- 목적함수: 약 326–353행

### Model 3: `Src/models/milp_network.py`

- node와 arc 집합: 약 50–62행
- 목적함수: 약 74–84행
- transition arc 생성: 약 112행 이후
- 위치별 path와 node balance: 약 160–193행

### Model 4: `Src/models/network_adaptive.py`

- node: 약 51행
- relocation cost: 약 80–87행
- 위치 간 transition arc 생성: 약 124행 이후
- 초기 구매/기간별 위치 점유: 약 181–189행
- node balance: 약 213–214행

행 번호는 스냅샷의 탐색용 근사값이며 최종 인용 전 원문 확인이 필요하다.

## 기존 검증 결과

`RMS_Network_Reformulation/results/comparison/single_part/seed_1/formulation_comparison.json`에 저장된 결과:

| formulation | objective | LP relaxation | binaries | variables | constraints | runtime(s) |
|---|---:|---:|---:|---:|---:|---:|
| base | 22,910 | 20,925.08148 | 1,856 | 4,096 | 3,136 | 6.506 |
| network | 22,910 | 22,162.618038 | 832 | 4,944 | 1,856 | 2.338 |
| network_mir | 22,910 | 22,674.8 | 832 | 미기록 | 1,892 | 0.904 |

이 결과는 Model 1과 3의 정수 목적값 일치 및 해당 instance에서 network 계산구조의 개선을 뒷받침한다.

## 반드시 경고할 사항

1. **논문값과 코드값 불일치**: 논문 사례 총비용은 `23,082`로 보고되지만 저장된 기준 코드의 exact optimum은 `22,910`이다(구매 `11,025`, 재구성 `1,925`, MHC `9,960`). 단순히 “alternative optimum”이라고 부를 수 없고 데이터·거리·flow·비용 정의의 차이를 추적해야 한다.
2. **Model 2의 위상**: `adaptive_shared_resource.py`는 기본 entrypoint에 연결된 순수 “paper+adaptive” 구현이 아니다. relocation 외의 확장도 포함한다. 논문 비교용 Model 2는 core constraint를 별도 명시해야 한다.
3. **Adaptive 검증 공백**: main 스냅샷에는 Model 2↔4 동치성을 수치로 검증한 committed regression result가 없다.
4. **MIR 재현성 공백**: 결과 파일에는 `network_mir`가 있지만 현재 스냅샷 소스에서 대응하는 MIR/counting/theta 구현을 찾기 어렵다. 결과 생성 코드나 이전 commit을 확인해야 한다.
5. **config 설명 불일치 가능성**: relocation cost 관련 주석과 실제 기본 숫자의 상대 크기가 일치하는지 재검토해야 한다.
6. **full-information 가정**: 네 모델은 전체 기간 수요를 알고 동시에 푸는 것이 기본이다. online/myopic 실험 결과를 같은 표에 넣을 때 정보구조 차이를 별도 열로 표시해야 한다.

## 후속 검증 테스트

1. relocation을 금지(`p'=p`만 허용)했을 때 Model 4 objective가 Model 3와 정확히 일치하는가.
2. relocation cost를 충분히 크게 했을 때 Model 4가 Model 3의 물리해로 돌아오는가.
3. Model 2와 4에 동일한 pure-adaptive 제약만 남기고 objective와 period별 `u`를 비교하는가.
4. 임의의 작은 instance를 exhaustive enumeration으로 풀어 두 formulation의 정수 물리해 집합을 비교하는가.
5. solver time limit을 해제하거나 충분히 늘리고 status가 `OPTIMAL`인지 확인하는가.

