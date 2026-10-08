# Exp3: Network vs Network Adaptive

Exp3는 부품 수, layout, overlap, period 수와 수요 변화를 조정해 Network와 Network Adaptive를 비교한다.

## 실험 조건

| 항목 | 조건 |
|---|---|
| 부품 수 | 1, 3, 5 |
| Layout | `layout_22`(4x5), `layout_27`(5x5) |
| Overlap | high, low |
| Period | 2, 4, 6 |
| Seed | 1, 2, 3 |
| 총 demand | base multi-part demand 370 x 0.75 = 278 |
| 모델 | network, network_adaptive |
| Time limit | 1,800초 |
| MIP gap | 0.01% (`0.0001`) |
| Relocation cost | 거리당 1.0 |
| Relocation distance | 제한 없음 |
| Warm start | Network 해를 Network Adaptive에 사용 |

총 108개 인스턴스와 216회 모델 실행을 생성한다.

참고로 총수요 278을 2개 period에 배분하면 period당 수요가 커져 `layout_22` 일부 조건에서
infeasible이 발생할 수 있다. 이는 데이터 생성 오류가 아니라 설치 위치 수와 operation별
생산능력의 조합으로 발생하는 조건이다. 해당 조건을 제외하고 실행하려면 `--period-count 4`
또는 `--period-count 6`을 사용한다.

## 데이터 생성

```bash
python3 exp_3/prepare.py
```

생성 결과:

- `exp_3/manifest.csv`: 108개 실행 조건
- `exp_3/demand_metadata.csv`: 54개 demand 파일의 메타데이터
- `Data/demands/exp_3/`: demand CSV
- `Data/parameters/exp_3/period_2.csv`
- `Data/parameters/exp_3/period_4.csv`
- `Data/parameters/exp_3/period_6.csv`
- `Data/locations/layout_27.csv`: 5x5 설치 위치와 start/end 위치

각 demand 파일은 총수요 278을 유지하고, period 수에 따라 period별 수요를 seed 기반으로
랜덤 배분한다. Sequence는 high/low route 집합에서 seed 기반으로 부품에 배정한다.

## 실행

전체 조건을 순서대로 실행한다.

```bash
python3 exp/run_experiments.py \
  --manifest exp_3/manifest.csv \
  --output Result/exp_3 \
  --model network \
  --model network_adaptive \
  --time-limit 1800 \
  --mip-gap 0.0001 \
  --network-warm-start
```

seed별로 나누어 실행하려면 `exp_3/RUN_COMMANDS.md`를 참고한다. 실행을 중단해도 이미
완료된 `OPTIMAL`, `TIME_LIMIT`, `INFEASIBLE` 결과는 summary 기준으로 자동 skip된다.

통합실행기는 `--part`, `--layout`, `--overlap`, `--period-count`, `--seed`를 조합해
일부 조건만 선택할 수 있다.

## 결과 위치

```text
Result/exp_3/p1/summary.csv
Result/exp_3/p3/summary.csv
Result/exp_3/p5/summary.csv
```

각 인스턴스의 상세 결과는 다음 구조로 저장된다.

```text
Result/exp_3/p3/<experiment_id>/<layout>/network/
Result/exp_3/p3/<experiment_id>/<layout>/network_adaptive/
```

`network_adaptive` summary의 `network_warm_start_*` 열에서 warm start 주입 상태를 확인할
수 있다.
