"""Verify the distance-cost transition around 16 / 3."""

from experiments.estimate_single_part_relocation_cost import OUTPUT_DIR, solve_case, write_csv


def main() -> None:
    values = [5.32, 16.0 / 3.0, 5.34]
    rows = [solve_case(cap=1, fixed_cost=0.0, distance_cost=value) for value in values]
    write_csv(OUTPUT_DIR / "distance_cost_breakpoint_refinement.csv", rows)


if __name__ == "__main__":
    main()
