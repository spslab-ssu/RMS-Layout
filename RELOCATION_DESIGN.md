# Relocation implementation note

## 기준선과 코드 경계

- `Src/milp.py`: lifecycle, coupling, material-flow 세 계층을 조립한다.
- `Src/relocation.py`: relocation에만 필요한 coupling 제약을 소유한다.
- `ENABLE_RELOCATION=False`: 기존 network+MIR와 변수 수·목적값을 회귀 재현한다.
- `archive/legacy_root/Src/`의 adaptive 구현: BR/NR 예비 비교 자료이며 새 기능을 추가하지 않는다.

## 정식화

기존 동일 위치 transition을 `(p,p,j,l,j',l',t)`로 유지하고, relocation을 켜면
`p != q`인 cross-location arc를 추가한다. 상세 transition arc는 연속변수로 두되,
물리적 machine path를 보장하기 위해 configuration 집계 transition
`a[p,q,j,j',t]`를 binary로 둔다.

```text
a[p,q,j,j',t] = sum_(l,l') z[p,q,j,l,j',l',t]
```

모든 기간에 `sum_(j,l) w[p,j,l,t] <= 1`을 강제한다. 이 점유 제약과
configuration 집계 binary가 함께 있어야 하나의 기계가 여러 전이로 분할되거나,
두 기계가 같은 위치로 합쳐지는 현상을 막을 수 있다. 이 방식은 operation 조합까지
모두 binary로 만드는 기존 adaptive 모델보다 이진변수를 줄인다.

물리 제약은 다음과 같다.

```text
capacity[p,l,t]
  = sum_j B[j,l] * w[p,j,l,t]
    - alpha * sum_(q != p,j_prev,l_prev,j) B[j,l] * z[q,p,j_prev,l_prev,j,l,t]

sum_(p != q,j,j') a[p,q,j,j',t] <= R_t

sum_(j,j') a[p,q,j,j',t] + sum_(j,j') a[q,p,j,j',t] <= 1
```

마지막 식은 2-cycle인 직접 맞교환만 금지한다. 더 긴 cycle까지 금지하려면 임시 위치를
명시하는 scheduling 확장이 필요하므로 현재 코드가 그것까지 금지한다고 해석하면 안 된다.

## Breakthrough: 무료 이동의 폭증은 가치가 아니라 퇴화다

이동비가 0이면 목적함수는 필요한 이동과 불필요한 이동을 구별하지 않는다. 따라서
`relocation_count=23` 같은 값은 "23회가 유익하다"가 아니라 같은 비용의 해 중 solver가
우연히 고른 한 해일 수 있다.

## 주 알고리즘: 정확한 2단계 사전식 최적화

체증비용은 주 알고리즘에서 사용하지 않는다. 다음 우선순위를 순차적으로 푼다.

```text
Stage 1: Z* = min C_system

Stage 2: min sum_(p != q,t) u[p,q,t]
         s.t. C_system <= Z* + epsilon
```

`C_system`에는 구매비, 재구성비, 물류비, 설정된 실제 relocation 비용이 들어간다.
Stage 1은 `LEXICOGRAPHIC_PRIMARY_MIP_GAP=0`으로 먼저 정확히 증명한다. 제한시간 내
증명하지 못하면 Stage 2를 실행하지 않으므로, 미완료 incumbent를 최적 구조라고 잘못
표현하지 않는다. `epsilon`의 기본값은 수치오차용 `1e-4`이다.

실용적인 제한시간 실험에서는 `ALLOW_PROVISIONAL_RELOCATION_AFTER_TIME_LIMIT=True`로
잠정 Stage 2를 선택할 수 있다. 이때 Stage 1 incumbent를 `Z_hat`으로 두고
`C_system <= Z_hat + epsilon` 안에서 이동을 줄인다. 이 결과는
`provisional_relocation_stage=True`, `lexicographic_optimal=False`로 기록하며, Stage 2도
시간초과라면 이동 횟수는 `best_relocation_count`일 뿐 최솟값으로 표현하지 않는다.

초기 relocation 결과는 첫 기간을 제외한 위치별 점유 제약이 누락된 모델에서
생성되었으므로 폐기한다. 특히 Example 1의 `22,514 / 5회` 결과는 정확한
물리 모델의 결과로 인용하면 안 된다. 수정 후 동일 조건의 재실험이 필요하다.

ordered crew slot 체증비용은 코드에 남아 있지만 향후 크루 초과근무 민감도 분석용이다.
주 결과의 불필요한 이동 판정에는 사용하지 않는다.

## 반드시 재확인할 연구 불일치

첨부 설계서의 Example 1은 `gamma=0`에서 VoR이 16이라고 기록하지만, 현재 정리된
network+MIR 데이터와 구현은 396을 보인다. 이 차이를 덮고 넘어가면 안 된다. 이전 결과의
`gamma`, fixed purchase, shared-resource, gap, 이동 제약 조건을 동일하게 고정한 재현
매트릭스가 다음 작업의 1순위다. 현재 값만으로 `kappa=0 => VoR=0` 명제를 주장할 수 없다.
기존 저장 결과 `archive/legacy_root/Result_adaptive_comparison/single_part/network_adaptive`도 objective
22,897에서 `TIME_LIMIT`과 1.166% gap을 기록하고 있어, 그 incumbent를 relocation 가치의
증명값으로 사용해서는 안 된다.

다운타임이 켜져도 기존 MIR/counting cut은 nominal capacity의 필요조건이므로 valid하다.
다만 moved-state의 `B(1-alpha)`를 직접 반영하지 않아 relocation-tight하지 않으며, 이
상태를 summary의 `strengthening.downtime_treatment`에 명시한다.

## 검증

- 기존 6개 baseline/DW 회귀검사 통과
- relocation 및 2단계 사전식 최적화 검사 통과
- 비용 중립 이동이 존재하는 인스턴스에서 Stage 2가 이동 0회를 선택함을 확인
- 모든 기간의 위치별 점유 제약 추가
- `main` 전체 이진 transition 모델에 수정 해를 고정했을 때 동일 objective로 feasible·optimal임을 확인
- 출력: `primary_stage`, `relocation_stage`, `minimum_relocation_count`, `relocations.csv`
