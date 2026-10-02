"""RMS Layout 실험용 demand와 실험 manifest를 생성한다.

생성 설계
----------
* part_count: 1, 3, 5, 7
* layout: 기존 layout_18/layout_22와 새 layout_32/layout_37
* overlap: low/high
* utilization: 0.5, 0.75, 1.0, 1.25
* seed: 1..5

기준 demand의 전체 기간 수요량은 utilization 배율을 적용해 유지한다.
다만 demand_1의 기간별 패턴을 그대로 복사하지 않도록 기간별 총량과 부품별
배분을 각각 seed로 재생성한다. 각 기간 총량은 해당 utilization 기준량의
±10% 범위 안에 있고, 네 기간 총합은 정확히 목표 총합과 같다.
"""
from __future__ import annotations

import argparse
import csv
import math
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "Data"
DEMAND_ROOT = DATA_DIR / "demands" / "exp"
LOCATION_ROOT = DATA_DIR / "locations"
RMT_TABLE = "table_1"
PERIODS = (1, 2, 3, 4)
PART_COUNTS = (1, 3, 5, 7)
OVERLAPS = ("low", "high")
UTILIZATIONS = (0.5, 0.75, 1.0, 1.25)
SEEDS = (1, 2, 3, 4, 5)
LAYOUTS = ("layout_18", "layout_22", "layout_32", "layout_37")

# layout 파일명은 설치 칸 수가 아니라 start/end를 포함한 전체 위치 수다.
# layout_18=4x4, layout_22=4x5, layout_32=5x6, layout_37=5x7.
LAYOUT_SHAPES = {
    "layout_18": (4, 4),
    "layout_22": (4, 5),
    "layout_32": (5, 6),
    "layout_37": (5, 7),
}

# 각 operation은 table_1에서 처리 가능한지 검증된 route만 사용한다.
# high는 공통 2->12 흐름을 유지하면서 5/7 part에서 일부 route를 바꾼다.
HIGH_ROUTES = {
    1: ((2, 12, 17),),
    3: ((2, 12, 17), (2, 12, 11), (2, 12, 11, 8)),
    5: ((2, 12, 17), (2, 12, 11), (2, 12, 11, 8), (2, 12, 17, 8), (2, 13, 11)),
    7: ((2, 12, 17), (2, 12, 11), (2, 12, 11, 8), (2, 12, 17, 8),
        (2, 13, 11), (2, 13, 16), (2, 12, 8)),
}

