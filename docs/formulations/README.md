# adaptive layout 정식화 문서 (2026-09-30)

Saffar, Moghaddam & Huang (2025), IJPR 63(17) 식 (1)–(16)에 **기간 경계의 기계 이동(relocation)** 을
더한 두 정식화를 논문 슬라이드 형식(Sets / Indices / Input Parameters / Decision variables /
Objective function / Subject to)으로 정리한 HTML.

브라우저로 바로 열면 되고, 각 식마다 **LaTeX 복사** 버튼이, 문서 끝에는 `amsmath align` 환경
**전체 복사** 블록이 있다.

| 파일 | 모델 | 전이변수 | 구현 |
|---|---|---|---|
| `model_z.html` | **z 인코딩** (팀 표기: network 모델) | `z[k,p,j′,j,l,t]` 6-index, 연속 | `Src/milp_adaptive.py` |
| `model_w.html` | **w 정식화** (Saffar 원형 + 이동 이진변수) | `w[k,p,j,t]` 4-index, 이진 + 논문 `y` | `scratchpad/saffar_w_adaptive.py` |

게시본(claude.ai artifact):
- z 모델 — https://claude.ai/artifact/VatndcvTcA2Uu8EY2x4ZJB
- w 모델 — https://claude.ai/artifact/LV1jhJ9MmNQvm1QAGoiNfa

## 두 모델의 관계

w와 y는 z의 **사영(projection)** 이다.

```
w_{kpjt}    = Σ_{j″∈J} Σ_{l∈L} z_{k p j j″ l t}   (k ≠ p)    ← 도착 config·operation을 합산
y_{p j′ j l t} = Σ_{k∈P} z_{k p j′ j l t}                     ← 출발 위치를 합산
```

w의 지수 `j`가 z의 `j′`(출발 config) 자리에 들어간다. 그래서 이동비 기준가 표기가
z는 `C_{j′}`, w는 `C_j`로 달라도 **같은 configuration**을 가리킨다.

MILP 용어로 z는 extended(arc-based), w는 compact formulation이다.
계보로는 w가 **DFLP(Dynamic Facility Layout Problem)** 의 표준 MIP 이동 구조
(배치 이진 + 재배치 이진 + 보존식)를 Saffar의 RMS 모형 위에 얹은 형태다 —
자세한 것은 `model_w.html` 8절.

## 실측 근거 (자세한 것은 `docs/experiment_results/2026-09-29_adaptive/`)

- LP relaxation bound가 두 모델(및 서훈 network 모델)에서 **소수점까지 일치**:
  multi_part 이동비 0 → 33,841.704881 / 이동비 거리당 1 → 33,845.87855
- Youssef 인스턴스에서 두 모델 모두 17,500을 최적으로 증명 (z 119초 / w 86초)
- multi_part는 10분 안에 양쪽 다 최적 증명이 되지 않아 incumbent만 비교했다 —
  **정수 최적값이 항상 같다는 것은 아직 증명된 주장이 아니다.**

## 재생성

HTML의 LaTeX 블록은 `scratchpad/build_tex.py`(세션 임시 디렉터리)로 만들었다.
직접 편집할 때 주의: **bash heredoc으로 백슬래시가 든 LaTeX을 보내면 이스케이프가 소실된다**
(`\forall` → 제어문자, `\neq` → 줄바꿈). 반드시 파일로 쓴 뒤 실행할 것.
