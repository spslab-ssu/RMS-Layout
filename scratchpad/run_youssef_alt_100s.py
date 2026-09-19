# -*- coding: utf-8 -*-
"""youssef_2007 (대안 라우트 A 3 + B 13) — λ 모델(Src/milp_alt.py) 정찰 솔브. config.py 무변경."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import config  # noqa: E402
from Src.data import load_instance  # noqa: E402
from Src.milp_alt import solve_milp  # noqa: E402
from Src.output import save_solution  # noqa: E402

TIME_LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 100


def make_shim() -> SimpleNamespace:
    shim = SimpleNamespace(**{k: getattr(config, k) for k in dir(config) if k.isupper()})
    d = config.DATA_DIR / "youssef_2007"
    shim.PROBLEM_NAME = "youssef_2007_alt"
    for key, fn in [("LOCATION_FILE", "locations.csv"), ("CONFIGURATION_FILE", "configurations.csv"),
                    ("PRODUCTION_RATE_FILE", "production_rates.csv"), ("DEMAND_FILE", "demands.csv"),
                    ("PARAMETER_FILE", "parameters.csv"), ("SHARED_RESOURCE_FILE", "shared_resources.csv"),
                    ("RESOURCE_REQUIREMENT_FILE", "resource_requirements.csv"), ("MODULE_COST_FILE", "module_costs.csv")]:
        setattr(shim, key, d / fn)
    shim.RESULT_DIR = config.BASE_DIR / "Result" / "youssef_2007_alt"
    shim.SHARED_RESOURCE_MODE = "off"
    shim.TIME_LIMIT = TIME_LIMIT
    shim.MIP_GAP = 0.0
    shim.USE_WARM_START = False
    return shim


def main() -> None:
    shim = make_shim()
    inst = load_instance(shim)
    print(f"[load] P={len(inst.install_locations)} J={len(inst.configurations)} L={len(inst.operations)} "
          f"T={inst.periods} pairs={len(inst.feasible_pairs)} arcs={len(inst.route_arcs)} "
          f"대안={ {p: len(r) for p, r in inst.part_routes.items()} }", flush=True)
    sol = solve_milp(inst, shim)
    save_solution(sol, shim.RESULT_DIR)
    s = sol.summary
    print("\n" + "=" * 60 + f"\nλ 모델 {TIME_LIMIT}초 결과\n" + "=" * 60)
    for key in ["status_name", "objective", "best_bound", "mip_gap", "runtime_seconds", "lp_relaxation_bound",
                "num_binary_vars", "num_vars", "num_constraints"]:
        if key in s:
            print(f"  {key:>22}: {s[key]}")
    print("  cost breakdown:")
    for k, v in sol.cost_breakdown.items():
        print(f"  {k:>22}: {v:,.1f}")
    fleet: dict[str, int] = {}
    for m in sol.purchased_machines:
        fleet[str(m.get("configuration"))] = fleet.get(str(m.get("configuration")), 0) + 1
    print(f"  구매 기계: {len(sol.purchased_machines)}대 {dict(sorted(fleet.items()))} / 재구성 {len(sol.reconfigurations)}건")
    print("\n  솔버가 고른 라우트 배분 (λ):")
    for r in s.get("route_shares", []):
        print(f"    {r['part']} t{r['period']}  {r['route']:<28} share={r['share']:.3f}  flow={r['flow']:.1f}")
    print(f"\n  결과 저장: {shim.RESULT_DIR}")


if __name__ == "__main__":
    main()
