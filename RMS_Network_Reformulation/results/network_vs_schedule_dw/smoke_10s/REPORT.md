# Network-MIR vs Schedule-based Dantzig–Wolfe

멀티파트 데이터, formulation별 10초, seed=1, threads=1의 동일 조건 비교입니다.
두 모델 모두 shared-resource 확장은 끄고 동일한 counting·theta·MIR valid inequalities를 사용했습니다.

## 핵심 확인

- 순수 LP 하한 일치: 예 (`network=34888.485638`, `schedule_dw=34888.485638`)
- LP 하한이 같다면 full schedule column과 lifecycle arc가 flow decomposition 관점에서 동등하다는 실증입니다.
- 따라서 이 비교의 핵심은 정수분기 성능, 시간별 gap, node 수, 모델 크기입니다.

## 최종 결과

| formulation | status | incumbent | bound | gap(%) | runtime(s) | nodes | binary | constraints | gap integral |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| network_mir | TIME_LIMIT | 35,791.0000 | 35,033.1382 | 2.1175 | 10.0030 | 544.0000 | 1600 | 3698 | 21.9807 |
| schedule_dw | TIME_LIMIT | 35,791.0000 | 35,040.6000 | 2.0966 | 10.0052 | 35.0000 | 57600 | 1298 | 34.8106 |

`gap_integral_percent_seconds`는 최초 incumbent 이후 gap 곡선 아래 면적이며 작을수록 빠르게 gap을 줄였다는 뜻입니다.
각 gap 기준 도달시간은 `comparison_summary.csv`, 전체 시간 이력은 `gap_progress.csv`에서 확인할 수 있습니다.
