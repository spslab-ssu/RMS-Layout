from __future__ import annotations

import shutil
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
LEGACY_DATA_DIR = BASE_DIR.parent / "implementation" / "data"


def main() -> None:
    """메인논문 단일/다중부품 재현용 입력 CSV를 생성한다.

    현재는 검증된 legacy CSV를 새 RMS_Layout/Data 표준 구조로 복사한다.
    추후 random instance나 sensitivity scenario 생성 로직을 여기에 추가한다.
    """
    _copy_dataset("single_part_problem", "single_part")
    _copy_dataset("multi_part_problem", "multi_part")
    print("Generated main paper datasets under Data/single_part and Data/multi_part")


def _copy_dataset(source_name: str, target_name: str) -> None:
    """기존 implementation 데이터셋을 새 표준 파일명으로 복사한다."""
    source_dir = LEGACY_DATA_DIR / source_name
    target_dir = BASE_DIR / "Data" / target_name
    target_dir.mkdir(parents=True, exist_ok=True)
    mapping = {
        "locations.csv": "locations.csv",
        "rmt_configurations.csv": "configurations.csv",
        "production_rates.csv": "production_rates.csv",
        "part_demands.csv": "demands.csv",
        "model_parameters.csv": "parameters.csv",
    }
    for src_name, dst_name in mapping.items():
        shutil.copyfile(source_dir / src_name, target_dir / dst_name)


if __name__ == "__main__":
    main()
