"""Time-expanded network reformulation 실행 진입점.

기존 `main.py`와 `Src/milp.py`는 그대로 두고, network model 실험은
이 파일에서만 호출한다. 협업 중 base MILP 수정과 충돌하지 않게 하기 위한
분리 실행 파일이다.
"""

import config
from Src.data import load_instance
from Src.milp_network import solve_milp
from Src.output import save_solution
from Src.visualize import draw_layouts


# network model 전용 옵션.
# overview의 모델 A처럼 node occupancy w만 binary로 두고,
# transition/sink arc z는 continuous로 둔다.
NETWORK_BINARY_ARCS = False
COMPUTE_LP_RELAXATION_BOUND = True


def main() -> None:
    config.NETWORK_BINARY_ARCS = NETWORK_BINARY_ARCS
    config.COMPUTE_LP_RELAXATION_BOUND = COMPUTE_LP_RELAXATION_BOUND
    instance = load_instance(config)
    solution = solve_milp(instance, config)
    save_solution(solution, config.RESULT_DIR)
    draw_layouts(config.RESULT_DIR, instance)


if __name__ == "__main__":
    main()
