from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import config
from Src.base_milp import solve_base_milp
from Src.data import load_instance
from Src.milp import solve_milp
from Src.output import save_solution
from Src.visualize import draw_layouts


FORMULATIONS = ("base", "network", "network_mir")
REFERENCE = {
    "single_part": {"paper_reported": 23082.0, "best_known": 22910.0},
    "multi_part": {"paper_reported": 36006.0, "best_known": 35775.0},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare the paper base formulation with network reformulations."
    )
    parser.add_argument(
        "--problem", choices=tuple(REFERENCE), default="single_part"
    )
    parser.add_argument(
        "--formulation",
        action="append",
        choices=FORMULATIONS,
        help="Repeat to select formulations; default: all.",
    )
    parser.add_argument("--time-limit", type=float, default=120.0)
    parser.add_argument("--mip-gap", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--threads", type=int, default=0)
    parser.add_argument("--solver-output", action="store_true")
    parser.add_argument("--skip-layouts", action="store_true")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Default: results/comparison/<problem>/seed_<seed>.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    selected = args.formulation or list(FORMULATIONS)
    output_dir = args.output_dir or (
        config.BASE_DIR
        / "results"
        / "comparison"
        / args.problem
        / f"seed_{args.seed}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    solutions: dict[str, object] = {}
    for formulation in selected:
        print(f"\n=== {formulation}: pure LP ===")
        lp_solution, _ = _solve(
            problem=args.problem,
            formulation=formulation,
            lp_relaxation=True,
            args=args,
        )
        print(f"\n=== {formulation}: MIP ===")
        mip_solution, instance = _solve(
            problem=args.problem,
            formulation=formulation,
            lp_relaxation=False,
            args=args,
        )
        solutions[formulation] = mip_solution

        formulation_dir = output_dir / formulation
        save_solution(mip_solution, formulation_dir)
        if not args.skip_layouts and mip_solution.summary.get("solution_count", 0):
            draw_layouts(formulation_dir, instance)
        rows.append(_comparison_row(formulation, lp_solution, mip_solution, args))

    _add_base_deltas(rows)
    _write_table(rows, output_dir / "formulation_comparison.csv")
    (output_dir / "formulation_comparison.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_markdown(rows, output_dir / "formulation_comparison.md")
    _write_solution_differences(solutions, output_dir / "solution_differences.json")
    print(f"\nComparison saved to: {output_dir}")


def _solve(problem: str, formulation: str, lp_relaxation: bool, args):
    profile = "network_mir" if formulation == "network_mir" else "network"
    settings = config.build_config(
        problem_name=problem,
        profile=profile,
        TIME_LIMIT=args.time_limit,
        MIP_GAP=args.mip_gap,
        OUTPUT_FLAG=1 if args.solver_output else 0,
        SEED=args.seed,
        THREADS=args.threads,
        LP_RELAXATION=lp_relaxation,
        USE_SHARED_RESOURCES=False,
        OPTIMIZE_SHARED_RESOURCE_CAPACITY=False,
    )
    instance = load_instance(settings)
    solution = (
        solve_base_milp(instance, settings)
        if formulation == "base"
        else solve_milp(instance, settings)
    )
    return solution, instance


def _comparison_row(formulation: str, lp_solution, mip_solution, args) -> dict:
    lp = lp_solution.summary
    mip = mip_solution.summary
    costs = mip_solution.cost_breakdown
    reference = REFERENCE[args.problem]
    return {
        "problem": args.problem,
        "formulation": formulation,
        "seed": args.seed,
        "time_limit": args.time_limit,
        "paper_reported_objective": reference["paper_reported"],
        "best_known_objective": reference["best_known"],
        "lp_status": lp["status_name"],
        "pure_lp_bound": lp.get("objective", ""),
        "pure_lp_gap_vs_best_percent": _gap(reference["best_known"], lp.get("objective")),
        "lp_runtime_seconds": _rounded(lp.get("runtime_seconds")),
        "mip_status": mip["status_name"],
        "mip_objective": mip.get("objective", ""),
        "mip_best_bound": mip.get("lower_bound", ""),
        "mip_gap": mip.get("mip_gap", ""),
        "mip_runtime_seconds": _rounded(mip.get("runtime_seconds")),
        "branch_and_bound_nodes": mip.get("node_count", ""),
        "binary_variables": mip["model_size"]["binary_variables"],
        "total_variables": mip["model_size"]["variables"],
        "constraints": mip["model_size"]["constraints"],
        "purchase_cost": costs.get("purchase_cost", ""),
        "reconfiguration_cost": costs.get("reconfiguration_cost", ""),
        "material_handling_cost": costs.get("material_handling_cost", ""),
        "purchased_machine_count": len(mip_solution.purchased_machines),
        "reconfiguration_count": len(mip_solution.reconfigurations),
        "objective_delta_vs_base": "",
        "lp_bound_improvement_vs_base": "",
        "binary_reduction_vs_base": "",
        "runtime_ratio_vs_base": "",
    }


def _add_base_deltas(rows: list[dict]) -> None:
    base = next((row for row in rows if row["formulation"] == "base"), None)
    if base is None:
        return
    for row in rows:
        row["objective_delta_vs_base"] = _difference(
            row["mip_objective"], base["mip_objective"]
        )
        row["lp_bound_improvement_vs_base"] = _difference(
            row["pure_lp_bound"], base["pure_lp_bound"]
        )
        row["binary_reduction_vs_base"] = (
            base["binary_variables"] - row["binary_variables"]
        )
        base_runtime = base["mip_runtime_seconds"]
        row["runtime_ratio_vs_base"] = (
            round(float(row["mip_runtime_seconds"]) / float(base_runtime), 6)
            if base_runtime not in {"", 0, 0.0}
            and row["mip_runtime_seconds"] != ""
            else ""
        )


def _write_solution_differences(solutions: dict[str, object], output: Path) -> None:
    details: dict[str, dict] = {}
    base = solutions.get("base")
    if base is None:
        output.write_text("{}\n", encoding="utf-8")
        return
    base_purchases = _purchase_keys(base)
    base_states = _state_keys(base)
    for name, solution in solutions.items():
        purchases = _purchase_keys(solution)
        states = _state_keys(solution)
        details[name] = {
            "objective": solution.summary.get("objective"),
            "same_objective_as_base": solution.summary.get("objective")
            == base.summary.get("objective"),
            "purchases_only_in_this_solution": sorted(purchases - base_purchases),
            "purchases_only_in_base_solution": sorted(base_purchases - purchases),
            "states_only_in_this_solution": sorted(states - base_states),
            "states_only_in_base_solution": sorted(base_states - states),
        }
    output.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")


def _purchase_keys(solution) -> set[tuple]:
    return {
        (row["location"], row["configuration"], row["initial_operation"])
        for row in solution.purchased_machines
    }


def _state_keys(solution) -> set[tuple]:
    return {
        (row["period"], row["location"], row["configuration"], row["operation"])
        for row in solution.machine_states
    }


def _write_table(rows: list[dict], output: Path) -> None:
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(rows: list[dict], output: Path) -> None:
    columns = [
        "formulation",
        "pure_lp_bound",
        "mip_objective",
        "mip_best_bound",
        "mip_gap",
        "binary_variables",
        "branch_and_bound_nodes",
        "mip_runtime_seconds",
    ]
    lines = [
        "# Formulation comparison",
        "",
        "| " + " | ".join(columns) + " |",
        "|" + "|".join("---" for _ in columns) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row[column]) for column in columns) + " |")
    lines.extend(
        [
            "",
            "The formulations use identical data, seed, thread setting, time limit, and MIP gap.",
            "Different layouts with the same objective are alternative optimal solutions.",
        ]
    )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _gap(reference: float, value) -> float | str:
    if value in {None, ""}:
        return ""
    return round(100.0 * (reference - float(value)) / reference, 6)


def _difference(left, right) -> float | str:
    if left in {None, ""} or right in {None, ""}:
        return ""
    return round(float(left) - float(right), 6)


def _rounded(value) -> float | str:
    return "" if value in {None, ""} else round(float(value), 6)


if __name__ == "__main__":
    main()
