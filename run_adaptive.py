"""Adaptive layout(relocation) 실행 진입점.

config.ADAPTIVE_MODE(off/separate/joint)와 ALPHA/BETA에 따라 기간 경계 기계 이동을 허용한다.
base(main.py)·network(run_network.py)와 분리해 충돌 없이 실험한다.
"""

import config
from Src.data import load_instance
from Src.milp_adaptive import solve_milp
from Src.output import save_solution
from Src.visualize import draw_layouts


def main() -> None:
    instance = load_instance(config)
    solution = solve_milp(instance, config)
    save_solution(solution, config.RESULT_DIR)
    draw_layouts(config.RESULT_DIR, instance)


if __name__ == "__main__":
    main()
