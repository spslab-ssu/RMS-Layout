# Exp3 실행 명령

프로젝트 루트 `RMS-Layout/`에서 실행한다.

## 1. 데이터 생성

```bash
python3 exp_3/prepare.py
```

## 2. Seed 1부터 Seed 3까지 순차 실행

아래 명령은 seed 1이 끝난 뒤 seed 2, seed 3을 이어서 실행한다.

```bash
python3 exp/run_experiments.py \
  --manifest exp_3/manifest.csv \
  --output Result/exp_3 \
  --model network \
  --model network_adaptive \
  --seed 1 \
  --time-limit 1800 \
  --mip-gap 0.0001 \
  --network-warm-start \
&& \
python3 exp/run_experiments.py \
  --manifest exp_3/manifest.csv \
  --output Result/exp_3 \
  --model network \
  --model network_adaptive \
  --seed 2 \
  --time-limit 1800 \
  --mip-gap 0.0001 \
  --network-warm-start \
&& \
python3 exp/run_experiments.py \
  --manifest exp_3/manifest.csv \
  --output Result/exp_3 \
  --model network \
  --model network_adaptive \
  --seed 3 \
  --time-limit 1800 \
  --mip-gap 0.0001 \
  --network-warm-start
```

## 3. 일부 조건만 실행

부품 수나 layout을 추가할 수 있다.

```bash
python3 exp/run_experiments.py \
  --manifest exp_3/manifest.csv \
  --output Result/exp_3 \
  --model network \
  --model network_adaptive \
  --part 3 \
  --layout layout_22 \
  --period-count 4 \
  --overlap high \
  --seed 1 \
  --time-limit 1800 \
  --mip-gap 0.0001 \
  --network-warm-start
```

## 4. 실행 결과

```text
Result/exp_3/p1/summary.csv
Result/exp_3/p3/summary.csv
Result/exp_3/p5/summary.csv
```

Adaptive 결과는 `objective`, `best_bound`, `mip_gap`, `relocation_cost`와
`network_warm_start_*` 열을 함께 확인한다. `TIME_LIMIT` 결과의 objective는 최적값이
아니라 제한시간 내 incumbent이다.
