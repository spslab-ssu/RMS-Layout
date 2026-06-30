"""메인논문 Example 1 단일부품 해 비교 스크립트.

목적:
1. 논문 Figure 2(a)의 초기 구매 배치를 강제로 고정한다.
2. 같은 MILP 수식에서 재구성/flow만 다시 최적화한다.
3. 논문 reported cost와 우리 MILP cost를 비교한다.

이 실험으로 확인하려는 점:
- 초기 장비 설치 위치 차이 때문인지
- 같은 초기 배치를 써도 flow/reconfiguration 선택에서 더 낮은 비용이 가능한지
"""

from pathlib import Path

import config
from Src.data import load_instance
from Src.milp import solve_milp
from Src.output import save_solution
from Src.visualize import draw_layouts


# 논문 Figure 2(a)에 보이는 period 1 구매/초기 상태.
# 위치 1~12에 12대가 설치되고 13~16은 비어 있다.
PAPER_INITIAL_PURCHASES = [
    (1, "mc52", 5),
    (2, "mc51", 1),
    (3, "mc31", 17),
    (4, "mc31", 17),
    (5, "mc52", 5),
    (6, "mc51", 1),
    (7, "mc31", 17),
    (8, "mc31", 17),
    (9, "mc52", 5),
    (10, "mc51", 1),
    (11, "mc51", 1),
    (12, "mc31", 17),
]

# 논문 본문 reported cost. 모델 결과와 비교하기 위한 기준값이다.
PAPER_REPORTED = {
    "purchase_cost": 11025.0,
    "reconfiguration_cost": 1925.0,
    "material_handling_cost": 10132.0,
    "total_objective": 23082.0,
    "mhc_by_period": {1: 1792.0, 2: 1960.0, 3: 2760.0, 4: 3620.0},
}


def main() -> None:
    config.PROBLEM_NAME = "single_part"
    config.PROBLEM_DIR = config.DATA_DIR / config.PROBLEM_NAME
    config.LOCATION_FILE = config.PROBLEM_DIR / "locations.csv"
    config.CONFIGURATION_FILE = config.PROBLEM_DIR / "configurations.csv"
    config.PRODUCTION_RATE_FILE = config.PROBLEM_DIR / "production_rates.csv"
    config.DEMAND_FILE = config.PROBLEM_DIR / "demands.csv"
    config.PARAMETER_FILE = config.PROBLEM_DIR / "parameters.csv"
    config.RESULT_DIR = config.BASE_DIR / "Result_paper_initial_fixed"
    config.MIP_GAP = 0.0
    config.FIXED_PURCHASES = PAPER_INITIAL_PURCHASES

    instance = load_instance(config)
    solution = solve_milp(instance, config)
    save_solution(solution, config.RESULT_DIR)
    draw_layouts(config.RESULT_DIR, instance)

    print("\n=== Paper reported ===")
    for key, value in PAPER_REPORTED.items():
        print(key, value)

    print("\n=== MILP with paper initial purchases fixed ===")
    print(solution.summary)
    print(solution.cost_breakdown)

    diff = {
        key: solution.cost_breakdown.get(key, 0.0) - PAPER_REPORTED[key]
        for key in ["purchase_cost", "reconfiguration_cost", "material_handling_cost", "total_objective"]
    }
    print("\n=== Difference: fixed-MILP - paper ===")
    print(diff)
    print(f"\nResult saved to: {config.RESULT_DIR}")


if __name__ == "__main__":
    main()
