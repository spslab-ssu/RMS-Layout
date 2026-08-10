# 동치성, 포함관계와 비교 가설

## raw 변수공간끼리는 포함관계를 말할 수 없다

Model 1의 `(x,s,y)`, Model 2의 자산 label 변수, Model 3·4의 arc 변수는 차원과 의미가 다르다. 따라서 한 모델의 원시 feasible set이 다른 모델의 원시 feasible set에 포함된다고 직접 쓰는 것은 부정확하다. 먼저 공통 물리변수 `u_{pjlt}`와 material flow `f`로 사영해야 한다.

## 목표로 하는 정수 물리해 관계

동일한 구매시점, 초기조건, 허용 configuration 전이, 위치 용량, 수요 및 비용을 가정하면:

```math
\operatorname{proj}_{u,f}(F_1)
=\operatorname{proj}_{u,f}(F_3)
\subseteq
\operatorname{proj}_{u,f}(F_2)
=\operatorname{proj}_{u,f}(F_4).
```

- `F1=F3`: 위치 고정 물리계획을 implication 변수 또는 network path로 다르게 표현한다.
- `F2=F4`: 이동 가능 물리계획을 labeled asset 또는 unlabeled path flow로 다르게 표현한다.
- 고정 위치 계획은 모든 transition에서 `p'=p`를 택하면 이동 가능 모델에서도 실현되므로 왼쪽은 오른쪽의 부분집합이다.

relocation 비용이 음수가 아니고 이동이 선택사항이라면 adaptive 최적값은 고정위치 최적값보다 나빠질 수 없다. 고정계획을 그대로 선택하면 이동비 0인 feasible solution이기 때문이다. 목적값이 더 나왔다면 time limit/gap 또는 서로 다른 제약·비용·초기조건을 먼저 의심해야 한다.

## Model 2와 4가 달라질 수 있는 대표 원인

1. Model 2는 구매한 자산이 모든 기간 반드시 존재하도록 했는데 Model 4가 중도 source/sink를 허용함.
2. 한쪽은 period 1 구매만 허용하고 다른 쪽은 중도 구매를 허용함.
3. 한쪽은 `p=p'` stay arc에 비용을 부과하거나 이동 횟수로 셈.
4. configuration 전이 가능집합 또는 machine type 일치 조건이 다름.
5. 한쪽만 shared-resource, module inventory, schedule limit를 사용함.
6. 위치 점유 제한이 “기간별”이 아니라 “최초 구매 위치별”로 잘못 적용됨.
7. 자산 label 대칭성 때문에 Model 2가 time limit 내 optimality를 증명하지 못함.

## network formulation의 장점

- 한 RMT의 기간별 상태연결이 flow conservation으로 직접 보장된다.
- 허용되지 않는 전이는 arc를 만들지 않는 방식으로 제거할 수 있다.
- implication/big-M 보조논리를 줄여 일반적으로 LP relaxation이 강해질 수 있다.
- lifecycle을 경로로 시각화하고 검사하기 쉽다.
- adaptive에서도 자산 label `k`를 생략할 수 있어 대칭성을 줄인다.

단점은 가능한 위치·상태 간 transition arc 수가 빠르게 커진다는 것이다. Model 4의 후보 arc 수는 대략 `O(|T||P|^2|H|^2)`이므로 sparse arc generation이 중요하다.

## LP relaxation에 관한 정확한 표현

`main`의 저장된 싱글파트 benchmark에서는 base와 network의 정수 목적값이 모두 `22,910`이었고, LP bound는 base `20,925.08148`, network `22,162.618038`, network+저장된 MIR 결과 `22,674.8`이었다. 최소화 문제에서 더 높은 하한은 더 강한 relaxation을 의미한다.

이는 network가 이 instance에서 더 강했다는 실증 근거다. 그러나 모든 instance에 대해 network relaxation이 base relaxation의 부분집합이라는 일반 정리는 별도의 polyhedral proof 없이 단정하지 않는다.

## 비교 실험의 권장 지표

- objective 및 purchase/reconfiguration/relocation/MHC breakdown
- RMT 구매 대수와 기간별 위치/configuration
- 이동 횟수, 총 이동거리, configuration 변경 횟수
- 변수·binary·제약 수
- root LP bound와 integrality gap
- runtime, explored nodes, incumbent gap, solver status
- Model 1↔3, Model 2↔4의 물리해 사영 일치 여부

