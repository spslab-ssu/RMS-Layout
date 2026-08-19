"""Print the saved single/multi-part pure-LP gap comparison."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    return parser.parse_args()


def read_json(relative_path: str) -> dict:
    path = ROOT / relative_path
    if not path.exists():
        raise FileNotFoundError(f"Saved benchmark result not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def lp_gap_percent(incumbent: float, lp_bound: float) -> float:
    return 100.0 * (incumbent - lp_bound) / incumbent


def build_rows() -> list[dict]:
    single_main = read_json(
        "results/relocation_strategy_comparison_single_300s/main_300s/benchmark_summary.json"
    )
    single_yh = read_json(
        "results/relocation_strategy_comparison_single_300s/yh_240_60/benchmark_summary.json"
    )
    multi_main = read_json(
        "results/relocation_strategy_comparison_300s/main_weighted/benchmark_summary.json"
    )
    multi_yh_lp = read_json(
        "results/relocation_strategy_comparison_300s/yh_exact_physical_rerun/benchmark_summary.json"
    )
    multi_yh_best = read_json(
        "results/multi_part_relocation_cost_estimation/count_cap_refined_stage2_valid/case_summary.json"
    )

    raw = [
        ("single", "main", single_main["pure_lp_bound"], single_main["objective"], single_main["status"]),
        (
            "single",
            "yh",
            single_yh["pure_lp_bound"],
            single_yh["primary_objective"],
            single_yh["primary_status"],
        ),
        (
            "multi",
            "main",
            multi_main["pure_lp_bound"],
            multi_main["primary_objective"],
            multi_main["mip_status"],
        ),
        (
            "multi",
            "yh",
            multi_yh_lp["pure_lp_bound"],
            multi_yh_best["base_system_cost"],
            multi_yh_best["primary_status"],
        ),
    ]
    return [
        {
            "problem": problem,
            "formulation": formulation,
            "pure_lp_bound": float(bound),
            "best_incumbent": float(incumbent),
            "lp_gap_percent": lp_gap_percent(float(incumbent), float(bound)),
            "mip_status": status,
        }
        for problem, formulation, bound, incumbent, status in raw
    ]


def print_table(rows: list[dict]) -> None:
    headers = ("Problem", "Model", "Pure LP bound", "Best incumbent", "LP Gap", "MIP status")
    formatted = [
        (
            row["problem"],
            row["formulation"],
            f'{row["pure_lp_bound"]:,.6f}',
            f'{row["best_incumbent"]:,.0f}',
            f'{row["lp_gap_percent"]:.6f}%',
            row["mip_status"],
        )
        for row in rows
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in formatted))
        for index in range(len(headers))
    ]
    print("  ".join(value.ljust(widths[index]) for index, value in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in formatted:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
    print()
    print("LP Gap = (best incumbent - pure LP bound) / best incumbent * 100")
    print("Lower is better. OPTIMAL means the incumbent is proven; TIME_LIMIT is best-known only.")
    print("Multi yh uses the updated feasible incumbent 35,651 from the cap-assisted sensitivity run.")


def main() -> None:
    args = parse_args()
    rows = build_rows()
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print_table(rows)


if __name__ == "__main__":
    main()
