"""RMS Layout 실행 진입점.

계산 로직을 직접 담지 않고, 설정 -> 데이터 -> 모델 -> 출력 -> 시각화
순서대로 각 모듈을 호출한다.
"""

import config
from Src.data.loader import load_instance
from Src.models.base import solve_milp
from Src.io.output import save_solution
from Src.viz.visualize import draw_layouts


def main() -> None:
    result_dir = config.RESULT_DIR / "base"
    print(f"Running: {config.PROBLEM_TYPE} / {config.RMT_TABLE_NAME} / {config.DEMAND_NAME}")
    print(f"Output dir: {result_dir}")
    instance = load_instance(config)
    solution = solve_milp(instance, config)
    save_solution(solution, result_dir)
    draw_layouts(result_dir, instance)
    print(solution.summary)
    print(solution.cost_breakdown)
    print(f"Result saved to: {result_dir}")


if __name__ == "__main__":
    main()
