# Network-MIR vs Schedule-based Dantzig–Wolfe

멀티파트 데이터, formulation별 600초, seed=1, threads=1의 동일 조건 비교입니다.
두 모델 모두 shared-resource 확장은 끄고 동일한 counting·theta·MIR valid inequalities를 사용했습니다.

## 핵심 확인

- 순수 LP 하한 일치: 예 (`network=34888.485638`, `schedule_dw=34888.485638`)
- LP 하한이 같다면 full schedule column과 lifecycle arc가 flow decomposition 관점에서 동등하다는 실증입니다.
- 따라서 이 비교의 핵심은 정수분기 성능, 시간별 gap, node 수, 모델 크기입니다.
- Network-MIR는 best-known 35,775를 75.8176초에 찾았고, Schedule-DW는 제한시간 내 찾지 못했습니다.
- 최종 gap은 Network-MIR 1.0859%, Schedule-DW 1.2974%입니다.
- Network-MIR의 gap integral은 Schedule-DW보다 24.78% 작아 전체 시간 구간에서도 더 빠르게 gap을 줄였습니다.
- 2% gap 도달시간은 Network-MIR 14.6471초, Schedule-DW 100.9062초입니다.
- 순수 LP 계산도 Network-MIR가 약 3.72배 빠릅니다.

## 최종 결과

| formulation | status | incumbent | bound | gap(%) | runtime(s) | nodes | binary | constraints | gap integral |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| network_mir | TIME_LIMIT | 35,775.0000 | 35,386.5205 | 1.0859 | 600.0054 | 25,817.0000 | 1600 | 3698 | 784.5372 |
| schedule_dw | TIME_LIMIT | 35,791.0000 | 35,326.6482 | 1.2974 | 600.0105 | 30,305.0000 | 57600 | 1298 | 1,043.0353 |

`gap_integral_percent_seconds`는 최초 incumbent 이후 gap 곡선 아래 면적이며 작을수록 빠르게 gap을 줄였다는 뜻입니다.
각 gap 기준 도달시간은 `comparison_summary.csv`, 전체 시간 이력은 `gap_progress.csv`에서 확인할 수 있습니다.

## 결론

이 멀티파트 4기간 인스턴스에서는 full-enumeration Schedule-DW가 Network-MIR보다 강한 LP 하한을 만들지 못하면서 이진변수를 크게 증가시켰습니다. 동일 600초 조건에서는 Network-MIR가 incumbent와 bound 양쪽에서 더 우수합니다. Schedule 접근을 계속 발전시키려면 전체 column 열거가 아니라 pricing과 branch-and-price가 필요합니다.
