# Exp4: Overlap 효과 검증

4차 실험은 2차 실험의 조건을 유지하면서 작업 sequence의 overlap 수준을 추가해,
Adaptive layout의 MHC 감소 효과가 overlap에 따라 달라지는지 확인한다.

## 실험 조건

| 항목 | 조건 |
|---|---|
| 부품 수 | 3, 5 |
| Layout | `layout_18`, `layout_22` |
| Utilization | 0.75, 1.0 |
| Overlap | high, low |
| Period | 4 |
| Seed | 1, 2 |
| 모델 | network, network_adaptive |
| Time limit | 3,600초 |
| MIP gap | 0 |
| Relocation cost | 거리당 1.0 |
| Relocation distance | 제한 없음 |
| Warm start | Network 해를 Network Adaptive에 주입 |

총 32개 조건과 64회 모델 실행을 생성한다.

High overlap은 route가 4개의 공통 operation을 공유하도록 만들고, low overlap은 operation을
서로 겹치지 않도록 분할한다. Seed별로 route 자체가 달라지도록 생성한다.

## 데이터 생성

저장소 루트에서 실행한다.

```bash
python3 exp_4/prepare.py
```

생성 결과:

- `exp_4/manifest.csv`: 16개 실행 조건
- `exp_4/demand_metadata.csv`: demand 메타데이터
- `Data/demands/exp_4/`: 16개 demand CSV
- `Data/parameters/exp_4/period_4.csv`: 4-period parameter

기준 demand의 period별 총수요 `[70, 110, 100, 90]`에 utilization을 적용한다.

## 결과 저장 위치

```text
Result/exp_4/p3/summary.csv
Result/exp_4/p5/summary.csv
```

## 확인할 지표

- 전체 Objective 및 감소율
- MHC 및 감소율
- relocation cost
- reconfiguration cost
- relocation 발생 횟수
- runtime, best bound, MIP gap
