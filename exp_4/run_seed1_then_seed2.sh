#!/usr/bin/env bash
set -euo pipefail

python3 exp/run_experiments.py \
  --manifest exp_4/manifest.csv \
  --output Result/exp_4 \
  --model network \
  --model network_adaptive \
  --seed 1 \
  --time-limit 3600 \
  --mip-gap 0 \
  --network-warm-start

python3 exp/run_experiments.py \
  --manifest exp_4/manifest.csv \
  --output Result/exp_4 \
  --model network \
  --model network_adaptive \
  --seed 2 \
  --time-limit 3600 \
  --mip-gap 0 \
  --network-warm-start
