# Research roadmap

## Completed baseline

- machine lifecycle network (`w/z`)
- counting, theta, MIR compact strengthening
- dominance pruning
- Example 1 LP/MIP regression tests
- Example 1/2 benchmark exporter

이 상태가 이후 확장의 공통 기준선입니다. 새 기능은 반드시
`network_mir` baseline과 objective, bound, runtime을 비교해야 합니다.

## Phase 1: relocation network (implemented)

`Src/relocation.py`가 cross-location transition을 선택적으로 만들고 이동비 `gamma`,
다운타임 `alpha`, 기간별 크루 용량 `R_t`, 역방향 맞교환 금지, 체증형 크루 슬롯을
coupling 계층에 추가한다. 상세 state arc는 연속으로 유지하고 `(p,q,t)` 이동 여부만
binary로 두어 6-index binary 폭증을 피한다.

주 해법은 `system cost -> relocation count`의 정확한 2단계 사전식 최적화다.
체증형 크루 슬롯은 주 목적함수가 아니라 후속 민감도 분석 옵션으로만 유지한다.

핵심 실험:

- relocation 금지와 허용의 objective 차이
- `gamma` sensitivity
- multi-part phase-in/out에서 실제 이동 횟수
- base-style 6-index formulation 대비 변수/제약 수

다음 실험 순서는 `RELOCATION_DESIGN.md`를 따른다. 특히 무료 이동에서 관측되는
과도한 이동 횟수는 최적해의 무차별성일 수 있으므로, 이동 횟수를 relocation 가치로
곧바로 해석하지 않는다.

## Phase 2: shared resource strengthening

현재 shared resource는 선택적 capacity row로 보존되어 있습니다. 후속 단계에서는
resource profile을 cut dominance와 column dominance에 포함합니다.

핵심 실험:

- resource capacity별 objective 증가
- MIR와 resource row 결합 시 root bound 변화
- module profile을 고려한 state/arc 사전 제거

## Phase 3: column generation

위치 하나의 전체 lifecycle path를 하나의 pattern column으로 봅니다.
Restricted master에는 material capacity, valid inequality, resource dual을 포함하고,
pricing은 configuration-time network shortest path로 풉니다.

검증 순서:

1. CG LP bound와 compact `network_mir` LP bound 일치
2. generated column 기반 restricted master heuristic
3. Ryan-Foster 또는 arc branching을 이용한 branch-and-price

## Experiment contract

모든 신규 실험은 다음을 남깁니다.

- configuration snapshot
- objective, best bound, gap, runtime
- 변수/제약/cut/column 수
- seed와 time limit
- 기존 benchmark 대비 차이

이 계약을 유지하면 기본 논문의 재현에서 relocation, shared resource,
branch-and-price까지 결과가 끊기지 않습니다.
