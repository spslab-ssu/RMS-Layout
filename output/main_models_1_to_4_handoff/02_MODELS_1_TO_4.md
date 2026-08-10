# 모델 1~4의 수식 구조

이 문서는 논문 제출용 최종 notation을 확정하기 전의 통합 수식 명세다. 공통 material-flow 식은 `01_COMMON_NOTATION_AND_DATA.md`를 따른다.

## Model 1 — 논문 기반 기준 MILP: 위치 고정

### 변수

- `x_{pjl}∈{0,1}`: 위치 `p`에 최초 구매한 RMT의 초기 `(j,l)` 상태
- `s_{pjlt}∈{0,1}`: period `t`에 위치 `p`가 `(j,l)` 상태
- `y_{pj'jlt}∈{0,1}`: 같은 위치의 RMT가 `t-1`의 configuration `j'`에서 `t`의 `j`로 바뀌어 operation `l`을 담당

### 핵심 제약

한 위치에 최대 한 대:

```math
\sum_{(j,l)\in H}x_{pjl}\le1 \qquad \forall p.
```

초기상태 연결:

```math
s_{pjl1}=x_{pjl} \qquad \forall p,(j,l)\in H.
```

상태 전이의 논리적 연결은 코드상 `y` implication으로 구현된다. 논문용으로는 다음과 같은 표준 선형화를 권장한다.

```math
y_{pj'jlt}\le \sum_{\bar l:(j',\bar l)\in H}s_{pj'\bar l,t-1},
```

```math
y_{pj'jlt}\le s_{pjlt},
```

```math
y_{pj'jlt}\ge
\sum_{\bar l:(j',\bar l)\in H}s_{pj'\bar l,t-1}+s_{pjlt}-1.
```

허용되지 않는 machine type 전이는 `Q_{j'j}=0`으로 차단한다. 상태 지속/전이는 각 위치별로 보존되어 RMT의 위치 `p`는 바뀌지 않는다.

### 목적함수

```math
\min
\sum_{p,j,l}c^B_jx_{pjl}
+\sum_{p,t\ge2,j',j,l}c^R_{j'j}y_{pj'jlt}
+C^{MHC}.
```

논문에서 “removal cost”는 RMT 폐기비가 아니라 configuration에서 module을 제거하는 재구성비에 포함된다.

---

## Model 2 — 논문형 MILP + adaptive relocation

위치가 바뀌어도 동일 물리 RMT임을 추적해야 하므로 자산 index `k`가 필요하다.

### 변수

- `b_k∈{0,1}`: 잠재 자산 `k` 구매 여부
- `s_{kpjlt}∈{0,1}`: 자산 `k`가 `t`에 위치 `p`, 상태 `(j,l)`
- `z_{kpt}∈{0,1}`: 자산 `k`가 `t`에 위치 `p`
- `g_{kjt}∈{0,1}`: 자산 `k`가 `t`에 configuration `j`
- `y_{kjj't}∈{0,1}`: 자산 `k`의 configuration 전이 `j→j'`
- `m_{kpp't}∈{0,1}`: 자산 `k`의 위치 전이 `p→p'`

### 상태와 위치

구매한 자산은 매 기간 정확히 한 상태를 가진다고 가정할 경우:

```math
\sum_{p,(j,l)\in H}s_{kpjlt}=b_k
\qquad \forall k,t.
```

한 위치에는 한 기간에 최대 한 자산:

```math
\sum_{k,(j,l)\in H}s_{kpjlt}\le1
\qquad \forall p,t.
```

보조변수 연결:

```math
z_{kpt}=\sum_{(j,l)\in H}s_{kpjlt},
\qquad
g_{kjt}=\sum_{p,l:(j,l)\in H}s_{kpjlt}.
```

### configuration 전이

```math
y_{kjj't}\le g_{kj,t-1},\quad
y_{kjj't}\le g_{kj't},\quad
y_{kjj't}\ge g_{kj,t-1}+g_{kj't}-1
```

```math
y_{kjj't}=0 \quad \text{if }Q_{jj'}=0.
```

### 위치 전이

```math
m_{kpp't}\le z_{kp,t-1},\quad
m_{kpp't}\le z_{kp't},\quad
m_{kpp't}\ge z_{kp,t-1}+z_{kp't}-1.
```

이 정의는 `p=p'`인 stay도 포함한다. 실제 이동 횟수는 `p≠p'`만 합산한다.

### 공통 상태로의 사영

```math
u_{pjlt}=\sum_k s_{kpjlt}.
```

이를 공통 생산능력 및 material-flow 식에 대입한다.

