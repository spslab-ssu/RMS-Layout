# 논문 맥락과 수식 확정 전 결정사항

## 논문 사례에서 확인된 맥락

- 계획 시작 시점에 모든 period의 demand를 알고 있으며 수요예측이 정확하다는 deterministic full-information 가정이다.
- 싱글파트 사례의 기간별 수요는 `50, 60, 80, 100`이다.
- 사례 공정경로는 `5→1→17`이다.
- 논문 해에서는 period 1에 RMT 12대를 구매하고 이후 module을 재구성한다.
- 논문의 기본 구조에서는 구매한 RMT의 물리적 위치가 기간 사이에 바뀌지 않는다.
- 비용은 RMT 구매, module add/remove를 포함한 configuration 변경, material handling으로 구성된다.

이 요약은 논문 PDF의 전체 원문을 대신하지 않는다. 최종 논문 인용·식 번호·용어는 사용자가 가진 기준 PDF와 대조해야 한다.

## 네 모델과 별도로 결정해야 하는 설계 선택

### 1. 구매와 퇴출

- 안 A: 모든 RMT는 period 1에만 구매하며 계획기간 끝까지 존재
- 안 B: period 중간 구매 허용
- 안 C: 중도 퇴출/재판매까지 허용

main의 논문 비교에는 안 A가 가장 자연스럽다. 중도 구매·퇴출을 넣으면 별도 연구 확장으로 표시한다.

### 2. operation assignment의 의미

- 한 RMT가 한 기간에 하나의 operation만 전담하는가.
- 같은 configuration으로 여러 operation의 물량을 분할 처리할 수 있는가.

현재 상태변수 `(j,l)`은 전자를 전제로 읽힌다. 후자를 원하면 상태와 생산 할당을 분리해야 한다.

### 3. relocation timing

- 이동은 period 경계에서 즉시 이뤄지고 생산 capacity 손실이 없는가.
- 이동시간/설치시간 때문에 다음 period capacity가 감소하는가.

main은 전자에 가깝다. 후자는 relocation lead time 제약이 필요한 별도 확장이다.

### 4. 재구성과 이동의 동시 수행

현재 network arc는 위치와 configuration을 한 period 경계에서 동시에 바꿀 수 있다. 물리적으로 금지하려면 “한 경계에서 이동 또는 재구성 중 하나만”이라는 arc 필터 또는 제약을 추가해야 하며 Model 2에도 동일하게 적용해야 한다.

### 5. 이동비와 material handling비

- relocation: RMT 자체를 period 사이에 이동하는 비용
- MHC: period 안에 부품/재공품이 공정 위치 사이를 이동하는 비용

두 비용은 목적과 시간축이 다르므로 합치지 않는다. 이동비가 너무 높아 이동이 선택되지 않는 것은 모델 오류가 아니라 현재 데이터에서 얻은 경제적 결론일 수 있다. 이동의 가치를 평가하려면 비용만 인위적으로 낮추기보다 수요 mix 변화, 복수 part, 병목 위치, layout 거리, 이동 제한 등을 sensitivity analysis한다.

## 권장 논문 서술 순서

1. 기준 문제와 full-information 가정
2. Model 1의 물리적 고정위치 구조
3. Model 2에서 relocation을 허용하여 feasible set을 확장
4. Model 1을 Model 3의 lifecycle network로 재수식화
5. 두 아이디어를 결합해 Model 4 도출
6. 정수 물리해 동치성과 fixed/adaptive 포함관계 제시
7. formulation별 계산성능과 adaptive의 운영가치를 서로 분리해 실험

