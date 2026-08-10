# RMS 싱글파트 모델 1~4: 통일 수식 명세

기준 스냅샷: `main@99e660fb8d262451cc361c72f68ff11c301d6021` (파일 6개 + zip 기준)

표기 구분: **[논문]** = 원문 그대로 / **[코드]** = `main` 실제 구현 / **[정리]** = 이번에 새로 도출·정리한 식 (기존 자료에 없던 부분)

먼저 미해결 항목부터 명시한다 — 논문 보고값 총비용 `23,082`와 `main` 저장 결과의 exact optimum `22,910`(구매 11,025 + 재구성 1,925 + MHC 9,960)이 일치하지 않는다. 데이터·거리·flow·비용 정의 차이를 추적해야 하는 **미해결 검증 항목**이며, 이 문서는 이를 임의로 봉합하지 않는다.

---

## (a) 통일 Notation Table

### 집합·인덱스

| 기호 | 의미 |
|---|---|
| `P` | 실제 RMT 설치 가능 위치, `p,p'∈P` |
| `T={1,...,H}` | 계획기간, `t∈T` |
| `J` | 가능한 RMT configuration, `j,j'∈J` |
| `L` | 수행 가능한 operation, `l,l'∈L` |
| `H⊆J×L` | configuration–operation 가능쌍 |
| `A` | 제품 공정경로의 연속 operation arc 집합 (싱글파트: `5→1→17`) |
| `K` | 잠재적 물리 RMT 자산 집합 (Model 2 전용 label) |
| `p^S,p^E` | material-flow용 가상 시작·종료 위치 |
| `l^S,l^E` | 공정경로용 가상 시작·종료 operation |

### 파라미터

| 기호 | 의미 |
|---|---|
| `D_{pp'}` | 위치 `p,p'` 사이 거리 |
| `c^B_j` | configuration `j` 상태 RMT 구매비용 |
| `c^R_{jj'}` | `j→j'` module 추가·제거 재구성비용 (RMT 폐기비 아님) |
| `B_{jl}` | configuration `j`가 operation `l` 수행 시 기간당 생산능력 |
| `d^t_{ll'}` | period `t`, 공정 arc `(l,l')`를 통과해야 하는 정확한 물량 |
| `h` | 단위거리·단위물량 material handling cost |
| `F` | 이동 1회당 고정비 |
| `β` | RMT 단위거리 relocation cost |
| `M(j)` | configuration `j`의 기본 machine type |
| `Q_{jj'}` | configuration `j→j'` 전이 허용 여부 |

싱글파트 수요(코드 기준): `50, 60, 80, 100`. 공정순서: `5→1→17`.

### 공통 물리변수 (모든 모델을 여기로 사영해서 비교)

- `u_{pjlt}∈{0,1}`: period `t`, 위치 `p`가 상태 `(j,l)`를 점유하는지 — 각 모델의 원시 변수를 이 변수로 사영한다.
- `v_{plt}≥0`: period `t`, 위치 `p`에서 operation `l`로 처리한 물량
- `f_{pl,p'l',t}≥0`: `(p,l)`에서 `(p',l')`로 이동한 물량

---

## (b) 모델 1~4: 목적함수와 전체 제약

### 공통 material-flow layer [코드] — 4개 모델 모두 동일하게 유지

```math
v_{plt} \le \sum_{j:(j,l)\in H} B_{jl}\,u_{pjlt} \qquad \forall p,l,t
```

```math
\sum_{(\bar p,\bar l)} f_{\bar p\bar l,pl,t} = v_{plt} \qquad \forall p,l,t
```

```math
v_{plt} = \sum_{(\bar p,\bar l)} f_{pl,\bar p\bar l,t} \qquad \forall p,l,t
```

```math
\sum_{p,p'} f_{pl,p'l',t} = d^t_{ll'} \qquad \forall (l,l')\in A,\ t
```

```math
C^{MHC} = h\sum_t\sum_{p,l,p',l'} D_{pp'}\, f_{pl,p'l',t}
```

