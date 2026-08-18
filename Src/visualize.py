from __future__ import annotations

from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


def draw_layouts(result_dir: Path, instance) -> None:
    """Result CSV를 읽어서 논문 Figure 2 스타일의 period별 layout 그림을 만든다."""
    _draw_layout_directory(result_dir, instance, "Final")
    stage_one_dir = result_dir / "stage_1_system_cost"
    stage_two_dir = result_dir / "stage_2_min_relocation"
    if stage_one_dir.exists() and stage_two_dir.exists():
        stage_one_images = _draw_layout_directory(stage_one_dir, instance, "Stage 1 · system cost")
        stage_two_images = _draw_layout_directory(stage_two_dir, instance, "Stage 2 · minimum relocation")
        comparison_dir = result_dir / "figures" / "stage_comparison"
        comparison_dir.mkdir(parents=True, exist_ok=True)
        comparisons = []
        for period, left, right in zip(instance.periods, stage_one_images, stage_two_images):
            comparison = _combine_side_by_side(left, right)
            comparison.save(comparison_dir / f"stage_comparison_period_{period}.png")
            comparisons.append(comparison)
        _combine_images(comparisons, comparison_dir / "stage_comparison_all_periods.png")
        candidates_dir = stage_one_dir / "candidates"
        if candidates_dir.exists():
            for candidate_dir in sorted(candidates_dir.glob("configuration_*")):
                _draw_layout_directory(candidate_dir, instance, candidate_dir.name)


def _draw_layout_directory(result_dir: Path, instance, stage_label: str) -> list[Image.Image]:
    states_path = result_dir / "machine_states.csv"
    flows_path = result_dir / "material_flows.csv"
    reconfigs_path = result_dir / "reconfigurations.csv"
    relocations_path = result_dir / "relocations.csv"
    if not states_path.exists() or states_path.stat().st_size == 0:
        return []

    states = pd.read_csv(states_path)
    flows = pd.read_csv(flows_path) if flows_path.exists() and flows_path.stat().st_size else pd.DataFrame()
    reconfigs = pd.read_csv(reconfigs_path) if reconfigs_path.exists() and reconfigs_path.stat().st_size else pd.DataFrame()
    relocations = pd.read_csv(relocations_path) if relocations_path.exists() and relocations_path.stat().st_size else pd.DataFrame()

    figure_dir = result_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    renderer = _LayoutRenderer(instance.locations)

    images = []
    for period in instance.periods:
        image = renderer.render(
            states=states[states["period"] == period],
            flows=flows[flows["period"] == period] if not flows.empty else flows,
            reconfigs=reconfigs[reconfigs["period"] == period] if not reconfigs.empty else reconfigs,
            relocations=relocations[relocations["period"] == period] if not relocations.empty else relocations,
            title=f"{stage_label} - {instance.problem_name} - period {period}",
        )
        image.save(figure_dir / f"layout_period_{period}.png")
        images.append(image)
    _combine_images(images, figure_dir / "layout_all_periods.png")
    return images


