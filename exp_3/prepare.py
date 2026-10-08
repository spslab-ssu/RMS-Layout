"""Exp3 수요 데이터와 실행 manifest를 생성한다.

Exp3는 Network와 Network Adaptive를 비교하기 위한 실험이다.
총수요는 기존 multi-part demand의 총량 370에 0.75를 적용한 278로
고정하고, period 수에 따라 수요를 seed 기반으로 재배분한다.
"""
from __future__ import annotations

import csv
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "Data"
OUTPUT_DIR = Path(__file__).resolve().parent
DEMAND_ROOT = DATA_DIR / "demands" / "exp_3"
PARAMETER_ROOT = DATA_DIR / "parameters" / "exp_3"
BASE_DEMAND = DATA_DIR / "demands" / "multi_part" / "demand_1.csv"

PART_COUNTS = (1, 3, 5)
LAYOUTS = ("layout_22", "layout_27")
OVERLAPS = ("high", "low")
PERIOD_COUNTS = (2, 4, 6)
SEEDS = (1, 2, 3)
TARGET_UTILIZATION = 0.75
RMT_TABLE = "table_1"

ALL_OPERATIONS = tuple(range(1, 21))
# High overlap은 seed마다 공통 core를 새로 선택하고, 각 부품의 suffix를 새로 생성한다.
# 기존 Saffar 예시의 2->12 흐름도 후보에 포함하되, 모든 seed가 같은 core를 사용하지 않는다.
HIGH_COMMON_CORES = (
    (2, 12), (2, 13), (5, 10), (6, 16), (9, 14), (11, 18),
)


