# -*- coding: utf-8 -*-
"""Data/youssef_2007 데이터셋 검증 스크립트 (솔버 실행 없음).

1) youssef_2007 로드: 집합 크기, module별 재구성비 검산, 자원파일 미로드 확인
2) 회귀: 기존 multi_part의 재구성비가 예전(전역 단가) 공식과 동일한지 확인
3) 용량 pre-check: 기간별 필요 기계 수 하한 <= install 슬롯 수(20)
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import config  # noqa: E402
from Src.data import load_instance  # noqa: E402


def make_shim(problem_name: str, **overrides) -> SimpleNamespace:
    """config 모듈을 복사한 뒤 데이터셋 경로만 바꾼 shim을 만든다."""
    shim = SimpleNamespace(**{k: getattr(config, k) for k in dir(config) if k.isupper()})
    problem_dir = config.DATA_DIR / problem_name
    shim.PROBLEM_NAME = problem_name
    shim.LOCATION_FILE = problem_dir / "locations.csv"
    shim.CONFIGURATION_FILE = problem_dir / "configurations.csv"
    shim.PRODUCTION_RATE_FILE = problem_dir / "production_rates.csv"
    shim.DEMAND_FILE = problem_dir / "demands.csv"
    shim.PARAMETER_FILE = problem_dir / "parameters.csv"
    shim.SHARED_RESOURCE_FILE = problem_dir / "shared_resources.csv"
    shim.RESOURCE_REQUIREMENT_FILE = problem_dir / "resource_requirements.csv"
    shim.MODULE_COST_FILE = problem_dir / "module_costs.csv"
    for key, value in overrides.items():
        setattr(shim, key, value)
    return shim


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "OK " if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    if not condition:
        raise SystemExit(f"검증 실패: {name} {detail}")


# ---------------------------------------------------------------- 1) youssef_2007
print("=" * 60)
print("1) youssef_2007 로드 검증")
print("=" * 60)
inst = load_instance(make_shim("youssef_2007", SHARED_RESOURCE_MODE="off"))

check("install 위치 20개", len(inst.install_locations) == 20, f"{len(inst.install_locations)}")
check("전체 위치 22개(start/end 포함)", len(inst.all_locations) == 22)
check("기간 1..5", inst.periods == [1, 2, 3, 4, 5], f"{inst.periods}")
check("operations 1..12", inst.operations == list(range(1, 13)), f"{inst.operations}")
check("configuration 9개", len(inst.configurations) == 9, f"{sorted(inst.configurations)}")
check("feasible_pairs 56개", len(inst.feasible_pairs) == 56, f"{len(inst.feasible_pairs)}")
check("공유자원 미로드", inst.shared_resource_file is None and not inst.shared_resource_capacity)

# MC15 전용 op 4개 (급소)
for op, rate in [(5, 60.0), (8, 180.0), (9, 90.0), (10, 200.0)]:
    holders = [j for (j, l) in inst.feasible_pairs if l == op]
    check(f"op{op}은 MC15 전용 rate={rate:g}", holders == ["MC15"] and inst.production_rate[("MC15", op)] == rate,
          f"{holders}")

# module별 재구성비 검산 (Youssef 내재 단가와 일치해야 함)
expected = {
    ("MC11", "MC12"): 280.0,   # 스핀들 1개 추가
    ("MC12", "MC11"): 140.0,   # 스핀들 1개 제거
    ("MC11", "MC15"): 150.0,   # 4축 추가
    ("MC15", "MC11"): 75.0,    # 4축 제거
    ("MC15", "MC14"): 915.0,   # 스핀들 3개 추가(840) + 4축 제거(75)
    ("MC14", "MC15"): 570.0,   # 4축 추가(150) + 스핀들 3개 제거(420)
    ("MC12", "MC15"): 290.0,   # 4축 추가(150) + 스핀들 제거(140)
    ("MC21", "MC22"): 170.0,   # M2 스핀들 1개 추가
    ("MC24", "MC21"): 255.0,   # M2 스핀들 3개 제거
    ("MC11", "MC14"): 840.0,   # 스핀들 3개 추가
}
for pair, value in expected.items():
    actual = inst.reconfiguration_cost.get(pair)
    check(f"재구성비 {pair[0]}->{pair[1]} = {value:g}", actual == value, f"actual={actual}")

check("M1<->M2 교차 재구성 금지", ("MC11", "MC21") not in inst.reconfiguration_cost
      and ("MC21", "MC11") not in inst.reconfiguration_cost)
same_machine_pairs = [k for k in inst.reconfiguration_cost if inst.machine[k[0]] != inst.machine[k[1]]]
check("교차 타입 키 0개", len(same_machine_pairs) == 0, f"{same_machine_pairs[:3]}")

# ---------------------------------------------------------------- 2) 회귀 (multi_part fallback)
print()
print("=" * 60)
print("2) 회귀 검증: multi_part 재구성비 = 예전 전역 단가 공식")
print("=" * 60)
mp = load_instance(make_shim("multi_part"))
add = mp.parameters["add_module_cost"]
rem = mp.parameters["remove_module_cost"]
old_formula = {}
for prev in mp.configurations:
    for nxt in mp.configurations:
        if mp.machine[prev] != mp.machine[nxt]:
            continue
        a = mp.modules[nxt] - mp.modules[prev]
        r = mp.modules[prev] - mp.modules[nxt]
        old_formula[(prev, nxt)] = add * len(a) + rem * len(r)
check("multi_part 재구성비 dict 동일 (fallback 불변)", mp.reconfiguration_cost == old_formula,
      f"{len(mp.reconfiguration_cost)}쌍")

sp = load_instance(make_shim("single_part"))
check("single_part 로드 정상 (기존 동작)", len(sp.configurations) > 0 and len(sp.reconfiguration_cost) > 0,
      f"configs={len(sp.configurations)}, pairs={len(sp.reconfiguration_cost)}")

# ---------------------------------------------------------------- 3) 용량 pre-check
print()
print("=" * 60)
print("3) 용량 pre-check: 기간별 필요 기계 수 하한 <= 20")
print("=" * 60)
best_rate = {}
for (j, l), rate in inst.production_rate.items():
    best_rate[l] = max(best_rate.get(l, 0.0), rate)

import pandas as pd  # noqa: E402
demand_df = pd.read_csv(config.DATA_DIR / "youssef_2007" / "demands.csv")
op_demand: dict[tuple[int, int], float] = {}
for row in demand_df.itertuples(index=False):
    route = [int(op) for op in str(row.operation_sequence).split(">")]
    for t in inst.periods:
        d = float(getattr(row, f"period{t}"))
        if d <= 0:
            continue
        for op in route:
            op_demand[(t, op)] = op_demand.get((t, op), 0.0) + d

print(f"{'기간':>4} {'하한합계':>8}  op별 하한")
for t in inst.periods:
    bounds = {op: math.ceil(op_demand[(t, op)] / best_rate[op])
              for (tt, op) in op_demand if tt == t}
    total = sum(bounds.values())
    detail = ", ".join(f"op{op}:{n}" for op, n in sorted(bounds.items()) if n > 1)
    print(f"{t:>4} {total:>8}  (2대 이상만: {detail or '없음'})")
    check(f"기간 {t} 하한 {total} <= 20", total <= 20)

print()
print("모든 검증 통과 — 데이터셋과 로더 패치가 정상입니다.")
