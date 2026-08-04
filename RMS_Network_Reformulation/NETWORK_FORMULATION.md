# Network formulation and strengthening

## 1. Base와 network의 구조 차이

Base의 `x[p,j,l]`, `s[p,j,l,t]`, `y[p,j_prev,j,l,t]`는 구매, 상태, 재구성을
서로 다른 이진변수로 두고 implication으로 연결합니다. LP relaxation에서는 이 연결이
fractional state를 허용해 machine layer가 약해집니다.

Network model은 다음 두 변수만 사용합니다.

- `w[p,j,l,t]` binary: period layer의 `(configuration, operation)` node 점유
- `z[p,j_prev,l_prev,j_next,l_next,t]` continuous: 연속 period 사이 transition arc

```text
sum_(j,l) w[p,j,l,1] <= 1

sum_(j_next,l_next) z[p,j,l,j_next,l_next,t+1] = w[p,j,l,t]
sum_(j_prev,l_prev) z[p,j_prev,l_prev,j,l,t]     = w[p,j,l,t]
```

`w`가 이진이면 활성 node는 하나뿐이므로 `z`는 연속이어도 선택 arc가 0/1로 결정됩니다.
서로 다른 machine type 사이에는 arc를 만들지 않습니다.

## 2. Material-flow layer 연결

```text
v[p,l,t] <= sum_j B[j,l] w[p,j,l,t]
```

`v`와 material arc `f`의 flow balance, route demand, Manhattan handling cost는
기존 논문 구조를 유지합니다. 따라서 개선은 machine layer에 집중되며 기존 결과 schema와
layout 시각화를 그대로 사용할 수 있습니다.

## 3. 목적함수

```text
purchase        = sum C[j] w[p,j,l,1]
reconfiguration = sum r[j_prev,j_next] z[...]
handling        = sum MHC * D[p,q] * f[...]
```

## 4. Valid inequalities

Operation `l`, period `t`의 수요를 `d[l,t]`, 최대 생산률을 `Bmax[l]`라 둡니다.

### Counting

```text
sum_(p,j feasible for l) w[p,j,l,t] >= ceil(d[l,t] / Bmax[l])
```

### Theta CG rounding

각 operation의 서로 다른 생산률을 divisor `theta` 후보로 사용합니다.

```text
sum_(p,j) ceil(B[j,l] / theta) w[p,j,l,t]
    >= ceil(d[l,t] / theta)
```

### MIR

`f = frac(d[l,t] / theta)`일 때 `f=0`인 후보는 건너뛰고 다음 계수를 사용합니다.

```text
alpha[j] = floor(B[j,l]/theta)
           + min(1, frac(B[j,l]/theta) / f)

sum_(p,j) alpha[j] w[p,j,l,t] >= ceil(d[l,t]/theta)
```

## 5. Dominance pruning

같은 `(l,t)`의 cut을 우변 1로 정규화합니다. 한 cut의 모든 정규화 계수가 다른
cut보다 작거나 같으면 더 강한 제약이므로 약한 cut을 제거합니다. 이 과정은 MIP feasible
set을 바꾸지 않고 모델 행 수만 줄입니다.

Example 1 `network_mir`에서는 89개 후보 중 36개만 모델에 추가됩니다.

## 6. 검증 결과

| profile | bound | gap vs 22,910 | added cuts |
|---|---:|---:|---:|
| network | 22,162.618 | 3.262% | 0 |
| network_counting | 22,612.662 | 1.298% | 12 |
| network_theta | 22,619.800 | 1.267% | 34 |
| network_mir | 22,674.800 | 1.027% | 36 |

이는 세미나 자료의 network/counting/theta/MIR pure-LP 결과와 일치합니다.
