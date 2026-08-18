# RMS Network Reformulation

Saffar et al.의 dynamic RMS layout model을 machine-lifecycle network로 재정식화하고,
세미나 자료의 counting, theta, MIR valid inequalities까지 재현하는 연구 코드입니다.

## 무엇이 달라졌나

Base model은 구매 `x`, 기간 상태 `s`, 재구성 `y`를 implication 제약으로 연결합니다.
이 프로젝트는 각 위치의 전체 기간 상태를 `w` node와 `z` transition arc로 연결한
하나의 source-sink path로 표현합니다.

| 항목 | Base model | Network reformulation |
|---|---|---|
| 기계 상태 | `x`, `s`, `y` 이진변수 | `w` 이진 node + `z` 연속 arc |
| 기간 연결 | implication | exact flow conservation |
| Example 1 이진변수 | 1,856 | 832 |
| pure LP bound | 20,925 | 22,162.618 |
| 가장 강한 compact bound | - | 22,674.8 (`network_mir`) |
| 확장성 | 전이변수 증가와 약한 LP | relocation/resource arc 확장에 적합 |

자세한 수식은 [NETWORK_FORMULATION.md](NETWORK_FORMULATION.md), 코드 구성은
[ARCHITECTURE.md](ARCHITECTURE.md), 후속 연구 순서는 [ROADMAP.md](ROADMAP.md)를
참고하세요.

## 강화 프로필

- `network`: lifecycle network만 사용
- `network_counting`: operation별 최소 기계 수 cut 추가
- `network_theta`: operation별 서로 다른 생산률을 divisor로 한 CG rounding 추가
- `network_mir`: counting + theta + MIR, 기본값이자 가장 강한 compact 모델

cut 후보는 `Src/strengthening.py`에서 만들고, 같은 operation-period 안에서
정규화 계수 기준으로 중복되거나 지배되는 cut을 제거합니다.

## 실행

```bash
source .venv/bin/activate

# 기본: Example 1, network_mir
python main.py

# formulation과 문제 선택
python main.py --problem multi_part --profile network --time-limit 100

# 논문 pure LP bound 재현
python -m experiments.reproduce_paper

# 기존 논문 base와 network 최적해·성능 직접 비교
python -m experiments.compare_formulations --problem single_part --time-limit 120

# 멀티파트 Network-MIR와 Schedule-DW를 formulation별 600초 비교
python -m experiments.compare_network_dw

# Example 1 회귀검사
python -m unittest \
  tests/test_network_reformulation.py \
  tests/test_formulation_comparison.py
```

결과는 기본적으로 `results/<problem>/<profile>/`에 저장됩니다.

## 검증 기준

Example 1의 best-known objective `22,910`을 기준으로 다음 pure LP bound를
자동검사합니다.

| profile | pure LP bound | gap |
|---|---:|---:|
| network | 22,162.618 | 3.262% |
| network_counting | 22,612.662 | 1.298% |
| network_theta | 22,619.800 | 1.267% |
| network_mir | 22,674.800 | 1.027% |

`network_mir`의 integer model도 objective `22,910`, binary `832`를 검사합니다.

## 기존 논문 formulation과 직접 비교

`experiments.compare_formulations`는 동일한 데이터, seed, thread 설정, time limit,
MIP gap에서 다음 세 formulation을 각각 pure LP와 MIP로 풉니다.

- `base`: 기존 논문의 `x-s-y` implication formulation
- `network`: machine lifecycle network
- `network_mir`: network + counting + theta + MIR

각 formulation의 해는 `results/comparison/<problem>/seed_<seed>/`에 저장하며,
목적값, bound, gap, 이진변수, 탐색 node, 실행시간, 비용 구성과 선택 상태 차이를
CSV·JSON·Markdown으로 함께 기록합니다.

## Network-MIR와 Schedule Dantzig–Wolfe 비교

`experiments.compare_network_dw`는 멀티파트 문제에서 다음 두 모델을 같은 seed,
thread 수, MIR cut, 600초 제한으로 비교합니다.

- `network_mir`: compact machine-lifecycle node-arc formulation
- `schedule_dw`: 한 column이 한 RMT의 4기간 전체 상태경로인 full-enumeration DW master

기본 실행은 다음과 같습니다.

```bash
python -m experiments.compare_network_dw
```

결과는 `results/network_vs_schedule_dw/multi_part/seed_1/`에 저장됩니다.
`comparison_summary.csv`는 최종 objective·bound·gap, root LP, 변수·제약 수,
최초 incumbent 시간, gap 기준별 도달시간과 gap integral을 제공합니다.
`gap_progress.csv`, `mip_gap_progress.png`, `bound_progress.png`에서는 두 모델이
시간에 따라 gap과 bound를 줄이는 과정을 직접 비교할 수 있습니다.

## 시각적 실험 화면

```bash
.venv/bin/python -m streamlit run app.py
```

웹 화면에서 다음을 직접 조작할 수 있습니다.

- Single-part / Multi-part 전환
- 원점은 `(0, 0)`으로 고정하고 `m × n`과 좌표 사이 거리만 설정
- 생성된 각 설치위치와 Start/End 좌표는 표에서 추가 수정
- 기간 수, part, 기간별 수요, operation sequence 편집
- relocation 비용·크루 상한·맞교환 금지 설정
- Stage 1의 동일 최적 시스템 비용 configuration 후보를 최대 6개까지 탐색
- Stage 2의 최소 relocation 해와 period별 레이아웃을 양쪽에서 비교
- 위치 이동비용, configuration 변경비용, `m × n × 거리` 민감도 분석

편집한 입력은 원본 `Data/`를 덮어쓰지 않고
`results/interactive/<scenario>_<timestamp>/input/`에 복사됩니다. Stage 1 후보는
`stage_1_system_cost/candidates/`, Stage 2 결과는 `stage_2_min_relocation/`에 보존됩니다.
민감도 결과는 `results/sensitivity/`에 실험별 CSV와 각 후보의 입력·해를 함께 저장합니다.

## 범위

핵심 baseline에서는 shared resource와 relocation을 끕니다. 기존 shared-resource
제약은 `--shared-resources`, relocation은 `--relocation`으로 켤 수 있으며 논문
baseline과 확장 실험의 결과 경로를 분리해야 합니다.

```bash
python main.py --problem single_part --profile network_mir --relocation \
  --relocation-distance-cost 1 \
  --relocation-downtime 0.25 \
  --relocation-crew-capacity 2 \
  --forbid-reverse-swaps
```

`--relocation`을 켜면 기본적으로 시스템 비용을 먼저 최소화하고, 같은 시스템 비용
안에서 relocation 횟수를 최소화하는 2단계 풀이를 수행합니다. 결과에는
`primary_stage`, `relocation_stage`, `minimum_relocation_count`, `relocations.csv`가
저장됩니다. 수식과 옵션 해석은 `RELOCATION_DESIGN.md`에 정리했습니다.

원본 세미나 자료는 `docs/reference/seminar_RMS_reformulation.pdf`에 보관했습니다.
