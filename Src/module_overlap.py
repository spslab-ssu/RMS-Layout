"""싱글파트 RMS의 보조 모듈 중복률 민감도 분석 도구.

생산률, 수요, 설비 가격과 레이아웃은 그대로 두고 configuration별
auxiliary_modules 열만 통제해 모듈 공용화의 순수 효과를 측정한다.
"""

from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Iterable

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


def parse_modules(value) -> set[int]:
    if pd.isna(value) or str(value).strip() == "":
        return set()
    text = str(value).replace(",", ";").replace("/", ";").replace(" ", "")
    return {int(token) for token in text.split(";") if token}


def format_modules(modules: Iterable[int]) -> str:
    return ";".join(str(module) for module in sorted(modules))


def build_controlled_configurations(configurations: pd.DataFrame, overlap_fraction: float) -> pd.DataFrame:
    """각 configuration의 모듈 수를 보존하면서 machine 내 중복률을 통제한다.

    공통 모듈은 machine별 prefix를, 비공통 모듈은 configuration별 전용 ID를
    사용한다. 따라서 0에서는 서로소이고 1에서는 작은 집합이 큰 집합의
    부분집합이 되어 pairwise overlap coefficient가 정확히 0과 1에 도달한다.
    """
    if not 0.0 <= overlap_fraction <= 1.0:
        raise ValueError("overlap_fraction must be between 0 and 1")

    result = configurations.copy()
    machines = list(dict.fromkeys(result["machine"].astype(str)))
    machine_index = {machine: index for index, machine in enumerate(machines, start=1)}

    for row_index, row in result.iterrows():
        machine = str(row["machine"])
        configuration = str(row["configuration"])
        module_count = len(parse_modules(row["auxiliary_modules"]))
        shared_count = int(overlap_fraction * module_count + 0.5)

        common_base = 100_000 + machine_index[machine] * 1_000
        # Configuration 이름 대신 행 번호를 사용해 어떤 문자열 ID에도 안전하다.
        unique_base = 1_000_000 + (row_index + 1) * 1_000
        common = {common_base + slot for slot in range(1, shared_count + 1)}
        unique = {
            unique_base + slot
            for slot in range(1, module_count - shared_count + 1)
        }
        result.at[row_index, "auxiliary_modules"] = format_modules(common | unique)
        # 사람이 CSV만 보아도 생성 규칙을 추적할 수 있게 별도 열은 추가하지 않는다.
        assert configuration

    return result


def calculate_overlap_metrics(configurations: pd.DataFrame) -> dict[str, float | int]:
    """같은 machine의 configuration 쌍에 대한 보조 모듈 중복 지표."""
    overlap_coefficients: list[float] = []
    jaccards: list[float] = []
    symmetric_differences: list[int] = []

    for _, group in configurations.groupby("machine", sort=False):
        sets = [parse_modules(value) for value in group["auxiliary_modules"]]
        for left, right in combinations(sets, 2):
            intersection = len(left & right)
            smaller = min(len(left), len(right))
            union = len(left | right)
            overlap_coefficients.append(intersection / smaller if smaller else 1.0)
            jaccards.append(intersection / union if union else 1.0)
            symmetric_differences.append(len(left ^ right))

    def mean(values: list[float | int]) -> float:
        return sum(values) / len(values) if values else 0.0

    return {
        "configuration_pair_count": len(overlap_coefficients),
        "mean_overlap_coefficient": mean(overlap_coefficients),
        "mean_jaccard_similarity": mean(jaccards),
        "mean_symmetric_difference": mean(symmetric_differences),
    }


def transition_cost_metrics(instance) -> dict[str, float | int]:
    costs = list(instance.reconfiguration_cost.values())
    return {
        "feasible_transition_count": len(costs),
        "mean_feasible_transition_cost": sum(costs) / len(costs) if costs else 0.0,
        "min_feasible_transition_cost": min(costs) if costs else 0.0,
        "max_feasible_transition_cost": max(costs) if costs else 0.0,
    }