# low는 route 간 operation 중복을 최소화하되, layout_18에서도 처리할 수 있도록
# 전체 고유 operation 수를 14개 이하로 제한한다.
LOW_ROUTES = {
    1: ((2, 12, 17),),
    3: ((2, 12), (17, 11), (1, 6)),
    5: ((2, 12), (17, 11), (1, 6), (20, 3), (14, 5)),
    7: ((2, 12), (17, 11), (1, 6), (20, 3), (14, 5), (4, 10), (19, 7)),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate RMS experiment data and manifest")
    parser.add_argument("--clean", action="store_true", help="기존 exp 생성물만 삭제 후 재생성")
    args = parser.parse_args()
    if args.clean:
        _clean_generated_data()
    for layout_name, (rows, cols) in LAYOUT_SHAPES.items():
        _write_layout_if_missing(layout_name, rows, cols)
    base_period_totals = _read_base_period_totals()
    demand_rows: list[dict[str, str | int | float]] = []
    for part_count in PART_COUNTS:
        part_dir = DEMAND_ROOT / f"p{part_count}"
        part_dir.mkdir(parents=True, exist_ok=True)
        for overlap in OVERLAPS:
            routes = _routes(part_count, overlap)
            for utilization in UTILIZATIONS:
                for seed in SEEDS:
                    rng = random.Random(_seed_value(part_count, overlap, utilization, seed))
                    period_totals = _random_period_totals(base_period_totals, utilization, rng)
                    demands = _allocate_demands(period_totals, part_count, rng)
                    experiment_id = _experiment_id(part_count, overlap, utilization, seed)
                    path = part_dir / f"{experiment_id}.csv"
                    _write_demand(path, demands, routes)
                    demand_rows.append({
                        "experiment_id": experiment_id,
                        "part_count": part_count,
                        "overlap": overlap,
                        "utilization": utilization,
                        "seed": seed,
                        "demand_file": str(path.relative_to(ROOT)),
                        "route_operation_count": len(set(op for route in routes for op in route)),
                        "period_total": ",".join(str(period_totals[t - 1]) for t in PERIODS),
                        "total_demand": sum(period_totals),
                    })
        _write_metadata(part_dir / "metadata.csv", demand_rows_for_part(demand_rows, part_count))

    manifest_rows = []
    for row in demand_rows:
        for layout_name in LAYOUTS:
            manifest_rows.append({**row, "layout_name": layout_name, "rmt_table": RMT_TABLE})
    _write_csv(DEMAND_ROOT / "manifest.csv", manifest_rows)
    _write_csv(DEMAND_ROOT / "demand_metadata.csv", demand_rows)
    print(f"generated demand files: {len(demand_rows)}")
    print(f"generated experiment rows: {len(manifest_rows)}")
    print(f"generated layouts: {', '.join(LAYOUTS)}")


def demand_rows_for_part(rows: list[dict], part_count: int) -> list[dict]:
    return [row for row in rows if int(row["part_count"]) == part_count]


def _clean_generated_data() -> None:
    if not DEMAND_ROOT.exists():
        return
    for path in sorted(DEMAND_ROOT.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()


def _read_base_period_totals() -> list[int]:
    path = DATA_DIR / "demands" / "multi_part" / "demand_1.csv"
    with path.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    return [sum(int(float(row[f"period{period}"])) for row in rows) for period in PERIODS]


def _write_layout_if_missing(name: str, rows: int, cols: int) -> None:
    path = LOCATION_ROOT / f"{name}.csv"
    if path.exists():
        return
    last_location = rows * cols
    data = [{"location": y * cols + x + 1, "x": x, "y": y, "type": "install"}
            for y in range(rows) for x in range(cols)]
    data.extend([
        {"location": last_location + 1, "x": -2, "y": (rows - 1) / 2, "type": "start"},
        {"location": last_location + 2, "x": cols + 1, "y": (rows - 1) / 2, "type": "end"},
    ])
    _write_csv(path, data)


def _routes(part_count: int, overlap: str) -> tuple[tuple[int, ...], ...]:
    return HIGH_ROUTES[part_count] if overlap == "high" else LOW_ROUTES[part_count]


def _seed_value(part_count: int, overlap: str, utilization: float, seed: int) -> int:
    overlap_code = 1 if overlap == "high" else 2
    return seed + part_count * 1000 + overlap_code * 10000 + round(utilization * 100) * 100000


def _random_period_totals(base: list[int], utilization: float, rng: random.Random) -> list[int]:
    scaled = [value * utilization for value in base]
    target = round(sum(scaled))
    lower = [math.ceil(value * 0.9) for value in scaled]
    upper = [math.floor(value * 1.1) for value in scaled]
    if sum(lower) > target or sum(upper) < target:
        raise ValueError("period demand bounds cannot contain target total")
    totals = lower[:]
    remaining = target - sum(totals)
    while remaining:
        candidates = [i for i in range(len(totals)) if totals[i] < upper[i]]
        if not candidates:
            raise RuntimeError("failed to allocate period demand total")
        index = rng.choice(candidates)
        totals[index] += 1
        remaining -= 1
    # 같은 utilization에서도 seed마다 기간 패턴이 달라지도록 순서를 섞는다.
    for _ in range(20):
        a, b = rng.sample(range(len(totals)), 2)
        if totals[a] < upper[a] and totals[b] > lower[b]:
            totals[a] += 1
            totals[b] -= 1
    return totals


def _allocate_demands(period_totals: list[int], part_count: int, rng: random.Random) -> list[list[int]]:
    result = [[0 for _ in PERIODS] for _ in range(part_count)]
    for period_index, total in enumerate(period_totals):
        weights = [rng.uniform(0.9, 1.1) for _ in range(part_count)]
        raw = [total * weight / sum(weights) for weight in weights]
        values = [math.floor(value) for value in raw]
        for index in sorted(range(part_count), key=lambda i: raw[i] - values[i], reverse=True)[:total - sum(values)]:
            values[index] += 1
        for part_index, value in enumerate(values):
            result[part_index][period_index] = value
    return result


def _experiment_id(part_count: int, overlap: str, utilization: float, seed: int) -> str:
    return f"p{part_count}_{overlap}_u{int(round(utilization * 100)):03d}_s{seed:02d}"


def _write_demand(path: Path, demands: list[list[int]], routes: tuple[tuple[int, ...], ...]) -> None:
    rows = []
    for index, values in enumerate(demands):
        rows.append({
            "part": f"P{index + 1}",
            **{f"period{period}": values[period - 1] for period in PERIODS},
            "operation_sequence": ">".join(str(operation) for operation in routes[index]),
        })
    _write_csv(path, rows)


def _write_metadata(path: Path, rows: list[dict]) -> None:
    _write_csv(path, rows)


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
