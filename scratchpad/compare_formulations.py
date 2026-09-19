# -*- coding: utf-8 -*-
"""Saffar(base) vs network 정식화 시간 비교 — youssef_2007 대안 16행 데이터셋(λ 네이티브).

사용법: python scratchpad/compare_formulations.py [TIME_LIMIT=900] [MIP_GAP=0.0] [SEEDS=1] [VARIANTS=base,network_contArcs] [DATASET=youssef_2007]
같은 인스턴스·같은 시간·warm start 없음으로 순차 실행하고 기록한다:
  - 비용 4항(구매/재구성/MHC/총합) 전체 + period별 (구매는 1기 일괄이라 t1에만)
  - gap, LP relaxation bound, best bound, 이진 변수, 노드 수
  - Gurobi 로그(LogFile)에서 incumbent 궤적과 첫 해 도달 시간
결과: Result/youssef_2007_formulations/summary.json, summary.csv, gurobi_<variant>_seed<k>.log
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import config  # noqa: E402
from Src.data import load_instance  # noqa: E402
from Src import milp as base_milp  # noqa: E402
from Src import milp_network  # noqa: E402

TIME_LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 900
MIP_GAP = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
SEEDS = int(sys.argv[3]) if len(sys.argv) > 3 else 1
WANTED = sys.argv[4].split(",") if len(sys.argv) > 4 else ["base", "network_contArcs"]
DATASET = sys.argv[5] if len(sys.argv) > 5 else "youssef_2007"
DATA = REPO / "Data" / DATASET
OUT = REPO / "Result" / f"{DATASET}_formulations"
DEMAND_FILE = sys.argv[6] if len(sys.argv) > 6 else "demands.csv"   # 예: demands_alternatives16.csv (λ 인스턴스)

ALL_VARIANTS = {
    "base_noReconfig":    (base_milp.solve_milp,    {"ALLOW_RECONFIGURATION": False}),
    "network_noReconfig": (milp_network.solve_milp, {"NETWORK_BINARY_ARCS": False, "ALLOW_RECONFIGURATION": False}),
    "base_noReconfig_lambda":    (base_milp.solve_milp,    {"ALLOW_RECONFIGURATION": False, "FORCE_ROUTE_LAMBDA": True}),
    "network_noReconfig_lambda": (milp_network.solve_milp, {"NETWORK_BINARY_ARCS": False, "ALLOW_RECONFIGURATION": False, "FORCE_ROUTE_LAMBDA": True}),
    "base_lambda":      (base_milp.solve_milp,    {"FORCE_ROUTE_LAMBDA": True}),
    "network_lambda":   (milp_network.solve_milp, {"NETWORK_BINARY_ARCS": False, "FORCE_ROUTE_LAMBDA": True}),
    "base":             (base_milp.solve_milp,    {}),
    "network_contArcs": (milp_network.solve_milp, {"NETWORK_BINARY_ARCS": False}),
    "network_binArcs":  (milp_network.solve_milp, {"NETWORK_BINARY_ARCS": True}),
}


def make_shim(seed: int, logfile: Path, **over) -> SimpleNamespace:
    shim = SimpleNamespace(**{k: getattr(config, k) for k in dir(config) if k.isupper()})
    shim.PROBLEM_NAME = DATASET
    for key, fn in [("LOCATION_FILE", "locations.csv"), ("CONFIGURATION_FILE", "configurations.csv"),
                    ("PRODUCTION_RATE_FILE", "production_rates.csv"), ("DEMAND_FILE", DEMAND_FILE),
                    ("PARAMETER_FILE", "parameters.csv"), ("SHARED_RESOURCE_FILE", "shared_resources.csv"),
                    ("RESOURCE_REQUIREMENT_FILE", "resource_requirements.csv"), ("MODULE_COST_FILE", "module_costs.csv")]:
        setattr(shim, key, DATA / fn)
    shim.SHARED_RESOURCE_MODE = "off"
    shim.USE_WARM_START = False
    shim.OUTPUT_FLAG = 1
    shim.COMPUTE_LP_RELAXATION_BOUND = True
    shim.TIME_LIMIT = TIME_LIMIT
    shim.MIP_GAP = MIP_GAP
    shim.GUROBI_PARAMS = {"Seed": seed, "LogFile": str(logfile)}
    for k, v in over.items():
        setattr(shim, k, v)
    return shim


def per_period_costs(sol, inst) -> dict[int, dict[str, float]]:
    """해의 row list에서 period별 비용을 재구성한다 (구매는 1기 일괄)."""
    c_mh = float(inst.parameters["material_handling_cost"])
    purchase_total = float(sol.cost_breakdown.get("purchase_cost", 0.0))
    out: dict[int, dict[str, float]] = {}
    for t in inst.periods:
        reconf = 0.0
        for r in sol.reconfigurations:
            if r.get("period") != t:
                continue
            cost = r.get("reconfiguration_cost")
            if cost is None:
                cost = inst.reconfiguration_cost.get((r.get("from_configuration"), r.get("to_configuration")), 0.0)
            reconf += float(cost)
        mhc = 0.0
        for fl in sol.material_flows:
            if fl.get("period") != t:
                continue
            if fl.get("flow_cost") is not None:
                mhc += float(fl["flow_cost"])
            else:
                mhc += float(fl["flow"]) * float(inst.distance[(fl["from_location"], fl["to_location"])]) * c_mh
        purchase = purchase_total if t == inst.periods[0] else 0.0
        out[t] = {"purchase": round(purchase, 2), "reconfiguration": round(reconf, 2), "mhc": round(mhc, 2),
                  "total": round(purchase + reconf + mhc, 2)}
    return out


def parse_incumbents(logfile: Path) -> list[dict[str, float]]:
    """Gurobi 로그의 H/* 행(새 incumbent)에서 (시간, incumbent, bound, gap)을 뽑는다."""
    rows = []
    if not logfile.exists():
        return rows
    for line in logfile.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not (line.startswith("H") or line.startswith("*")):
            continue
        tokens = line.split()
        gap_idx = next((i for i, tok in enumerate(tokens) if tok.endswith("%")), None)
        if gap_idx is None or gap_idx < 2 or not tokens[-1].endswith("s"):
            continue
        try:
            rows.append({
                "time_s": float(tokens[-1][:-1]),
                "incumbent": float(tokens[gap_idx - 2]),
                "bound": float(tokens[gap_idx - 1]),
                "gap": float(tokens[gap_idx][:-1]) / 100.0,
            })
        except ValueError:
            continue
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    print(f"TIME_LIMIT={TIME_LIMIT}s  MIP_GAP={MIP_GAP}  SEEDS={SEEDS}  VARIANTS={WANTED}", flush=True)
    for seed in range(SEEDS):
        for name in WANTED:
            solve, over = ALL_VARIANTS[name]
            logfile = OUT / f"gurobi_{name}_{DEMAND_FILE.replace('.csv','')}_seed{seed}.log"
            if logfile.exists():
                logfile.unlink()
            shim = make_shim(seed, logfile, **over)
            inst = load_instance(shim)
            print(f"\n### {name} seed{seed} 시작 (P={len(inst.install_locations)} arcs={len(inst.route_arcs)} "
                  f"대안={ {p: len(r) for p, r in inst.part_routes.items()} })", flush=True)
            t0 = time.time()
            sol = solve(inst, shim)
            wall = time.time() - t0
            s = sol.summary
            traj = parse_incumbents(logfile)
            row = {
                "variant": name, "seed": seed,
                "flags": {"STATE_EQUALS_PURCHASE": bool(getattr(shim, "STATE_EQUALS_PURCHASE", False)),
                          "ALLOW_RECONFIGURATION": bool(getattr(shim, "ALLOW_RECONFIGURATION", True)),
                          "FORCE_ROUTE_LAMBDA": bool(getattr(shim, "FORCE_ROUTE_LAMBDA", False))},
                "status": s.get("status_name"),
                "objective": s.get("objective"), "best_bound": s.get("best_bound"), "gap": s.get("mip_gap"),
                "lp_relaxation_bound": s.get("lp_relaxation_bound"), "lp_seconds": s.get("lp_relaxation_seconds"),
                "runtime_s": round(float(s.get("runtime_seconds", 0)), 1), "wall_s": round(wall, 1),
                "num_binary": s.get("num_binary_vars"), "num_vars": s.get("num_vars"), "num_constraints": s.get("num_constraints"),
                "nodes": s.get("node_count"),
                "purchase_cost": sol.cost_breakdown.get("purchase_cost"),
                "reconfiguration_cost": sol.cost_breakdown.get("reconfiguration_cost"),
                "material_handling_cost": sol.cost_breakdown.get("material_handling_cost"),
                "total_objective": sol.cost_breakdown.get("total_objective"),
                "per_period": per_period_costs(sol, inst) if sol.purchased_machines else {},
                "machines": len(sol.purchased_machines),
                "reconfig_events": len(sol.reconfigurations),
                "routes": {f"{r['part']}t{r['period']}": f"{r['route']}({r['share']})" for r in s.get("route_shares", [])},
                "first_incumbent_s": traj[0]["time_s"] if traj else None,
                "first_incumbent": traj[0]["incumbent"] if traj else None,
                "num_incumbents": len(traj),
                "incumbent_trajectory": traj,
                "logfile": str(logfile),
            }
            rows.append(row)
            print(f"    -> {row['status']} obj={row['objective']} bound={row['best_bound']} gap={row['gap']} "
                  f"LP={row['lp_relaxation_bound']} 첫해={row['first_incumbent_s']}s({row['first_incumbent']}) "
                  f"incumbent수={row['num_incumbents']} nodes={row['nodes']} binary={row['num_binary']}", flush=True)
            print(f"    비용: 구매={row['purchase_cost']} 재구성={row['reconfiguration_cost']} MHC={row['material_handling_cost']} "
                  f"총={row['total_objective']} | period별={row['per_period']}", flush=True)
            print(f"    라우트: {row['routes']}", flush=True)
            (OUT / f"summary_{DEMAND_FILE.replace('.csv','')}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            with open(OUT / "summary.csv", "w", newline="", encoding="utf-8") as fh:
                cols = ["variant", "seed", "status", "objective", "best_bound", "gap", "lp_relaxation_bound", "runtime_s",
                        "num_binary", "num_vars", "nodes", "purchase_cost", "reconfiguration_cost", "material_handling_cost",
                        "total_objective", "machines", "reconfig_events", "first_incumbent_s", "first_incumbent", "num_incumbents"]
                w = csv.DictWriter(fh, fieldnames=cols)
                w.writeheader()
                for r in rows:
                    w.writerow({c: r.get(c) for c in cols})

    print("\n\n==== 정식화 비교 (같은 인스턴스, 제한 %ds) ====" % TIME_LIMIT)
    print(f"{'variant':<18}{'obj':>8}{'bound':>8}{'gap':>7}{'LP':>8}{'첫해(s)':>8}{'binary':>8}{'nodes':>8}  구매/재구성/MHC")
    for r in rows:
        gap = r["gap"]
        print(f"{r['variant']:<18}{(r['objective'] or 0):>8.0f}{(r['best_bound'] or 0):>8.0f}"
              f"{(f'{gap*100:.1f}%' if gap is not None else '-'):>7}{(r['lp_relaxation_bound'] or 0):>8.0f}"
              f"{(r['first_incumbent_s'] if r['first_incumbent_s'] is not None else '-'):>8}{str(r['num_binary'] or '-'):>8}{int(r['nodes'] or 0):>8}"
              f"  {r['purchase_cost']}/{r['reconfiguration_cost']}/{r['material_handling_cost']}")


if __name__ == "__main__":
    main()
