from __future__ import annotations

from pathlib import Path

import pandas as pd
from pandas.errors import EmptyDataError
from PIL import Image, ImageDraw, ImageFont


def draw_layouts(result_dir: Path, instance) -> None:
    """Result CSV를 읽어서 period별 layout과 비용 이벤트를 그림으로 만든다."""
    states_path = result_dir / "machine_states.csv"
    flows_path = result_dir / "material_flows.csv"
    reconfigs_path = result_dir / "reconfigurations.csv"
    purchases_path = result_dir / "purchased_machines.csv"
    if not states_path.exists() or states_path.stat().st_size == 0:
        return

    states = _read_csv_or_empty(states_path)
    flows = _read_csv_or_empty(flows_path)
    reconfigs = _read_csv_or_empty(reconfigs_path)
    purchases = _read_csv_or_empty(purchases_path)
    if states.empty:
        return

    figure_dir = result_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    renderer = _LayoutRenderer(instance.locations)
    first_period = min(instance.periods) if instance.periods else 1

    images = []
    for period in instance.periods:
        image = renderer.render(
            states=states[states["period"] == period],
            flows=flows[flows["period"] == period] if not flows.empty else flows,
            reconfigs=reconfigs[reconfigs["period"] == period] if not reconfigs.empty else reconfigs,
            purchases=purchases if period == first_period else pd.DataFrame(),
            title=f"RMS layout - {instance.problem_name} - period {period}",
        )
        image.save(figure_dir / f"layout_period_{period}.png")
        images.append(image)
    _combine_images(images, figure_dir / "layout_all_periods.png")


def _read_csv_or_empty(path: Path) -> pd.DataFrame:
    """빈 결과 CSV는 pandas EmptyDataError 대신 빈 DataFrame으로 처리한다."""
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except EmptyDataError:
        return pd.DataFrame()