주의: 논문은 제품–기간 수요와 operation 수행을 중심으로 식을 쓰지만, 코드는 loader가 생성한 **route-arc demand**를 마지막 등식으로 강제한다. 따라서 "Model 1 = 논문 식 그대로"라는 표현은 부정확하며, 정확히는 **논문 기반 기준 MILP의 코드 구현**이다.

---

### Model 1 — 논문 기반 기준 MILP: 위치 고정 [논문+코드]

변수:
- `x_{pjl}∈{0,1}`: 위치 `p`에 최초 구매한 RMT의 초기 `(j,l)` 상태
- `s_{pjlt}∈{0,1}`: period `t`에 위치 `p`가 `(j,l)` 상태 (`u_{pjlt}≡s_{pjlt}`)
- `y_{pj'jlt}∈{0,1}`: 같은 위치 RMT가 `t-1`의 `j'`에서 `t`의 `j`로 전이, operation `l` 담당

제약:

```math
\sum_{(j,l)\in H} x_{pjl} \le 1 \qquad \forall p
```

```math
s_{pjl1} = x_{pjl} \qquad \forall p,(j,l)\in H
```

```math
y_{pj'jlt} \le \sum_{\bar l:(j',\bar l)\in H} s_{pj'\bar l,t-1}
```

```math
y_{pj'jlt} \le s_{pjlt}
```

```math
y_{pj'jlt} \ge \sum_{\bar l:(j',\bar l)\in H} s_{pj'\bar l,t-1} + s_{pjlt} - 1
```

```math
y_{pj'jlt} = 0 \quad \text{if } Q_{j'j}=0
```

RMT의 위치 `p`는 기간 전체에서 고정된다(이동 없음).

목적함수:

```math
\min \sum_{p,j,l} c^B_j x_{pjl} + \sum_{p,t\ge2,j',j,l} c^R_{j'j}\, y_{pj'jlt} + C^{MHC}
```

---

### Model 2 — 논문형 MILP + adaptive relocation [코드, relocation core만 분리]

위치가 바뀌어도 동일 물리 RMT임을 추적하기 위해 자산 index `k`가 필요하다.

