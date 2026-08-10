"""Full adaptive layout network model 실행 진입점."""

import config
from Src.data.loader import load_instance
from Src.io.output import save_solution
from Src.models.network_adaptive import solve_milp
from Src.viz.visualize import draw_layouts


NETWORK_BINARY_ARCS = True
COMPUTE_LP_RELAXATION_BOUND = True


def main() -> None:
    result_dir = config.RESULT_DIR / "network_adaptive"
    print(f"Running: {config.PROBLEM_TYPE} / {config.RMT_TABLE_NAME} / {config.DEMAND_NAME}")
    print(f"Output dir: {result_dir}")
    config.NETWORK_BINARY_ARCS = NETWORK_BINARY_ARCS
    config.COMPUTE_LP_RELAXATION_BOUND = COMPUTE_LP_RELAXATION_BOUND
    instance = load_instance(config)
    solution = solve_milp(instance, config)
    save_solution(solution, result_dir)
    draw_layouts(result_dir, instance)
    print(solution.summary)
    print(solution.cost_breakdown)
    print(f"Result saved to: {result_dir}")

if __name__ == "__main__":
    main()