def main() -> None:
    target_total = _target_total()
    _write_layout_27_if_missing()
    for period_count in PERIOD_COUNTS:
        _write_parameter_file(period_count)

    manifest_rows = []
    metadata_rows = []
    for part_count in PART_COUNTS:
        for overlap in OVERLAPS:
            routes_by_seed = _routes_by_seed(part_count, overlap)
            for period_count in PERIOD_COUNTS:
                for seed in SEEDS:
                    rng = random.Random(_demand_seed(part_count, overlap, period_count, seed))
                    period_totals = _allocate_total_by_period(target_total, period_count, rng)
                    demands = _allocate_total_by_part(period_totals, part_count, rng)
                    assigned_routes = routes_by_seed[seed]
                    experiment_id = _experiment_id(part_count, overlap, period_count, seed)
                    demand_path = DEMAND_ROOT / f"p{part_count}" / f"{experiment_id}.csv"
                    _write_demand(demand_path, demands, assigned_routes)
                    metadata = {
                        "experiment_id": experiment_id,
                        "part_count": part_count,
                        "overlap": overlap,
                        "utilization": TARGET_UTILIZATION,
                        "period_count": period_count,
                        "seed": seed,
                        "demand_file": str(demand_path.relative_to(ROOT)),
                        "parameter_file": str((_parameter_path(period_count)).relative_to(ROOT)),
                        "period_total": ",".join(str(value) for value in period_totals),
                        "total_demand": sum(period_totals),
                        "route_operation_count": len({op for route in assigned_routes for op in route}),
                        "operation_sequences": "|".join(">".join(str(op) for op in route) for route in assigned_routes),
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
    print(f"target total demand: {target_total}")
    print(f"wrote {len(metadata_rows)} demand files")
    print(f"wrote {len(manifest_rows)} manifest rows")


def _target_total() -> int:
    with BASE_DEMAND.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    period_columns = [key for key in rows[0] if key.startswith("period")]
    base_total = sum(int(float(row[column])) for row in rows for column in period_columns)
    return round(base_total * TARGET_UTILIZATION)


def _routes_by_seed(part_count: int, overlap: str) -> dict[int, tuple[tuple[int, ...], ...]]:
    generated: dict[int, tuple[tuple[int, ...], ...]] = {}
    signatures: set[tuple[tuple[int, ...], ...]] = set()
    for seed in SEEDS:
        for attempt in range(100):
            rng = random.Random(_sequence_seed(part_count, overlap, seed, attempt))
            if overlap == "high":
                assigned = _generate_high_routes(part_count, rng)
            else:
                assigned = _generate_low_routes(part_count, rng)
            signature = tuple(assigned)
            if signature not in signatures:
                generated[seed] = signature
                signatures.add(signature)
                break
        else:
            raise RuntimeError(f"failed to generate distinct routes for {part_count=}, {overlap=}")
    return generated


def _generate_high_routes(part_count: int, rng: random.Random) -> list[tuple[int, ...]]:
    """공통 core를 유지하면서 seed별로 완전히 새로운 route를 만든다."""
    core = rng.choice(HIGH_COMMON_CORES)
    remaining = [operation for operation in ALL_OPERATIONS if operation not in core]
    routes = []
    for _ in range(part_count):
        for _attempt in range(100):
            suffix_length = rng.choice((1, 2))
            suffix = tuple(rng.sample(remaining, suffix_length))
            route = core + suffix
            if route not in routes:
                routes.append(route)
                break
        else:
            raise RuntimeError(f"failed to generate unique high routes for {part_count=}")
    rng.shuffle(routes)
    return routes


def _generate_low_routes(part_count: int, rng: random.Random) -> list[tuple[int, ...]]:
    """operation permutation을 서로 겹치지 않는 route들로 분할한다."""
    operations = list(ALL_OPERATIONS)
    rng.shuffle(operations)
    lengths = [3] * part_count
    for index in rng.sample(range(part_count), k=max(0, min(part_count, part_count // 2))):
        lengths[index] = 4
    routes = []
    cursor = 0
    for length in lengths:
        routes.append(tuple(operations[cursor:cursor + length]))
        cursor += length
    rng.shuffle(routes)
    return routes


def _sequence_seed(part_count: int, overlap: str, seed: int, attempt: int) -> int:
    overlap_code = 1 if overlap == "high" else 2
    return seed + part_count * 1000 + overlap_code * 10000 + attempt * 100000


def _demand_seed(part_count: int, overlap: str, period_count: int, seed: int) -> int:
    overlap_code = 1 if overlap == "high" else 2
    return seed + part_count * 1000 + overlap_code * 10000 + period_count * 100000


def _allocate_total_by_period(total: int, period_count: int, rng: random.Random) -> list[int]:
    weights = [rng.uniform(0.75, 1.25) for _ in range(period_count)]
    raw = [total * weight / sum(weights) for weight in weights]
    values = [int(value) for value in raw]
    for index in sorted(range(period_count), key=lambda i: raw[i] - values[i], reverse=True)[: total - sum(values)]:
        values[index] += 1
    rng.shuffle(values)
    return values


def _allocate_total_by_part(period_totals: list[int], part_count: int, rng: random.Random) -> list[list[int]]:
    result = [[0 for _ in period_totals] for _ in range(part_count)]
    for period_index, total in enumerate(period_totals):
        weights = [rng.uniform(0.85, 1.15) for _ in range(part_count)]
        raw = [total * weight / sum(weights) for weight in weights]
        values = [int(value) for value in raw]
        for index in sorted(range(part_count), key=lambda i: raw[i] - values[i], reverse=True)[: total - sum(values)]:
            values[index] += 1
        for part_index, value in enumerate(values):
            result[part_index][period_index] = value
    return result


def _experiment_id(part_count: int, overlap: str, period_count: int, seed: int) -> str:
    return f"p{part_count}_{overlap}_t{period_count}_s{seed:02d}"


def _write_demand(path: Path, demands: list[list[int]], routes: list[tuple[int, ...]]) -> None:
    rows = []
    for part_index, values in enumerate(demands):
        rows.append({
            "part": f"P{part_index + 1}",
            **{f"period{period}": values[period - 1] for period in range(1, len(values) + 1)},
            "operation_sequence": ">".join(str(operation) for operation in routes[part_index]),
        })
    _write_csv(path, rows)


def _write_layout_27_if_missing() -> None:
    path = DATA_DIR / "locations" / "layout_27.csv"
    if path.exists():
        return
    rows = [
        {"location": y * 5 + x + 1, "x": x, "y": y, "type": "install"}
        for y in range(5) for x in range(5)
    ]
    rows.extend([
        {"location": 26, "x": -2, "y": 2, "type": "start"},
        {"location": 27, "x": 6, "y": 2, "type": "end"},
    ])
    _write_csv(path, rows)


def _parameter_path(period_count: int) -> Path:
    return PARAMETER_ROOT / f"period_{period_count}.csv"


def _write_parameter_file(period_count: int) -> None:
    source = DATA_DIR / "parameters" / "multi_part.csv"
    rows = []
    with source.open(newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            rows.append({"parameter": row["parameter"], "value": period_count if row["parameter"] == "period_count" else row["value"]})
    _write_csv(_parameter_path(period_count), rows)


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
