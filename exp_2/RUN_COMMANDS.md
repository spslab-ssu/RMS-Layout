# 2차 실험 실행 명령

프로젝트 루트(`RMS-Layout/`)에서 실행합니다.

## Seed 1 이후 Seed 2 연속 실행

아래 명령은 seed 1이 종료된 뒤 seed 2를 자동으로 실행합니다.

```bash
python3 exp/run_experiments.py \
  --manifest exp_2/manifest.csv \
  --output Result/exp_2 \
  --model network \
  --model network_adaptive \
  --seed 1 \
  --time-limit 3600 \
  --mip-gap 0 \
  --network-warm-start \
&& \
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

## Seed별 개별 실행

### Seed 1

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

### Seed 2

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

## 옵션 설명

| 옵션 | 의미 |
|---|---|
| `--manifest exp_2/manifest.csv` | 2차 실험 대상 조건 사용 |
| `--output Result/exp_2` | 2차 실험 결과 저장 위치 |
| `--model network` | 기본 network 모델 실행 |
| `--model network_adaptive` | adaptive network 모델 실행 |
| `--seed 1` 또는 `--seed 2` | 특정 seed만 실행 |
| `--time-limit 3600` | 인스턴스당 최대 3600초 |
| `--mip-gap 0` | 최적해 증명까지 탐색 |
| `--network-warm-start` | network 해를 adaptive 모델의 초기해로 사용 |

## 결과 위치

```text
Result/exp_2/p3/summary.csv
Result/exp_2/p5/summary.csv
```

이미 완료된 인스턴스는 재실행 시 자동으로 건너뜁니다.