def evaluate_reference_transitions(transitions: list[dict], instance) -> float:
    """기준 최적해의 동일 전이들을 새 모듈 비용표로 재평가한다."""
    total = 0.0
    for transition in transitions:
        key = (
            str(transition["from_configuration"]),
            str(transition["to_configuration"]),
        )
        if key not in instance.reconfiguration_cost:
            raise ValueError(f"Reference transition is unavailable in scenario: {key}")
        total += instance.reconfiguration_cost[key]
    return total


def draw_sensitivity_chart(rows: list[dict], output_path: Path) -> None:
    """추가 plotting 의존성 없이 결과 비교 PNG를 생성한다."""
    controlled = sorted(
        (row for row in rows if row["scenario_type"] == "controlled"),
        key=lambda row: row["actual_overlap_coefficient"],
    )
    if not controlled:
        return

    width, height = 1200, 720
    left, right, top, bottom = 115, 55, 120, 105
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 20)
        small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 16)
        title_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 27)
    except OSError:
        font = small = title_font = ImageFont.load_default()

    plot_left, plot_right = left, width - right
    plot_top, plot_bottom = top, height - bottom
    all_y = [float(row[key]) for row in controlled for key in (
        "optimized_reconfiguration_cost", "fixed_reference_reconfiguration_cost"
    )]
    y_max = max(all_y + [1.0]) * 1.12

    def xy(x_value: float, y_value: float) -> tuple[float, float]:
        return (
            plot_left + x_value * (plot_right - plot_left),
            plot_bottom - y_value / y_max * (plot_bottom - plot_top),
        )

    draw.text((width / 2, 30), "Module Overlap Sensitivity - Single-Part Base Model", fill="#172033", font=title_font, anchor="ma")
    for tick in range(6):
        ratio = tick / 5
        y = plot_bottom - ratio * (plot_bottom - plot_top)
        draw.line((plot_left, y, plot_right, y), fill="#dfe5ec", width=1)
        draw.text((plot_left - 12, y), f"{y_max * ratio:,.0f}", fill="#445064", font=small, anchor="rm")
    for tick in range(5):
        ratio = tick / 4
        x = plot_left + ratio * (plot_right - plot_left)
        draw.line((x, plot_top, x, plot_bottom), fill="#edf0f4", width=1)
        draw.text((x, plot_bottom + 16), f"{ratio * 100:.0f}%", fill="#445064", font=small, anchor="ma")
    draw.line((plot_left, plot_top, plot_left, plot_bottom), fill="#333b48", width=2)
    draw.line((plot_left, plot_bottom, plot_right, plot_bottom), fill="#333b48", width=2)

    series = [
        ("optimized_reconfiguration_cost", "Re-optimized solution", "#1665d8", 7, 7),
        # 두 결과가 같아도 아래의 굵은 파란 선이 가장자리에서 보이게 한다.
        ("fixed_reference_reconfiguration_cost", "Fixed reference plan", "#e05252", 3, 4),
    ]
    for series_index, (key, label, color, line_width, radius) in enumerate(series):
        points = [xy(float(row["actual_overlap_coefficient"]), float(row[key])) for row in controlled]
        if len(points) > 1:
            draw.line(points, fill=color, width=line_width)
        for point in points:
            x, y = point
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color, outline="white", width=1)
        legend_x = plot_right - 280
        legend_y = plot_top + 18 + 30 * series_index
        draw.line((legend_x, legend_y, legend_x + 34, legend_y), fill=color, width=line_width)
        draw.text((legend_x + 45, legend_y), label, fill="#263244", font=small, anchor="lm")

    draw.text((width / 2, height - 43), "Mean auxiliary-module overlap coefficient", fill="#263244", font=font, anchor="ma")
    draw.text((plot_left, plot_top - 17), "Reconfiguration cost", fill="#263244", font=font, anchor="ls")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