### 목적함수

초기 상태로 구매 configuration을 결정할 경우:

```math
\min
\sum_{k,p,j,l}c^B_js_{kpjl1}
+\sum_{k,t\ge2,j,j'}c^R_{jj'}y_{kjj't}
+\sum_{k,t\ge2,p\ne p'}(F+\beta D_{pp'})m_{kpp't}
+C^{MHC}.
```

`main:Src/models/adaptive_shared_resource.py`에는 shared-resource capacity, module stock, 이동/재구성 횟수 제한 등도 있다. 이는 adaptive의 필수 정의가 아니라 별도 확장이다. 네 모델의 순수 비교에서는 먼저 제외하거나 네 모델 모두에 동등하게 적용해야 한다.

---

## Model 3 — network formulation: 위치 고정

각 위치에 대해 시간 방향의 한 경로로 RMT lifecycle을 표현한다.

### network 구성

- 노드 `n=(p,t,j,l)`
- 구매 arc: source에서 `(p,1,j,l)`로 진입
- 전이 arc: `(p,t-1,j,l)→(p,t,j',l')`; 위치 `p`는 고정
- 종료 arc: 마지막 기간 노드에서 sink로 진입

### 변수

- `w_{ptjl}∈{0,1}`: lifecycle node 점유
- `a^B_{pjl}∈{0,1}`: 구매 arc 사용
- `a_{ptjlj'l'}∈{0,1}`: 기간 전이 arc 사용
- `a^E_{pjl}∈{0,1}`: 종료 arc 사용

### network conservation

위치당 최대 한 경로:

```math
\sum_{j,l}a^B_{pjl}\le1 \qquad \forall p.
```

첫 기간:

```math
w_{p1jl}=a^B_{pjl}.
```

중간 노드의 유입과 점유, 점유와 유출:

```math
\sum_{(j^-,l^-)}a_{ptj^-l^-jl}=w_{ptjl}
\qquad t\ge2,
```

```math
w_{ptjl}=\sum_{(j^+,l^+)}a_{p,t+1,jl j^+l^+}
\qquad t<H.
```

마지막 기간:

```math
w_{pHjl}=a^E_{pjl}.
```

허용 transition arc만 생성하여 machine type 및 configuration 전이 규칙을 강제한다.

### 사영과 목적함수

```math
u_{pjlt}=w_{ptjl}.
```

```math
\min
\sum_{p,j,l}c^B_ja^B_{pjl}
+\sum_{p,t\ge2,j,l,j',l'}c^R_{jj'}a_{ptjlj'l'}
+C^{MHC}.
```

Model 1의 `s,y` 논리를 하나의 연속된 경로로 묶는 것이 핵심이다.

---

## Model 4 — network + adaptive relocation

Model 3의 transition arc가 위치까지 바꿀 수 있도록 확장된다.

### network 구성과 변수

- 노드 `n=(p,t,j,l)`
- 이동가능 전이 arc: `(p,t-1,j,l)→(p',t,j',l')`
- `a_{pp'tjlj'l'}∈{0,1}`: 해당 transition 사용
- 구매·노드·종료 변수는 Model 3와 동일한 역할

### 위치 용량과 flow conservation

각 기간·위치에 최대 한 대:

```math
\sum_{j,l}w_{ptjl}\le1 \qquad \forall p,t.
```

모든 노드에서:

```math
\sum_{p^-,j^-,l^-}a_{p^-p,t,j^-l^-jl}=w_{ptjl}
\qquad t\ge2,
```

```math
w_{ptjl}=\sum_{p^+,j^+,l^+}a_{pp^+,t+1,jl j^+l^+}
\qquad t<H.
```

초기 구매 및 마지막 종료 연결은 Model 3과 같다. 이 흐름보존 때문에 개별 자산 index가 없어도 각 경로가 한 RMT lifecycle이 된다.

### 목적함수

```math
\min
\sum_{p,j,l}c^B_ja^B_{pjl}
+\sum_{t\ge2,p,p',j,l,j',l'}
\left[c^R_{jj'}+\mathbf{1}_{p\ne p'}(F+\beta D_{pp'})\right]
a_{pp'tjlj'l'}
+C^{MHC}.
```

Model 2와 같은 이동 메커니즘이란 정확히 다음을 뜻한다: `t-1`의 위치와 `t`의 위치를 같은 RMT lifecycle에서 연결하고, `p≠p'`일 때 같은 거리함수와 고정/변동 relocation cost를 부과하며, 도착 위치의 점유 제한을 지킨다.

