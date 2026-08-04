# Research roadmap

## Completed baseline

- machine lifecycle network (`w/z`)
- counting, theta, MIR compact strengthening
- dominance pruning
- Example 1 LP/MIP regression tests
- Example 1/2 benchmark exporter

이 상태가 이후 확장의 공통 기준선입니다. 새 기능은 반드시
`network_mir` baseline과 objective, bound, runtime을 비교해야 합니다.

## Phase 1: relocation network

현재 arc는 같은 위치에서 기간만 연결합니다. 다음 단계에서는
`z[p_prev,...,p_next,...,t]` relocation arc를 선택적으로 만들고 이동비 `gamma`를
목적함수에 추가합니다.

핵심 실험:

- relocation 금지와 허용의 objective 차이
- `gamma` sensitivity
- multi-part phase-in/out에서 실제 이동 횟수
- base-style 6-index formulation 대비 변수/제약 수

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
