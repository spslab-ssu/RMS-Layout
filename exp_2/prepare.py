"""2차 optimal 비교 실험의 조건 manifest를 준비한다.

기존 exp_random 수요 CSV를 재사용하므로 수요 파일을 중복 저장하지 않는다.
seed 1의 8개 조건이 먼저 오고 seed 2의 8개 조건이 이어지도록 정렬한다.
"""
from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST = ROOT / "Data/demands/exp_random/manifest.csv"
OUTPUT_MANIFEST = Path(__file__).resolve().parent / "manifest.csv"

PART_COUNTS = (3, 5)
LAYOUTS = ("layout_18", "layout_22")
UTILIZATIONS = (0.75, 1.0)
SEEDS = (1, 2)


def main() -> None:
    with SOURCE_MANIFEST.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))

    selected = [
        row for row in rows
        if int(row["part_count"]) in PART_COUNTS
        and row["layout_name"] in LAYOUTS
        and float(row["utilization"]) in UTILIZATIONS
        and int(row["seed"]) in SEEDS
    ]
    selected.sort(
        key=lambda row: (
            int(row["seed"]),
            int(row["part_count"]),
            float(row["utilization"]),
            LAYOUTS.index(row["layout_name"]),
        )
    )

    expected = len(PART_COUNTS) * len(LAYOUTS) * len(UTILIZATIONS) * len(SEEDS)
    if len(selected) != expected:
        raise RuntimeError(f"expected {expected} rows, found {len(selected)}")

    OUTPUT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_MANIFEST.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(selected[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(selected)

    print(f"wrote {len(selected)} rows to {OUTPUT_MANIFEST}")
    print("seed order:", ", ".join(sorted({row["seed"] for row in selected}, key=int)))


if __name__ == "__main__":
    main()