변수:
- `b_k∈{0,1}`: 잠재 자산 `k` 구매 여부
- `s_{kpjlt}∈{0,1}`: 자산 `k`가 `t`에 위치 `p`, 상태 `(j,l)`
- `z_{kpt}∈{0,1}`: 자산 `k`가 `t`에 위치 `p`
- `g_{kjt}∈{0,1}`: 자산 `k`가 `t`에 configuration `j`
- `y_{kjj't}∈{0,1}`: 자산 `k`의 configuration 전이 `j→j'`
- `m_{kpp't}∈{0,1}`: 자산 `k`의 위치 전이 `p→p'` (p=p' stay 포함, 실제 이동횟수는 `p≠p'`만 합산)

제약:

```math
\sum_{p,(j,l)\in H} s_{kpjlt} = b_k \qquad \forall k,t
```

```math
\sum_{k,(j,l)\in H} s_{kpjlt} \le 1 \qquad \forall p,t
```

```math
z_{kpt} = \sum_{(j,l)\in H} s_{kpjlt}, \qquad g_{kjt} = \sum_{p,l:(j,l)\in H} s_{kpjlt}
```

```math
y_{kjj't} \le g_{kj,t-1}, \quad y_{kjj't} \le g_{kj't}, \quad y_{kjj't} \ge g_{kj,t-1}+g_{kj't}-1
```

```math
y_{kjj't} = 0 \quad \text{if } Q_{jj'}=0
```

```math
m_{kpp't} \le z_{kp,t-1}, \quad m_{kpp't} \le z_{kp't}, \quad m_{kpp't} \ge z_{kp,t-1}+z_{kp't}-1
```

사영: `u_{pjlt} = \sum_k s_{kpjlt}`.

목적함수 (구매 configuration을 초기상태로 결정하는 버전):

```math
\min \sum_{k,p,j,l} c^B_j\, s_{kpjl1} + \sum_{k,t\ge2,j,j'} c^R_{jj'}\, y_{kjj't} + \sum_{k,t\ge2,p\ne p'} (F+\beta D_{pp'})\, m_{kpp't} + C^{MHC}
```

**주의 [정리]**: `main`의 `adaptive_shared_resource.py`에는 shared-resource capacity, module stock, 이동/재구성 횟수 제한 등 추가 확장이 더 들어 있다. 이것들은 relocation의 필수 정의가 아니다. 4모델 순수 비교에서는 제외하거나 4모델 모두에 동등 적용해야 한다.

---

### Model 3 — network formulation: 위치 고정 [코드]

각 위치에 대해 시간축 방향의 경로 하나로 RMT lifecycle을 표현한다.

노드: `n=(p,t,j,l)`. Arc: 구매 arc(source→`(p,1,j,l)`), 전이 arc(`(p,t-1,j,l)→(p,t,j',l')`, 위치 `p` 고정), 종료 arc(마지막 기간→sink).

변수:
- `w_{ptjl}∈{0,1}`: lifecycle node 점유 (`u_{pjlt}≡w_{ptjl}`)
- `a^B_{pjl}∈{0,1}`: 구매 arc 사용
- `a_{ptjlj'l'}∈{0,1}`: 기간 전이 arc 사용
- `a^E_{pjl}∈{0,1}`: 종료 arc 사용

제약:

```math
\sum_{j,l} a^B_{pjl} \le 1 \qquad \forall p
```

```math
w_{p1jl} = a^B_{pjl}
```

```math
\sum_{(j^-,l^-)} a_{ptj^-l^-jl} = w_{ptjl} \qquad t\ge2
```

```math
w_{ptjl} = \sum_{(j^+,l^+)} a_{p,t+1,jlj^+l^+} \qquad t<H
```

```math
w_{pHjl} = a^E_{pjl}
```

허용되지 않는 전이는 arc 생성 단계에서 제외해 강제한다(machine type, `Q_{jj'}`).

목적함수:

```math
\min \sum_{p,j,l} c^B_j\, a^B_{pjl} + \sum_{p,t\ge2,j,l,j',l'} c^R_{jj'}\, a_{ptjlj'l'} + C^{MHC}
```

Model 1의 `s,y` implication logic을 하나의 연속 경로(flow conservation)로 묶은 것이 핵심이다.

---

### Model 4 — network + adaptive relocation [코드]

Model 3의 전이 arc가 위치까지 바꿀 수 있도록 확장된다.

노드: `n=(p,t,j,l)`. 이동가능 전이 arc: `(p,t-1,j,l)→(p',t,j',l')`.

변수: `a_{pp'tjlj'l'}∈{0,1}` (해당 transition 사용). 구매·노드·종료 변수는 Model 3와 동일한 역할.

제약:

```math
\sum_{j,l} w_{ptjl} \le 1 \qquad \forall p,t
```

```math
\sum_{p^-,j^-,l^-} a_{p^-p,t,j^-l^-jl} = w_{ptjl} \qquad t\ge2
```

```math
w_{ptjl} = \sum_{p^+,j^+,l^+} a_{pp^+,t+1,jlj^+l^+} \qquad t<H
```

초기 구매(`w_{p1jl}=a^B_{pjl}`) 및 마지막 종료(`w_{pHjl}=a^E_{pjl}`) 연결은 Model 3와 동일. 이 flow conservation 덕분에 자산 label `k` 없이도 각 경로가 하나의 RMT lifecycle이 된다.

목적함수:

```math
\min \sum_{p,j,l} c^B_j\, a^B_{pjl} + \sum_{t\ge2,p,p',j,l,j',l'} \left[c^R_{jj'} + \mathbf{1}_{p\ne p'}(F+\beta D_{pp'})\right] a_{pp'tjlj'l'} + C^{MHC}
```

Model 2와 "같은 이동 메커니즘"이라는 말의 정확한 의미: `t-1`의 위치와 `t`의 위치를 같은 RMT lifecycle에서 연결하고, `p≠p'`일 때 동일한 거리함수·고정/변동 relocation cost를 부과하며, 도착 위치의 점유 제한을 지키는 것.

---

## (c) 변수 정의역 총정리

| 모델 | 변수 | 정의역 | 인덱스 범위 |
|---|---|---|---|
| 1 | `x_{pjl}` | `{0,1}` | `p∈P, (j,l)∈H` |
| 1 | `s_{pjlt}` | `{0,1}` | `p,t,(j,l)∈H` |
| 1 | `y_{pj'jlt}` | `{0,1}` | `p,t≥2,(j',l),(j,l)∈H` |
| 2 | `b_k` | `{0,1}` | `k∈K` |
| 2 | `s_{kpjlt}` | `{0,1}` | `k,p,t,(j,l)∈H` |
| 2 | `z_{kpt},g_{kjt}` | `{0,1}` (보조, 정의로 유도) | `k,p,t` / `k,j,t` |
| 2 | `y_{kjj't}` | `{0,1}` | `k,t≥2,j,j'` |
| 2 | `m_{kpp't}` | `{0,1}` | `k,t≥2,p,p'` (p=p' 포함) |
| 3 | `w_{ptjl}` | `{0,1}` | `p,t,(j,l)∈H` |
| 3 | `a^B_{pjl},a^E_{pjl}` | `{0,1}` | `p,(j,l)∈H` |
| 3 | `a_{ptjlj'l'}` | `{0,1}` | `p,t≥2,(j,l),(j',l')∈H` |
| 4 | `a_{pp'tjlj'l'}` | `{0,1}` | `p,p',t≥2,(j,l),(j',l')∈H` |
| 공통 | `v_{plt}` | `≥0` | `p,l,t` |
| 공통 | `f_{pl,p'l',t}` | `≥0` | `p,l,p',l',t` |

---

## (d) 모델 간 정수해 매핑 (사영)

원시 변수공간끼리는 차원과 의미가 달라 포함관계를 직접 말할 수 없다. 반드시 공통 물리변수 `(u,f)`로 사영한 뒤 비교한다.

- Model 1: `u_{pjlt} := s_{pjlt}`
- Model 2: `u_{pjlt} := \sum_k s_{kpjlt}`
- Model 3: `u_{pjlt} := w_{ptjl}`
- Model 4: `u_{pjlt} := w_{ptjl}` (Model 3와 동일 정의, arc 구조만 다름)

`f`는 모든 모델에서 공통 material-flow layer로 동일하게 정의된다(모델별로 정의를 바꾸지 않는다 — 이것이 "공정한 비교"의 전제).

---

## (e) 동치성 명제와 proof sketch

동일한 구매시점(안 A: period 1 구매만), 초기조건, 허용 configuration 전이(`Q`), 위치 용량(위치당 1대), 수요, 비용 정의를 가정할 때:

```math
\operatorname{proj}_{u,f}(F_1) = \operatorname{proj}_{u,f}(F_3) \subseteq \operatorname{proj}_{u,f}(F_2) = \operatorname{proj}_{u,f}(F_4)
```

**명제 1: `proj(F1) = proj(F3)`.**
증명 스케치 — 두 모델 다 위치 `p`가 고정이므로 각 `p`는 독립적인 시간축 문제다. Model 1의 `(x_{pjl}, s_{pjlt}, y_{pj'jlt})` 궤적 하나는 Model 3에서 `a^B_{pjl}=x_{pjl}`, `w_{ptjl}=s_{pjlt}`, `a_{ptjlj'l'}=y_{pj'jlt}\cdot[\text{동일 }(j,l)\to(j',l')\text{ 전이}]`로 정확히 사상되고, 역방향도 같은 방식으로 성립한다. Model 1의 implication 제약(3개 부등식)과 Model 3의 flow conservation은 둘 다 "이전 기간 상태 또는 신규 구매가 있어야 현재 상태 성립"이라는 동일한 논리를 다른 방식(big-M류 implication vs. 노드 유입=점유)으로 인코딩하므로 feasible한 `(j,l)` 궤적 집합이 위치별로 완전히 동일하다.

**명제 2: `proj(F2) = proj(F4)`.**
증명 스케치 — 자산 label `k`를 제거하고 물리적 위치·기간 점유만 보면, Model 2의 `s_{kpjlt}`가 나타내는 "자산 `k`의 시간에 따른 (위치,상태) 경로"와 Model 4의 arc 경로 `(p,t,j,l)\to(p',t+1,j',l')`는 동일한 대상을 label 유무로만 다르게 표현한다. `m_{kpp't}\leftrightarrow a_{pp'tjlj'l'}`가 같은 이동을 가리키고, relocation cost `(F+\beta D_{pp'})`가 `p\ne p'`에만 부과되는 정의가 동일하면 목적함수도 일치한다. 다만 이 명제는 **04번 문서가 지적한 미검증 항목**이다 — `main` 스냅샷에는 Model 2↔4 동치성을 수치로 검증한 committed regression 결과가 없다. 증명은 구조상 타당하지만 실증은 아직 안 됐다.

**명제 3: `proj(F1) ⊆ proj(F2)` (같은 논리로 `proj(F3) ⊆ proj(F4)`).**
증명 스케치 — Model 2/4의 모든 전이 arc에서 `p'=p`(stay)를 선택하면 relocation cost가 0으로 정확히 Model 1/3의 계획을 재현하는 feasible solution이 된다. 따라서 고정위치 최적 계획은 항상 adaptive 모델의 feasible set 안에 있다. relocation cost가 음수가 아니므로, adaptive 최적값은 고정위치 최적값보다 나빠질 수 없다(`obj(F2) \le obj(F1)`, `obj(F4)\le obj(F3)`). **이 부등식이 실험에서 깨진다면 모델 오류가 아니라 time limit/gap, 또는 두 모델에 서로 다른 제약·비용·초기조건이 들어갔다는 신호로 먼저 의심해야 한다** — 04번 문서가 정리한 대표 원인 7가지(중도 source/sink 허용 차이, 구매시점 차이, stay arc 비용/횟수 처리 차이, 전이 허용집합 차이, shared-resource 등 비대칭 확장, 위치 점유 제한의 정의 차이, label 대칭성으로 인한 미해 증명)를 먼저 점검한다.

---

## (f) 계산복잡도 / LP relaxation 비교

싱글파트 저장 benchmark (`RMS_Network_Reformulation/results/comparison/single_part/seed_1/formulation_comparison.json`):

| formulation | 정수 objective | LP relaxation | binaries | variables | constraints | runtime(s) |
|---|---:|---:|---:|---:|---:|---:|
| base (Model 1) | 22,910 | 20,925.08148 | 1,856 | 4,096 | 3,136 | 6.506 |
| network (Model 3) | 22,910 | 22,162.618038 | 832 | 4,944 | 1,856 | 2.338 |
| network_mir | 22,910 | 22,674.8 | 832 | 미기록 | 1,892 | 0.904 |

최소화 문제이므로 더 높은 LP 하한이 더 강한 relaxation을 뜻한다. 이 instance에서는 network가 base보다 명확히 강했고(정수해는 동일 22,910, 이는 명제 1의 실증 근거), binary 수도 약 절반(832 vs 1,856)으로 줄었다. **다만 이것은 이 한 instance의 실증 결과이며, "network relaxation이 항상 base relaxation보다 강하다"는 일반 정리는 별도 polyhedral proof 없이 단정하지 않는다.**

Model 4의 후보 arc 수는 대략 `O(|T|\,|P|^2\,|H|^2)`로 위치·상태 조합이 늘어날수록 빠르게 커진다 — sparse arc generation(허용 전이만 생성)이 실용적으로 중요하다.

network formulation의 구조적 장점 요약:
- 기간별 상태연결이 flow conservation으로 직접 보장됨(별도 implication 불필요)
- 허용되지 않는 전이는 애초에 arc를 만들지 않는 방식으로 제거 가능
- big-M류 보조논리가 줄어 LP relaxation이 일반적으로 강해지는 경향
- lifecycle을 경로로 시각화·검사하기 쉬움
- adaptive에서도 자산 label `k`가 필요 없어 대칭성(symmetry)이 줄어듦

단점: transition arc 수 증가(위 복잡도 식).

---

## (g) 코드–수식 line mapping

기준: `main@99e660fb8d262451cc361c72f68ff11c301d6021`. **행 번호는 탐색용 근사치이며 최종 인용 전 원문 재확인 필요.**

| 모델 | 파일 | 구간 | 내용 |
|---|---|---|---|
| 1 | `Src/models/milp.py` | ~28 | `solve` |
| 1 | 〃 | ~43–52 | `x/s/y` key 구성 |
| 1 | 〃 | ~91–104 | 위치당 1대 + 초기상태 |
| 1 | 〃 | ~106–135 | configuration transition |
| 1 | 〃 | ~143–181 | capacity/material flow |
| 1 | 〃 | ~183–194 | 목적함수 |
| 2 | `Src/models/adaptive_shared_resource.py` | ~93–107 | asset set, `b_k` |
| 2 | 〃 | ~116–144 | `s,z,g,y,move` |
| 2 | 〃 | ~155–195 | 자산/위치 점유·연결 |
| 2 | 〃 | ~213–238 | configuration/position transition |
| 2 | 〃 | ~240– | capacity/material flow |
| 2 | 〃 | ~290– | shared-resource 등 선택 확장(핵심 모델 아님) |
| 2 | 〃 | ~326–353 | 목적함수 |
| 3 | `Src/models/milp_network.py` | ~50–62 | node/arc 집합 |
| 3 | 〃 | ~74–84 | 목적함수 |
| 3 | 〃 | ~112– | transition arc 생성 |
| 3 | 〃 | ~160–193 | 위치별 path/node balance |
| 4 | `Src/models/network_adaptive.py` | ~51 | node |
| 4 | 〃 | ~80–87 | relocation cost |
| 4 | 〃 | ~124– | 위치 간 transition arc 생성 |
| 4 | 〃 | ~181–189 | 초기 구매/기간별 위치 점유 |
| 4 | 〃 | ~213–214 | node balance |

---

## (h) 검증 실험 설계 (권장 순서)

1. relocation을 금지(`p'=p`만 허용)했을 때 Model 4 objective가 Model 3와 정확히 일치하는지 확인 — 명제 1 실증 확장.
2. relocation cost를 충분히 크게 했을 때 Model 4가 Model 3의 물리해로 정확히 회귀하는지 확인 — 명제 3의 경계조건 확인.
3. Model 2와 4에서 shared-resource 등 부가 제약을 걷어내고 "순수 relocation core"만 남긴 뒤 objective와 기간별 `u`를 비교 — 명제 2 실증(현재 미검증 상태).
4. 작은 instance(예: `P`,`T` 축소)를 exhaustive enumeration으로 직접 풀어 두 formulation의 정수 물리해 집합이 정말 같은지 비교.
5. solver time limit을 해제하거나 충분히 늘려 4개 모델 모두 status가 `OPTIMAL`인지 확인(현재 결과가 gap 때문인지 구조 때문인지 구분).

비교 시 함께 보고할 지표:
- objective 및 purchase/reconfiguration/relocation/MHC breakdown
- RMT 구매 대수와 기간별 위치/configuration
- 이동 횟수, 총 이동거리, configuration 변경 횟수
- 변수·binary·제약 수
- root LP bound와 integrality gap
- runtime, explored nodes, incumbent gap, solver status
- Model 1↔3, Model 2↔4의 물리해 사영(`u,f`) 일치 여부

공정 비교를 위해 반드시 고정할 것: 동일 기간/위치/configuration/공정경로/수요/capacity, 동일 구매·모듈비·MHC 정의, Model 2·4에 동일 relocation cost와 동일 이동 허용집합, 구매 허용 시점의 통일(안 A/B/C 중 택1), 위치당 1대 제한과 자산의 기간당 1위치 점유 제한의 통일.

---

## 부록 A. 논문과 별도로 결정해야 하는 설계 선택 ("결정 필요")

1. **구매·퇴출**: 안 A(period 1 구매만, 끝까지 보유) / 안 B(중도 구매 허용) / 안 C(중도 퇴출·재판매 허용). `main`의 논문 비교에는 안 A가 기본값으로 가장 자연스러움. B/C는 별도 확장.
2. **operation assignment의 의미**: 한 RMT가 한 기간에 하나의 operation만 전담하는가(현재 `(j,l)` 상태변수는 이걸 전제), 아니면 같은 configuration으로 여러 operation의 물량을 분할 처리할 수 있는가(원하면 상태와 생산 할당을 분리해야 함).
3. **relocation timing**: 이동이 기간 경계에서 즉시·capacity 손실 없이 일어나는가(현재 `main`은 이쪽) 대 이동/설치시간 때문에 다음 기간 capacity가 줄어드는가(별도의 lead-time 제약 필요).
4. **재구성과 이동의 동시 수행 허용 여부**: 현재 network arc는 한 기간 경계에서 위치와 configuration을 동시에 바꿀 수 있다. 물리적으로 금지하려면 "한 경계에서 이동 또는 재구성 중 하나만" 제약을 추가하고 Model 2에도 동일 적용해야 한다.
5. **이동비와 MHC는 별개**: relocation은 RMT 자체의 기간 간 이동비, MHC는 기간 내 부품 흐름 비용. 시간축과 대상이 다르므로 합치지 않는다. 이동비가 높아 이동이 선택되지 않는 결과는 모델 오류가 아니라 현재 데이터에서 나온 경제적 결론일 수 있다 — relocation의 가치를 보고 싶으면 비용을 인위적으로 낮추기보다 수요 mix 변화·복수 파트·병목 위치·layout 거리·이동 횟수 제한 등으로 sensitivity analysis를 한다.

## 부록 B. 알려진 미해결 사항 (임의로 채우지 않음)

1. 논문값 `23,082` vs 코드값 `22,910` 불일치 원인 미확정.
2. Model 2 파일(`adaptive_shared_resource.py`)은 relocation 외 확장(shared resource, module stock, schedule limit)을 포함해 순수 "논문+adaptive" 구현이 아님 — 이 문서에서는 relocation core만 분리해 서술.
3. Model 2↔4 동치성의 수치 검증(committed regression)이 아직 없음.
4. `network_mir` 결과가 저장 파일에는 있으나 현재 스냅샷 소스에서 대응 MIR/counting/theta 구현을 찾기 어려움 — 결과 생성 코드나 이전 commit 확인 필요.
5. relocation cost 관련 주석과 실제 기본값의 상대 크기가 맞는지 재검토 필요.
6. 4개 모델은 기본적으로 전체 기간 수요를 아는 deterministic full-information 가정 — online/myopic(기간별 재최적화)은 정보구조가 다른 별도의 다섯 번째 축이며 adaptive relocation과 혼동하지 않는다.

## 부록 C. 권장 논문 서술 순서

1. 기준 문제와 full-information 가정
2. Model 1의 물리적 고정위치 구조
3. Model 2에서 relocation을 허용해 feasible set 확장
4. Model 1을 Model 3의 lifecycle network로 재수식화
5. 두 아이디어를 결합해 Model 4 도출
6. 정수 물리해 동치성과 fixed/adaptive 포함관계 제시(명제 1~3)
7. formulation별 계산성능과 adaptive의 운영가치를 분리해서 실험(계산 효율 vs 의사결정 범위 확장은 별개 질문)
