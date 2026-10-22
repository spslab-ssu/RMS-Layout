# Initial LP Relaxation Experiment

이 폴더의 실행기는 MIP를 풀지 않고 각 모델의 초기 LP relaxation만 계산한다.

`manifest_exp1.csv`에는 1차 실험에 실제 사용한 96개 인스턴스가 미리 정리되어 있다.

## 실행 대상

기본 manifest(`manifest_exp1.csv`) 기준으로 다음 네 모델을 동일한 인스턴스에 대해 순차 실행한다.

- `base`
- `base_adaptive`
- `network`
- `network_adaptive`

실행 결과는 `Result/lp_relaxation/summary.csv`에 저장되며, 기존 MIP 실험 결과와 분리된다.

## 전체 1차 실험 실행

```bash
cd "/Users/miles/Documents/02_학부연구생/01_RMS/03_Development/RMS-Layout"

python3 exp_lp_bound/run_lp_relaxation.py \
  --output Result/lp_relaxation_exp1 \
  --time-limit 300
```

`--time-limit`은 LP relaxation 1회에 허용하는 시간이다. MIP 시간 제한이 아니며, MIP 자체는 실행되지 않는다.

## 대표 인스턴스 점검

```bash
python3 exp_lp_bound/run_lp_relaxation.py \
  --manifest exp_lp_bound/manifest_exp1.csv \
  --output Result/lp_relaxation_pilot \
  --part 1 \
  --layout layout_22 \
  --seed 1 \
  --limit 1
```

## 기록 항목

- `lp_relaxation_bound`: 초기 LP relaxation의 목적함수 값
- `lp_run_wall_seconds`: 모델 생성과 LP relaxation 계산을 포함한 실제 경과시간
- `num_vars`, `num_constraints`: 모델 크기
- `status_name`: `LP_OPTIMAL` 또는 `LP_NO_OPTIMUM`

`best_bound`, `mip_gap`, `objective`는 MIP를 실행하지 않으므로 기록 대상이 아니다.
