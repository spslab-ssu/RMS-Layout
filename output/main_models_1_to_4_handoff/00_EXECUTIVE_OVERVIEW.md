# Executive overview

## 연구 질문

논문의 싱글파트 RMS 설계 문제를 기준으로, (a) RMT 위치를 기간 사이에 이동할 수 있게 운영 유연성을 추가하고, (b) 같은 물리 문제를 시간확장 network flow로 다시 표현했을 때 모델 구조와 계산 성능이 어떻게 달라지는지를 비교한다.

## 두 개의 독립된 축

네 모델은 사실 두 축의 조합이다.

| 축 | 선택 A | 선택 B | 바뀌는 것 |
|---|---|---|---|
| 운영정책 | 위치 고정 | 위치 이동 허용(adaptive) | 물리적으로 가능한 계획 |
| 수식 표현 | implication/state MILP | time-expanded network | 같은 계획을 표현하는 변수와 LP relaxation |

따라서:

| 모델 | 운영정책 | 수식 표현 |
|---|---|---|
| 1. 논문/기준 | 고정 | implication/state MILP |
| 2. 논문 + adaptive | 이동 허용 | 자산 식별 기반 MILP |
| 3. network | 고정 | 위치별 시간확장 경로 |
| 4. network + adaptive | 이동 허용 | 위치 간 시간확장 경로 |

## 무엇이 진짜 새 아이디어인가

1. **Adaptive relocation**: 기간 `t-1`에 위치 `p`에 있던 동일 RMT가 기간 `t`에 `p'`로 이동할 수 있게 한다. 이때 이동변수와 거리비용이 추가된다. 이것은 feasible set을 확대하는 운영 아이디어다.
2. **Network reformulation**: 구매, 구성 상태, 구성변경을 source-node-transition-sink의 경로로 표현한다. 운영 능력 자체를 확대하지 않지만, 중복 변수와 약한 implication을 줄여 계산을 개선할 수 있다.
3. **공통 material-flow layer**: 네 모델 모두 위치별 생산능력과 공정경로 수요를 연결한다. 네 모델 비교에서 이 층은 가능하면 동일하게 유지해야 공정한 비교가 된다.

## 논문 가정과 online/myopic은 별개의 축

논문과 `main`의 네 모델은 기본적으로 전체 기간 수요를 알고 한 번에 최적화하는 deterministic full-information 모델이다. 기간별로 현재 수요만 공개하고 매번 다시 푸는 online/myopic 방식은 정보구조가 다른 다섯 번째 실험축이다. 이를 네 모델의 adaptive relocation과 혼동하면 안 된다.

## 반드시 보존할 공정한 비교 조건

- 동일한 기간, 위치, configuration, 공정경로, 수요, capacity를 사용한다.
- 구매·모듈 추가/제거·물류비의 정의를 동일하게 사용한다.
- Model 2와 4에는 동일한 relocation cost와 동일한 이동 허용집합을 사용한다.
- 구매는 period 1에만 가능한지, 이후에도 가능한지를 명시하고 동일하게 맞춘다.
- 한 위치에 한 대만 허용하는지와 한 자산이 한 기간에 한 위치만 점유하는지를 동일하게 맞춘다.
- 최적 목적값뿐 아니라 solver status, gap, time limit, 해의 물리적 상태를 같이 비교한다.

