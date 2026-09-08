# -*- coding: utf-8 -*-
"""youssef_2007 데이터셋 100초 정찰 솔브 (config.py 무변경, override로 실행)."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import config  # noqa: E402
from Src.data import load_instance  # noqa: E402
from Src.milp import solve_milp  # noqa: E402
from Src.output import save_solution  # noqa: E402


def make_shim() -> SimpleNamespace:
    shim = SimpleNamespace(**{k: getattr(config, k) for k in dir(config) if k.isupper()})
    problem_dir = config.DATA_DIR / "youssef_2007"
    shim.PROBLEM_NAME = "youssef_2007"
    shim.LOCATION_FILE = problem_dir / "locations.csv"
    shim.CONFIGURATION_FILE = problem_dir / "configurations.csv"
    shim.PRODUCTION_RATE_FILE = problem_dir / "production_rates.csv"
    shim.DEMAND_FILE = problem_dir / "demands.csv"
    shim.PARAMETER_FILE = problem_dir / "parameters.csv"
    shim.SHARED_RESOURCE_FILE = problem_dir / "shared_resources.csv"       # 없음 -> 미로드
    shim.RESOURCE_REQUIREMENT_FILE = problem_dir / "resource_requirements.csv"
    shim.MODULE_COST_FILE = problem_dir / "module_costs.csv"
    shim.RESULT_DIR = config.BASE_DIR / "Result" / "youssef_2007"
    shim.SHARED_RESOURCE_MODE = "off"
    shim.TIME_LIMIT = 100
    shim.MIP_GAP = 0.0
    shim.USE_WARM_START = False
    return shim


def main() -> None:
    shim = make_shim()
    instance = load_instance(shim)
    print(f"[load] P={len(instance.install_locations)} J={len(instance.configurations)} "
          f"L={len(instance.operations)} T={len(instance.periods)} pairs={len(instance.feasible_pairs)} "
          f"arcs={len(instance.route_arcs)}")

    solution = solve_milp(instance, shim)
    save_solution(solution, shim.RESULT_DIR)

    s = solution.summary
    print()
    print("=" * 60)
    print("100초 정찰 결과")
    print("=" * 60)
    for key in ["status", "objective", "best_bound", "mip_gap", "runtime_seconds",
                "lp_relaxation_bound", "num_binary_vars", "num_integer_vars",
                "num_variables", "num_constraints"]:
        if key in s:
            print(f"  {key:>22}: {s[key]}")
    print()
    print("  cost breakdown:")
    for key, value in solution.cost_breakdown.items():
        print(f"  {key:>22}: {value:,.1f}")
    print()
    n_machines = len(solution.purchased_machines)
    n_reconfigs = len(solution.reconfigurations)
    mc15 = sum(1 for m in solution.purchased_machines if str(m.get("configuration", "")).upper() == "MC15")
    by_machine: dict[str, int] = {}
    for m in solution.purchased_machines:
        cfg = str(m.get("configuration", "?"))
        by_machine[cfg] = by_machine.get(cfg, 0) + 1
    print(f"  구매 기계: {n_machines}대 {dict(sorted(by_machine.items()))}")
    print(f"  (구매 시점 MC15: {mc15}대) / 재구성 이벤트: {n_reconfigs}건")
    if solution.reconfigurations:
        for r in solution.reconfigurations[:10]:
            print(f"    reconfig: {r}")
    print(f"\n  결과 저장: {shim.RESULT_DIR}")


if __name__ == "__main__":
    main()
