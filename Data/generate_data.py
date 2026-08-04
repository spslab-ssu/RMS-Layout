from __future__ import annotations

import csv
import shutil
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "Data"


SIMILAR_TABLE_CONFIGS = [
    ("M1", "mc11", 850, [2, 3], [12, 17, 20, 22], {4: 18, 8: 16, 12: 10, 16: 15}),
    ("M1", "mc12", 1320, [2, 3], [12, 13, 16, 20, 23], {5: 20, 9: 12, 18: 20}),
    ("M1", "mc13", 890, [2, 3], [13, 16, 19, 20, 24], {3: 24, 7: 18, 16: 22}),
    ("M1", "mc14", 1450, [2, 3], [12, 16, 17], {10: 18, 19: 23}),
    ("M2", "mc21", 1330, [4, 5, 7, 10], [11, 14, 22, 24], {1: 20, 6: 16, 12: 22, 20: 26}),
    ("M2", "mc22", 1210, [4, 5, 7, 10], [11, 15, 19], {2: 24, 13: 19, 15: 20}),
    ("M2", "mc23", 2000, [4, 5, 7, 10], [15, 19, 23], {3: 17, 8: 28, 11: 21, 17: 30}),
    ("M2", "mc24", 1580, [4, 5, 7, 10], [14, 15, 18, 23], {2: 25, 5: 19, 7: 20, 14: 16}),
    ("M2", "mc25", 1750, [4, 5, 7, 10], [13, 23], {4: 16, 13: 20, 18: 14, 20: 23}),
    ("M3", "mc31", 1400, [1, 2, 6, 10], [13, 15, 16, 19], {2: 15, 9: 23, 12: 18, 17: 20}),
    ("M3", "mc32", 2520, [1, 2, 6, 10], [11, 12, 15, 16, 19, 21], {1: 12, 4: 19, 8: 29, 11: 22, 15: 17, 17: 24, 19: 24}),
    ("M4", "mc41", 1920, [7, 9, 10], [15, 20], {6: 16, 10: 18, 18: 22}),
    ("M4", "mc42", 2020, [7, 9, 10], [15, 16, 20, 24], {1: 22, 12: 24, 17: 19, 20: 15}),
    ("M4", "mc43", 1880, [7, 9, 10], [12, 16, 18, 23], {2: 17, 4: 21, 8: 24, 13: 16, 16: 26, 19: 23}),
    ("M5", "mc51", 1730, [8, 9, 10], [19, 22], {1: 25, 7: 18, 11: 16, 14: 10, 18: 28}),
    ("M5", "mc52", 1530, [8, 9, 10], [14, 18, 19, 22, 25], {3: 14, 5: 25, 10: 22, 17: 24, 20: 30}),
    ("M5", "mc53", 2160, [8, 9, 10], [14, 16, 19, 22], {4: 17, 9: 10, 15: 14}),
    ("M5", "mc54", 1800, [8, 9, 10], [18, 20, 22], {1: 13, 6: 27, 7: 12, 14: 18, 16: 21, 19: 15}),
]


def main() -> None:
    """번호 기반 RMT table과 demand 조합용 CSV를 생성한다."""
    _refresh_resource_requirements(DATA_DIR / "rmt_tables" / "table_1")
    _write_similar_table_data()
    print("Generated Data locations/rmt_tables/parameters/demands/shared_resources")


def _refresh_resource_requirements(table_dir: Path) -> None:
    """configuration auxiliary_modules에서 shared resource requirement를 만든다."""
    _write_resource_requirements(table_dir / "configurations.csv", table_dir / "resource_requirements.csv")


def _write_similar_table_data() -> None:
    """유사 데이터 table 1/2를 table_2와 demand_2로 저장한다."""
    rmt_dir = DATA_DIR / "rmt_tables" / "table_2"
    rmt_dir.mkdir(parents=True, exist_ok=True)
    _write_configurations(rmt_dir / "configurations.csv", SIMILAR_TABLE_CONFIGS)
    _write_production_rates(rmt_dir / "production_rates.csv", SIMILAR_TABLE_CONFIGS)
    _write_resource_requirements(rmt_dir / "configurations.csv", rmt_dir / "resource_requirements.csv")
    _write_similar_problem_inputs()


def _write_similar_problem_inputs() -> None:
    """유사 논문의 RSPFL operation sequence를 layout 모델용 단일부품 demand로 저장한다."""
    demand_dir = DATA_DIR / "demands" / "single_part"
    demand_dir.mkdir(parents=True, exist_ok=True)
    _write_rows(
        demand_dir / "demand_2.csv",
        ["part", "period1", "period2", "period3", "period4", "operation_sequence"],
        [{"part": "A", "period1": 60, "period2": 60, "period3": 60, "period4": 60, "operation_sequence": "2>5>7>15>8>16"}],
    )
    resources = sorted({resource for _, _, _, _, aux, _ in SIMILAR_TABLE_CONFIGS for resource in aux})
    capacity_rows = [{"resource": resource, "capacity": 5} for resource in resources]
    shared_dir = DATA_DIR / "shared_resources"
    shared_dir.mkdir(parents=True, exist_ok=True)
    _write_rows(shared_dir / "shared_resources_2.csv", ["resource", "capacity"], capacity_rows)
    _write_rows(shared_dir / "resource_capacities_2.csv", ["resource", "capacity"], capacity_rows)


def _write_configurations(path: Path, configs: list[tuple]) -> None:
    fields = ["machine", "configuration"] + [f"op{i}" for i in range(1, 21)] + ["cost", "basic_modules", "auxiliary_modules"]
    rows = []
    for machine, configuration, cost, basic_modules, auxiliary_modules, rates in configs:
        row = {
            "machine": machine,
            "configuration": configuration,
            "cost": cost,
            "basic_modules": _join_modules(basic_modules),
            "auxiliary_modules": _join_modules(auxiliary_modules),
        }
        for operation in range(1, 21):
            row[f"op{operation}"] = rates.get(operation, "")
        rows.append(row)
    _write_rows(path, fields, rows)


def _write_production_rates(path: Path, configs: list[tuple]) -> None:
    rows = []
    for machine, configuration, _, _, _, rates in configs:
        for operation, production_rate in sorted(rates.items()):
            rows.append({
                "machine": machine,
                "configuration": configuration,
                "operation": operation,
                "production_rate": production_rate,
            })
    _write_rows(path, ["machine", "configuration", "operation", "production_rate"], rows)


def _write_resource_requirements(configuration_file: Path, output_file: Path) -> None:
    """configuration의 auxiliary_modules에서 binary resource requirement를 만든다."""
    rows: list[dict[str, str | int]] = []
    with configuration_file.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            configuration = str(row["configuration"])
            modules = str(row.get("auxiliary_modules", "")).replace(",", ";").replace("/", ";").replace(" ", "")
            for module in modules.split(";"):
                if module:
                    rows.append({"configuration": configuration, "resource": int(module), "amount": 1})
    _write_rows(output_file, ["configuration", "resource", "amount"], rows)


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _join_modules(values: list[int]) -> str:
    return ";".join(str(value) for value in values)


if __name__ == "__main__":
    main()