class _LayoutRenderer:
    """PIL 기반 간단 layout renderer."""

    def __init__(self, locations: dict[int, dict[str, float | str]]) -> None:
        self.locations = locations
        xs = [float(row["x"]) for row in locations.values()]
        ys = [float(row["y"]) for row in locations.values()]
        self.min_x, self.max_x = min(xs), max(xs)
        self.min_y, self.max_y = min(ys), max(ys)
        self.width, self.height = 1900, 1050
        self.margin = 150
        self.box_w, self.box_h = 112, 68
        span_x = max(1.0, self.max_x - self.min_x)
        span_y = max(1.0, self.max_y - self.min_y)
        self.scale = min((self.width - 2 * self.margin) / span_x, (self.height - 2 * self.margin) / span_y)
        self.font = ImageFont.load_default()

    def xy(self, location: int) -> tuple[float, float]:
        loc = self.locations[location]
        x = self.margin + (float(loc["x"]) - self.min_x) * self.scale
        y = self.height - (self.margin + (float(loc["y"]) - self.min_y) * self.scale)
        return x, y

    def render(self, states: pd.DataFrame, flows: pd.DataFrame, reconfigs: pd.DataFrame, purchases: pd.DataFrame, title: str) -> Image.Image:
        image = Image.new("RGB", (self.width, self.height), "white")
        draw = ImageDraw.Draw(image)
        draw.text((35, 28), title, fill="#111111", font=self.font)
        self._draw_legend(draw)

        for idx, row in enumerate(flows.itertuples(index=False)):
            self._draw_arrow(
                draw,
                self.xy(int(row.from_location)),
                self.xy(int(row.to_location)),
                f"flow {float(row.flow):g}",
                idx,
                max(1, min(5, int(1 + float(row.flow) / 20))),
                fill="#9a9a9a",
            )

        self._draw_relocation_events(draw, reconfigs)

        state_by_location = {int(row.location): row for row in states.itertuples(index=False)}
        purchase_locations = {int(row.location) for row in purchases.itertuples(index=False)} if not purchases.empty else set()
        reconfigured = {int(row.location) for row in reconfigs.itertuples(index=False)} if not reconfigs.empty else set()
        relocated_to = {int(row.to_location) for row in reconfigs.itertuples(index=False) if _row_float(row, "relocation_cost") > 0} if not reconfigs.empty else set()

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
                fill = "#fff4db" if location in reconfigured else "white"
                outline = "#c62828" if location in relocated_to else ("#2e7d32" if location in purchase_locations else "#222222")
                width = 5 if location in relocated_to or location in purchase_locations else 2
                draw.rectangle(box, fill=fill, outline=outline, width=width)
                self._draw_text(draw, (x, y), [f"{location}, {row.configuration}", f"op {int(row.operation)}", f"v={float(row.flow):g}"])
                badges = []
                if location in purchase_locations:
                    badges.append(("BUY", "#2e7d32"))
                if location in reconfigured:
                    badges.append(("RECFG", "#ef6c00"))
                if location in relocated_to:
                    badges.append(("MOVE", "#c62828"))
                self._draw_badges(draw, box, badges)
            else:
                self._draw_dashed_box(draw, box)
                self._draw_text(draw, (x, y), [str(location)])
        return image

    def _draw_legend(self, draw: ImageDraw.ImageDraw) -> None:
        items = [("BUY", "#2e7d32"), ("RECFG", "#ef6c00"), ("MOVE", "#c62828"), ("flow", "#9a9a9a")]
        x, y = 35, 58
        for label, color in items:
            draw.rectangle((x, y, x + 62, y + 22), fill=color, outline=color)
            draw.text((x + 8, y + 6), label, fill="white", font=self.font)
            x += 84

    def _draw_relocation_events(self, draw: ImageDraw.ImageDraw, reconfigs: pd.DataFrame) -> None:
        if reconfigs.empty or "relocation_cost" not in reconfigs.columns:
            return
        moved = reconfigs[reconfigs["relocation_cost"].fillna(0).astype(float) > 0]
        for idx, row in enumerate(moved.itertuples(index=False)):
            start = self.xy(int(row.from_location))
            end = self.xy(int(row.to_location))
            label = f"move {int(row.from_location)}->{int(row.to_location)} / c={_row_float(row, 'relocation_cost'):g}"
            self._draw_arrow(draw, start, end, label, idx, 7, fill="#c62828", pad=70, label_fill="#c62828")

    def _draw_text(self, draw: ImageDraw.ImageDraw, center: tuple[float, float], lines: list[str]) -> None:
        x, y = center
        line_h = 12
        total_h = line_h * len(lines)
        for idx, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=self.font)
            draw.text((x - (bbox[2] - bbox[0]) / 2, y - total_h / 2 + idx * line_h), line, fill="#111111", font=self.font)

    def _draw_badges(self, draw: ImageDraw.ImageDraw, box: tuple[float, float, float, float], badges: list[tuple[str, str]]) -> None:
        if not badges:
            return
        x1, y1, x2, _ = box
        y = y1 - 24
        for idx, (label, color) in enumerate(badges):
            x = x1 + idx * 48
            draw.rounded_rectangle((x, y, x + 44, y + 18), radius=4, fill=color, outline=color)
            draw.text((x + 5, y + 5), label, fill="white", font=self.font)

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

    def _draw_arrow(
        self,
        draw: ImageDraw.ImageDraw,
        start: tuple[float, float],
        end: tuple[float, float],
        label: str,
        offset_idx: int,
        width_px: int,
        fill: str = "#555555",
        pad: int = 48,
        label_fill: str = "#111111",
    ) -> None:
        x1, y1 = start
        x2, y2 = end
        dx, dy = x2 - x1, y2 - y1
        length = (dx * dx + dy * dy) ** 0.5
        if length == 0:
            return
        nx, ny = -dy / length, dx / length
        offset = (offset_idx % 5 - 2) * 4
        ux, uy = dx / length, dy / length
        start = (x1 + ux * pad + nx * offset, y1 + uy * pad + ny * offset)
        end = (x2 - ux * pad + nx * offset, y2 - uy * pad + ny * offset)
        draw.line((*start, *end), fill=fill, width=width_px)
        self._draw_arrow_head(draw, start, end, fill=fill)
        mx, my = (start[0] + end[0]) / 2 + nx * 10, (start[1] + end[1]) / 2 + ny * 10
        bbox = draw.textbbox((mx, my), label, font=self.font)
        draw.rectangle((bbox[0] - 3, bbox[1] - 2, bbox[2] + 3, bbox[3] + 2), fill="white")
        draw.text((mx, my), label, fill=label_fill, font=self.font)

    @staticmethod
    def _draw_arrow_head(draw: ImageDraw.ImageDraw, start: tuple[float, float], end: tuple[float, float], fill: str = "#555555") -> None:
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
        draw.polygon([p1, p2, p3], fill=fill)


def _row_float(row, field: str) -> float:
    value = getattr(row, field, 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
