# 공통 표기와 데이터 해석

## 집합과 인덱스

- `P`: 실제 RMT 설치 가능 위치, `p,p' ∈ P`
- `T={1,...,H}`: 계획기간, `t ∈ T`
- `J`: 가능한 RMT configuration, `j,j' ∈ J`
- `L`: 수행 가능한 operation, `l,l' ∈ L`
- `H ⊆ J×L`: configuration-operation 가능쌍
- `A`: 제품 공정경로의 연속 operation arc 집합
- `K`: 잠재적 물리 RMT 자산 집합(Model 2에서만 명시적 label 사용)
- `p^S,p^E`: material-flow용 가상 시작·종료 위치
- `l^S,l^E`: 공정경로용 가상 시작·종료 operation

## 주요 파라미터

- `D_{pp'}`: 위치 `p,p'` 사이 거리
- `c^B_j`: configuration `j` 상태의 RMT 구매비용
- `c^R_{jj'}`: `j`에서 `j'`로 module을 추가·제거하는 재구성비용
- `B_{jl}`: configuration `j`가 operation `l`을 수행할 때 기간당 생산능력
- `d^t_{ll'}`: period `t`에 공정 arc `(l,l')`를 통과해야 하는 정확한 물량
- `h`: 단위거리·단위물량 material handling cost
- `F`: 이동 1회당 고정비
- `β`: RMT의 단위거리 relocation cost
- `M(j)`: configuration `j`의 기본 machine type
- `Q_{jj'}`: configuration `j→j'` 전이 허용 여부

main의 싱글파트 수요 파일은 기간별 `50, 60, 80, 100`을 사용한다. 논문 사례의 공정순서는 `5→1→17`로 해석된다.

## 공통 material-flow 변수

- `v_{plt} ≥ 0`: period `t`, 위치 `p`에서 operation `l`로 처리한 물량
- `f_{pl,p'l',t} ≥ 0`: `(p,l)`에서 `(p',l')`로 이동한 물량

## 공통 material-flow 제약

아래 `u_{pjlt}`는 특정 모델의 상태변수를 물리적 위치-configuration-operation 점유로 사영한 공통 기호다.

생산능력:

```math
v_{plt} \le \sum_{j:(j,l)\in H} B_{jl}u_{pjlt}
\qquad \forall p,l,t.
```

공정별 유입량과 처리량 일치:

```math
\sum_{(\bar p,\bar l)} f_{\bar p\bar l,pl,t}=v_{plt}
\qquad \forall p,l,t.
```

처리량과 유출량 일치:

```math
v_{plt}=\sum_{(\bar p,\bar l)} f_{pl,\bar p\bar l,t}
\qquad \forall p,l,t.
```

각 공정경로 arc의 수요를 정확히 만족:

```math
\sum_{p,p'} f_{pl,p'l',t}=d^t_{ll'}
\qquad \forall (l,l')\in A,\ t.
```

Material handling cost:

```math
C^{MHC}=h\sum_t\sum_{p,l,p',l'}D_{pp'}f_{pl,p'l',t}.
```

가상 시작·종료 노드와 허용 arc의 정확한 정의는 `Src/data/loader.py`를 따라야 한다.

## 중요한 해석 차이

논문은 제품-기간 수요와 operation 수행을 중심으로 식을 제시하지만, `main` 코드는 loader가 만든 route-arc demand를 위 마지막 등식으로 강제한다. 따라서 “Model 1=논문 식의 문자 그대로 복제”라고 쓰면 과도하다. 정확한 명칭은 **논문 기반 기준 MILP의 코드 구현**이다.

