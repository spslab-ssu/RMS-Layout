# Exp4 실행 명령

저장소 루트에서 실행한다. 각 seed는 두 layout 조건을 모두 포함하며, 먼저 seed1 전체를
완료한 뒤 seed2가 시작되도록 명령을 순차적으로 실행한다.

## 1. 데이터 생성

```bash
python3 exp_4/prepare.py
```

## 2. Seed 1 실행

```bash
python3 exp/run_experiments.py \
  --manifest exp_4/manifest.csv \
  --output Result/exp_4 \
  --model network \
  --model network_adaptive \
  --seed 1 \
  --time-limit 3600 \
  --mip-gap 0 \
  --network-warm-start
```

## 3. Seed 2 실행

Seed1 명령이 종료된 뒤 실행한다.

```bash
python3 exp/run_experiments.py \
  --manifest exp_4/manifest.csv \
  --output Result/exp_4 \
  --model network \
  --model network_adaptive \
  --seed 2 \
  --time-limit 3600 \
  --mip-gap 0 \
  --network-warm-start
```

## 4. 한 번에 순차 실행

```bash
python3 exp/run_experiments.py --manifest exp_4/manifest.csv --output Result/exp_4 --model network --model network_adaptive --seed 1 --time-limit 3600 --mip-gap 0 --network-warm-start && \
python3 exp/run_experiments.py --manifest exp_4/manifest.csv --output Result/exp_4 --model network --model network_adaptive --seed 2 --time-limit 3600 --mip-gap 0 --network-warm-start
```

실행 중단 후 같은 명령을 다시 실행해도 완료된 `OPTIMAL`, `TIME_LIMIT`, `INFEASIBLE`
행은 `summary.csv`를 기준으로 자동 건너뛴다.
