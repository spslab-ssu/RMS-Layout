from __future__ import annotations

import csv
import shutil
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
LEGACY_DATA_DIR = BASE_DIR.parent / "implementation" / "data"
DEFAULT_RMT_TABLE = "goyal_saffar"


def main() -> None:
    """메인논문 재현용 dataset CSV와 공통 RMT table CSV를 생성한다.

    RMT configuration/rate/resource requirement는 single/multi가 공유하므로
    Data/rmt_tables/<table_name>/에 한 번만 둔다. 문제별로 달라지는
    locations, demands, parameters, shared resource capacity는
    Data/datasets/<problem_name>/에 둔다.
    """
    _copy_rmt_table("single_part_problem", DEFAULT_RMT_TABLE)
    _copy_dataset("single_part_problem", "single_part")
    _copy_dataset("multi_part_problem", "multi_part")
    print("Generated datasets under Data/datasets and RMT table under Data/rmt_tables")


def _copy_rmt_table(source_name: str, table_name: str) -> None:
    """공통 RMT table 파일을 생성한다."""
    source_dir = LEGACY_DATA_DIR / source_name
    target_dir = BASE_DIR / "Data" / "rmt_tables" / table_name
    target_dir.mkdir(parents=True, exist_ok=True)
    mapping = {
        "rmt_configurations.csv": "configurations.csv",
        "production_rates.csv": "production_rates.csv",
    }
    for src_name, dst_name in mapping.items():
        shutil.copyfile(source_dir / src_name, target_dir / dst_name)
    _write_resource_requirements(target_dir / "configurations.csv", target_dir / "resource_requirements.csv")


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
    with output_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["configuration", "resource", "amount"])
        writer.writeheader()
        writer.writerows(rows)


def _copy_dataset(source_name: str, target_name: str) -> None:
    """문제별 데이터셋 파일을 생성한다."""
    source_dir = LEGACY_DATA_DIR / source_name
    target_dir = BASE_DIR / "Data" / "datasets" / target_name
    target_dir.mkdir(parents=True, exist_ok=True)
    mapping = {
        "locations.csv": "locations.csv",
        "part_demands.csv": "demands.csv",
        "model_parameters.csv": "parameters.csv",
    }
    for src_name, dst_name in mapping.items():
        shutil.copyfile(source_dir / src_name, target_dir / dst_name)


if __name__ == "__main__":
    main()
