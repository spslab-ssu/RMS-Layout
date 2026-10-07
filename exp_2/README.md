# 2차 실험: Network vs Network Adaptive

2차 실험은 부품 수와 수요 규모가 증가할 때 full adaptive layout의 최적 objective가
개선되는지 확인한다. 수요 CSV는 `Data/demands/exp_random/`의 기존 random-sequence
데이터를 재사용하며, 중복 파일을 만들지 않는다.

## 조건

- 부품 수: `3`, `5`
- Layout: `layout_18`, `layout_22`
- Utilization: `0.75`, `1.0`
- Seed: `1`, `2`
- 모델: `network`, `network_adaptive`
- relocation distance limit: 없음
- relocation cost: 기존 설정값 `1.0`
- RMT table: `table_1`

총 16개 인스턴스이며, manifest는 seed 1의 8개 조건 다음에 seed 2의 8개 조건이
오도록 정렬되어 있다.

## 준비

```bash
python3 exp_2/prepare.py
```

## 실행

먼저 seed 1을 실행한다. `network` 결과는 같은 인스턴스의
`network_adaptive`에 partial MIP start로 자동 주입된다.

```bash
python3 exp/run_experiments.py \
  --manifest exp_2/manifest.csv \
  --output Result/exp_2 \
  --model network \
  --model network_adaptive \
  --seed 1 \
  --time-limit 3600 \
  --mip-gap 0 \
  --network-warm-start
```

seed 1이 끝나면 같은 명령에서 `--seed 2`로 이어서 실행한다.

```bash
python3 exp/run_experiments.py \
  --manifest exp_2/manifest.csv \
  --output Result/exp_2 \
  --model network \
  --model network_adaptive \
  --seed 2 \
  --time-limit 3600 \
  --mip-gap 0 \
  --network-warm-start
```

## 결과 위치

```text
Result/exp_2/p3/summary.csv
Result/exp_2/p5/summary.csv
Result/exp_2/p3/<experiment_id>/<layout>/network/
Result/exp_2/p3/<experiment_id>/<layout>/network_adaptive/
```

`network_adaptive` 결과의 `network_warm_start_*` 컬럼에서 warm start 요청 여부,
실제 주입 여부와 변수별 주입 개수를 확인할 수 있다.

최적 objective 비교는 두 모델 모두 `OPTIMAL`인 행만 사용한다. time limit 행은
incumbent objective와 best bound를 별도로 보고한다.
