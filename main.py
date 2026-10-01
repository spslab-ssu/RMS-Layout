"""RMS Layout 실행 진입점.

계산 로직을 직접 담지 않고, 설정 -> 데이터 -> 모델 -> 출력 -> 시각화
순서대로 각 모듈을 호출한다.

풀 모형은 config.MODEL 로 고른다. ("base" | "z" | "w")
"""

import config
from Src.data import load_instance
from Src.output import save_solution
from Src.visualize import draw_layouts

# MODEL 값 -> (모형이 있는 모듈, 화면에 찍을 이름)
MODELS = {
    "base": ("Src.milp", "논문 원형"),
    "z": ("Src.milp_adaptive", "adaptive z 인코딩"),
    "w": ("base_adaptive", "adaptive w 정식화"),
}


def main() -> None:
    model = str(getattr(config, "MODEL", "base")).lower()
    if model not in MODELS:
        raise ValueError(f"MODEL 은 {list(MODELS)} 중 하나여야 한다 (지금: {model!r})")
    module_name, label = MODELS[model]
    solve_milp = __import__(module_name, fromlist=["solve_milp"]).solve_milp

    mode = str(getattr(config, "ADAPTIVE_MODE", "off")).lower()
    print(f"모형 {model} ({label}) | 데이터 {config.PROBLEM_NAME} | "
          f"시간제한 {config.TIME_LIMIT}s | MIPGap {config.MIP_GAP}")
    if model == "base" and mode != "off":
        print(f"  주의: base 모형은 위치 고정이다. ADAPTIVE_MODE={mode} 는 무시된다.")
    elif model != "base":
        print(f"  이동 정책 {mode} | alpha {config.ALPHA} beta {config.BETA}")

    instance = load_instance(config)
    solution = solve_milp(instance, config)
    save_solution(solution, config.RESULT_DIR)
    draw_layouts(config.RESULT_DIR, instance)


if __name__ == "__main__":
    main()
