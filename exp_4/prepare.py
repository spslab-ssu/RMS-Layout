"""Exp4 데이터와 실행 manifest를 생성한다.

Exp4는 2차 실험 조건을 확장해 overlap 효과를 비교한다.
부품 수 3/5, layout18, utilization 0.75/1.0, high/low overlap,
seed 1/2의 16개 조건을 생성한다.
"""
from __future__ import annotations

import csv
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "Data"
OUTPUT_DIR = Path(__file__).resolve().parent
DEMAND_ROOT = DATA_DIR / "demands" / "exp_4"
PARAMETER_ROOT = DATA_DIR / "parameters" / "exp_4"
BASE_DEMAND = DATA_DIR / "demands" / "multi_part" / "demand_1.csv"

PART_COUNTS = (3, 5)
LAYOUTS = ("layout_18", "layout_22")
OVERLAPS = ("high", "low")
UTILIZATIONS = (0.75, 1.0)
SEEDS = (1, 2)
RMT_TABLE = "table_1"
PERIOD_COUNT = 4
ALL_OPERATIONS = tuple(range(1, 21))
HIGH_CORES = ((2, 12, 11, 8), (2, 12, 17, 8), (5, 10, 16, 6))


def main() -> None:
    base_period_totals = _base_period_totals()
    _write_parameter_file()
    manifest_rows = []
    metadata_rows = []

    for part_count in PART_COUNTS:
        for overlap in OVERLAPS:
            for utilization in UTILIZATIONS:
                for seed in SEEDS:
                    rng = random.Random(_seed(part_count, overlap, utilization, seed))
                    period_totals = _scale_period_totals(base_period_totals, utilization)
                    demands = _allocate_by_part(period_totals, part_count, rng)
                    routes = _routes(part_count, overlap, seed)
                    experiment_id = _experiment_id(part_count, overlap, utilization, seed)
                    demand_path = DEMAND_ROOT / f"p{part_count}" / f"{experiment_id}.csv"
                    _write_demand(demand_path, demands, routes)
                    metadata = {
                        "experiment_id": experiment_id,
                        "part_count": part_count,
                        "overlap": overlap,
                        "utilization": utilization,
                        "period_count": PERIOD_COUNT,
                        "seed": seed,
                        "demand_file": str(demand_path.relative_to(ROOT)),
                        "parameter_file": str(_parameter_path().relative_to(ROOT)),
                        "period_total": ",".join(map(str, period_totals)),
                        "total_demand": sum(period_totals),
                        "operation_sequences": "|".join(
                            ">".join(map(str, route)) for route in routes
                        ),
                    }
                    metadata_rows.append(metadata)
                    for layout_name in LAYOUTS:
                        manifest_rows.append({
                            **metadata,
                            "layout_name": layout_name,
                            "rmt_table": RMT_TABLE,
                        })

    _write_csv(OUTPUT_DIR / "manifest.csv", manifest_rows)
    _write_csv(OUTPUT_DIR / "demand_metadata.csv", metadata_rows)
    print(f"wrote {len(metadata_rows)} demand files")
    print(f"wrote {len(manifest_rows)} manifest rows")


def _base_period_totals() -> list[int]:
    with BASE_DEMAND.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    columns = [key for key in rows[0] if key.startswith("period")]
    return [sum(int(float(row[column])) for row in rows) for column in columns]


def _scale_period_totals(values: list[int], utilization: float) -> list[int]:
    raw = [value * utilization for value in values]
    scaled = [int(value) for value in raw]
    remainder = round(sum(raw)) - sum(scaled)
    for index in sorted(range(len(raw)), key=lambda i: raw[i] - scaled[i], reverse=True)[:remainder]:
        scaled[index] += 1
    return scaled


def _allocate_by_part(period_totals: list[int], part_count: int, rng: random.Random) -> list[list[int]]:
    result = [[0 for _ in period_totals] for _ in range(part_count)]
    for period_index, total in enumerate(period_totals):
        weights = [rng.uniform(0.85, 1.15) for _ in range(part_count)]
        raw = [total * weight / sum(weights) for weight in weights]
        values = [int(value) for value in raw]
        remainder = total - sum(values)
        for index in sorted(range(part_count), key=lambda i: raw[i] - values[i], reverse=True)[:remainder]:
            values[index] += 1
        for part_index, value in enumerate(values):
            result[part_index][period_index] = value
    return result


def _routes(part_count: int, overlap: str, seed: int) -> list[tuple[int, ...]]:
    rng = random.Random(100000 + part_count * 1000 + seed * 10 + (1 if overlap == "high" else 2))
    if overlap == "high":
        core = rng.choice(HIGH_CORES)
        remaining = [operation for operation in ALL_OPERATIONS if operation not in core]
        routes = []
        for _ in range(part_count):
            extra = rng.choice(remaining)
            route = list(core)
            position = rng.randint(0, len(route))
            route.insert(position, extra)
            if tuple(route) in routes:
                route[-1] = remaining[(remaining.index(extra) + 1) % len(remaining)]
            routes.append(tuple(route))
        rng.shuffle(routes)
        return routes

    operations = list(ALL_OPERATIONS)
    rng.shuffle(operations)
    lengths = [3] * part_count
    for index in rng.sample(range(part_count), k=part_count // 2):
        lengths[index] = 4
    routes = []
    cursor = 0
    for length in lengths:
        routes.append(tuple(operations[cursor:cursor + length]))
        cursor += length
    rng.shuffle(routes)
    return routes


def _seed(part_count: int, overlap: str, utilization: float, seed: int) -> int:
    overlap_code = 1 if overlap == "high" else 2
    utilization_code = int(utilization * 100)
    return seed + part_count * 1000 + overlap_code * 10000 + utilization_code * 100000


def _experiment_id(part_count: int, overlap: str, utilization: float, seed: int) -> str:
    utilization_code = f"u{int(utilization * 100):03d}"
    return f"p{part_count}_{overlap}_{utilization_code}_s{seed:02d}"


def _write_demand(path: Path, demands: list[list[int]], routes: list[tuple[int, ...]]) -> None:
    rows = []
    for part_index, values in enumerate(demands):
        rows.append({
            "part": f"P{part_index + 1}",
            **{f"period{period}": values[period - 1] for period in range(1, PERIOD_COUNT + 1)},
            "operation_sequence": ">".join(map(str, routes[part_index])),
        })
    _write_csv(path, rows)


def _parameter_path() -> Path:
    return PARAMETER_ROOT / "period_4.csv"


def _write_parameter_file() -> None:
    source = DATA_DIR / "parameters" / "multi_part.csv"
    rows = []
    with source.open(newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            rows.append({"parameter": row["parameter"], "value": PERIOD_COUNT if row["parameter"] == "period_count" else row["value"]})
    _write_csv(_parameter_path(), rows)


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
