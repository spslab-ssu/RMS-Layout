"""RMS Layout 실행 진입점.

계산 로직을 직접 담지 않고, 설정 -> 데이터 -> 모델 -> 출력 -> 시각화
순서대로 각 모듈을 호출한다.
"""

import config
from Src.data.loader import load_instance
from Src.models.milp import solve_milp
from Src.io.output import save_solution
from Src.viz.visualize import draw_layouts


def main() -> None:
    instance = load_instance(config)
    solution = solve_milp(instance, config)
    save_solution(solution, config.RESULT_DIR)
    draw_layouts(config.RESULT_DIR, instance)


if __name__ == "__main__":
    main()
