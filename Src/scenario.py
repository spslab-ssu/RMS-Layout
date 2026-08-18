"""Editable scenario utilities for the interactive experiment UI."""

from __future__ import annotations

from pathlib import Path
from shutil import copy2

import pandas as pd


SCENARIO_FILES = (
    "configurations.csv",
    "production_rates.csv",
    "shared_resources.csv",
    "resource_requirements.csv",
)


def build_grid_locations(
    rows: int,
    columns: int,
    *,
    origin_x: float = 0.0,
    origin_y: float = 0.0,
    spacing_x: float = 1.0,
    spacing_y: float = 1.0,
    start_x: float | None = None,
    start_y: float | None = None,
    end_x: float | None = None,
    end_y: float | None = None,
) -> pd.DataFrame:
    """Create an m x n install grid plus editable start/end coordinates."""
    if rows < 1 or columns < 1:
        raise ValueError("Grid rows and columns must both be positive.")
    if spacing_x <= 0 or spacing_y <= 0:
        raise ValueError("Grid spacing must be positive.")

    records = []
    location = 1
    for row in range(rows):
        for column in range(columns):
            records.append(
                {
                    "location": location,
                    "x": origin_x + column * spacing_x,
                    "y": origin_y + row * spacing_y,
                    "type": "install",
                }
            )
            location += 1

    center_y = origin_y + (rows - 1) * spacing_y / 2
    start_x = origin_x - 2 * spacing_x if start_x is None else start_x
    start_y = center_y if start_y is None else start_y
    end_x = origin_x + (columns + 1) * spacing_x if end_x is None else end_x
    end_y = center_y if end_y is None else end_y
    records.extend(
        [
            {"location": location, "x": start_x, "y": start_y, "type": "start"},
            {"location": location + 1, "x": end_x, "y": end_y, "type": "end"},
        ]
    )
    return pd.DataFrame.from_records(records)


def prepare_scenario_directory(
    base_problem_dir: Path,
    scenario_dir: Path,
    locations: pd.DataFrame,
    demands: pd.DataFrame,
) -> dict[str, Path]:
    """Write editable inputs without modifying the checked-in baseline data."""
    validated_locations = validate_locations(locations)
    validated_demands = validate_demands(demands)
    scenario_dir.mkdir(parents=True, exist_ok=True)

    for filename in SCENARIO_FILES:
        source = base_problem_dir / filename
        if source.exists():
            copy2(source, scenario_dir / filename)

    params = pd.read_csv(base_problem_dir / "parameters.csv")
    values = {
        str(row.parameter): float(row.value)
        for row in params.itertuples(index=False)
    }
    period_columns = sorted(
        (column for column in validated_demands.columns if column.startswith("period")),
        key=lambda name: int(name.removeprefix("period")),
    )
    start_location = int(
        validated_locations.loc[validated_locations["type"] == "start", "location"].iloc[0]
    )
    end_location = int(
        validated_locations.loc[validated_locations["type"] == "end", "location"].iloc[0]
    )
    values.update(
        {
            "period_count": float(len(period_columns)),
            "start_location": float(start_location),
            "end_location": float(end_location),
        }
    )

    validated_locations.to_csv(scenario_dir / "locations.csv", index=False)
    validated_demands.to_csv(scenario_dir / "demands.csv", index=False)
    pd.DataFrame(
        [{"parameter": key, "value": value} for key, value in values.items()]
    ).to_csv(scenario_dir / "parameters.csv", index=False)

    return {
        "LOCATION_FILE": scenario_dir / "locations.csv",
        "CONFIGURATION_FILE": scenario_dir / "configurations.csv",
        "PRODUCTION_RATE_FILE": scenario_dir / "production_rates.csv",
        "DEMAND_FILE": scenario_dir / "demands.csv",
        "PARAMETER_FILE": scenario_dir / "parameters.csv",
        "SHARED_RESOURCE_FILE": scenario_dir / "shared_resources.csv",
        "RESOURCE_REQUIREMENT_FILE": scenario_dir / "resource_requirements.csv",
    }


def validate_locations(locations: pd.DataFrame) -> pd.DataFrame:
    required = {"location", "x", "y", "type"}
    missing = required - set(locations.columns)
    if missing:
        raise ValueError(f"Location table is missing columns: {sorted(missing)}")
    result = locations.loc[:, ["location", "x", "y", "type"]].copy()
    result["location"] = pd.to_numeric(result["location"], errors="raise").astype(int)
    result["x"] = pd.to_numeric(result["x"], errors="raise").astype(float)
    result["y"] = pd.to_numeric(result["y"], errors="raise").astype(float)
    result["type"] = result["type"].astype(str).str.strip().str.lower()
    if result["location"].duplicated().any():
        raise ValueError("Location IDs must be unique.")
    if not set(result["type"]).issubset({"install", "start", "end"}):
        raise ValueError("Location type must be install, start, or end.")
    if (result["type"] == "start").sum() != 1 or (result["type"] == "end").sum() != 1:
        raise ValueError("Exactly one start and one end location are required.")
    if not (result["type"] == "install").any():
        raise ValueError("At least one install location is required.")
    return result.sort_values("location").reset_index(drop=True)


def validate_demands(demands: pd.DataFrame) -> pd.DataFrame:
    required = {"part", "operation_sequence"}
    missing = required - set(demands.columns)
    if missing:
        raise ValueError(f"Demand table is missing columns: {sorted(missing)}")
    period_columns = [column for column in demands.columns if column.startswith("period")]
    if not period_columns:
        raise ValueError("At least one period column is required.")
    result = demands.loc[:, ["part", *period_columns, "operation_sequence"]].copy()
    result["part"] = result["part"].astype(str).str.strip()
    result["operation_sequence"] = result["operation_sequence"].astype(str).str.strip()
    if (result["part"] == "").any() or result["part"].duplicated().any():
        raise ValueError("Part names must be nonempty and unique.")
    for column in period_columns:
        result[column] = pd.to_numeric(result[column], errors="raise").astype(float)
        if (result[column] < 0).any():
            raise ValueError("Demand values must be nonnegative.")
    for route in result["operation_sequence"]:
        try:
            operations = [int(token.strip()) for token in route.split(">")]
        except ValueError as exc:
            raise ValueError(f"Invalid operation sequence: {route!r}") from exc
        if not operations:
            raise ValueError("Operation sequence cannot be empty.")
    return result.reset_index(drop=True)
