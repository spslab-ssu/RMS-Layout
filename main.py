"""RMS Layout 실행 진입점.

이 파일은 V2GRO의 main.py와 같은 역할을 한다.
계산 로직을 직접 담지 않고, 설정 -> 데이터 -> 모델 -> 출력 -> 시각화
순서대로 각 모듈을 호출한다.
"""

import config
from Src.data import load_instance
from Src.milp import solve_milp
from Src.output import save_solution
from Src.visualize import draw_layouts


def main() -> None:
    instance = load_instance(config)
    solution = solve_milp(instance, config)
    save_solution(solution, config.RESULT_DIR)
    draw_layouts(config.RESULT_DIR, instance)


if __name__ == "__main__":
    main()