class _LayoutRenderer:
    """PIL 기반 간단 layout renderer."""

    def __init__(self, locations: dict[int, dict[str, float | str]]) -> None:
        self.locations = locations
        xs = [float(row["x"]) for row in locations.values()]
        ys = [float(row["y"]) for row in locations.values()]
        self.min_x, self.max_x = min(xs), max(xs)
        self.min_y, self.max_y = min(ys), max(ys)
        self.width, self.height = 1700, 950
        self.margin = 130
        self.box_w, self.box_h = 92, 58
        span_x = max(1.0, self.max_x - self.min_x)
        span_y = max(1.0, self.max_y - self.min_y)
        self.scale = min((self.width - 2 * self.margin) / span_x, (self.height - 2 * self.margin) / span_y)
        self.font = ImageFont.load_default()

    def xy(self, location: int) -> tuple[float, float]:
        loc = self.locations[location]
        x = self.margin + (float(loc["x"]) - self.min_x) * self.scale
        y = self.height - (self.margin + (float(loc["y"]) - self.min_y) * self.scale)
        return x, y

    def render(self, states: pd.DataFrame, flows: pd.DataFrame, reconfigs: pd.DataFrame, relocations: pd.DataFrame, title: str) -> Image.Image:
        image = Image.new("RGB", (self.width, self.height), "white")
        draw = ImageDraw.Draw(image)
        draw.text((35, 30), title, fill="#111111", font=self.font)

        for idx, row in enumerate(flows.itertuples(index=False)):
            self._draw_arrow(draw, self.xy(int(row.from_location)), self.xy(int(row.to_location)), f"{float(row.flow):g}", idx, max(1, min(5, int(1 + float(row.flow) / 20))))
        for idx, row in enumerate(relocations.itertuples(index=False)):
            self._draw_arrow(
                draw,
                self.xy(int(row.from_location)),
                self.xy(int(row.to_location)),
                "MOVE",
                idx,
                4,
                color="#c0392b",
            )

        state_by_location = {int(row.location): row for row in states.itertuples(index=False)}
        reconfigured = {int(row.location) for row in reconfigs.itertuples(index=False)} if not reconfigs.empty else set()

        for location in sorted(self.locations):
            loc = self.locations[location]
            x, y = self.xy(location)
            box = (x - self.box_w / 2, y - self.box_h / 2, x + self.box_w / 2, y + self.box_h / 2)
            if loc["type"] == "start":
                draw.rectangle(box, fill="#f5f5f5", outline="#222222", width=2)
                self._draw_text(draw, (x, y), [str(location), "Start"])
            elif loc["type"] == "end":
                draw.rectangle(box, fill="#f5f5f5", outline="#222222", width=2)
                self._draw_text(draw, (x, y), [str(location), "End"])
            elif location in state_by_location:
                row = state_by_location[location]
                fill = "#d9d9d9" if location in reconfigured else "white"
                draw.rectangle(box, fill=fill, outline="#222222", width=2)
                self._draw_text(draw, (x, y), [f"{location}, {row.configuration}", f"op {int(row.operation)}", f"v={float(row.flow):g}"])
            else:
                self._draw_dashed_box(draw, box)
                self._draw_text(draw, (x, y), [str(location)])
        return image

    def _draw_text(self, draw: ImageDraw.ImageDraw, center: tuple[float, float], lines: list[str]) -> None:
        x, y = center
        line_h = 12
        total_h = line_h * len(lines)
        for idx, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=self.font)
            draw.text((x - (bbox[2] - bbox[0]) / 2, y - total_h / 2 + idx * line_h), line, fill="#111111", font=self.font)

    def _draw_dashed_box(self, draw: ImageDraw.ImageDraw, box: tuple[float, float, float, float]) -> None:
        x1, y1, x2, y2 = box
        draw.rectangle(box, fill="white")
        dash = 7
        for x in range(int(x1), int(x2), dash * 2):
            draw.line((x, y1, min(x + dash, x2), y1), fill="#777777", width=2)
            draw.line((x, y2, min(x + dash, x2), y2), fill="#777777", width=2)
        for y in range(int(y1), int(y2), dash * 2):
            draw.line((x1, y, x1, min(y + dash, y2)), fill="#777777", width=2)
            draw.line((x2, y, x2, min(y + dash, y2)), fill="#777777", width=2)

    def _draw_arrow(self, draw: ImageDraw.ImageDraw, start: tuple[float, float], end: tuple[float, float], label: str, offset_idx: int, width_px: int, color: str = "#555555") -> None:
        x1, y1 = start
        x2, y2 = end
        dx, dy = x2 - x1, y2 - y1
        length = (dx * dx + dy * dy) ** 0.5
        if length == 0:
            return
        nx, ny = -dy / length, dx / length
        offset = (offset_idx % 5 - 2) * 4
        pad = 48
        ux, uy = dx / length, dy / length
        start = (x1 + ux * pad + nx * offset, y1 + uy * pad + ny * offset)
        end = (x2 - ux * pad + nx * offset, y2 - uy * pad + ny * offset)
        draw.line((*start, *end), fill=color, width=width_px)
        self._draw_arrow_head(draw, start, end, color)
        mx, my = (start[0] + end[0]) / 2 + nx * 10, (start[1] + end[1]) / 2 + ny * 10
        draw.text((mx, my), label, fill=color, font=self.font)

    @staticmethod
    def _draw_arrow_head(draw: ImageDraw.ImageDraw, start: tuple[float, float], end: tuple[float, float], color: str = "#555555") -> None:
        x1, y1 = start
        x2, y2 = end
        dx, dy = x2 - x1, y2 - y1
        length = (dx * dx + dy * dy) ** 0.5
        if length == 0:
            return
        ux, uy = dx / length, dy / length
        left = (-uy, ux)
        size = 10
        p1 = (x2, y2)
        p2 = (x2 - ux * size + left[0] * size * 0.55, y2 - uy * size + left[1] * size * 0.55)
        p3 = (x2 - ux * size - left[0] * size * 0.55, y2 - uy * size - left[1] * size * 0.55)
        draw.polygon([p1, p2, p3], fill=color)


def _combine_images(images: list[Image.Image], output_path: Path) -> None:
    """period별 이미지를 하나의 긴 이미지로 결합한다."""
    if not images:
        return
    gap = 24
    width = max(img.width for img in images)
    height = sum(img.height for img in images) + gap * (len(images) - 1)
    combined = Image.new("RGB", (width, height), "white")
    y = 0
    for img in images:
        combined.paste(img, (0, y))
        y += img.height + gap
    combined.save(output_path)


def _combine_side_by_side(left: Image.Image, right: Image.Image) -> Image.Image:
    gap = 24
    combined = Image.new(
        "RGB",
        (left.width + gap + right.width, max(left.height, right.height)),
        "white",
    )
    combined.paste(left, (0, 0))
    combined.paste(right, (left.width + gap, 0))
    return combined
