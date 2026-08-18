from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

import config
from Src.data import load_instance
from Src.scenario import build_grid_locations, prepare_scenario_directory


class EditableScenarioTest(unittest.TestCase):
    def test_builds_an_arbitrary_grid_with_start_and_end(self) -> None:
        locations = build_grid_locations(
            2,
            3,
            origin_x=10.0,
            origin_y=-2.0,
            spacing_x=2.0,
            spacing_y=3.0,
        )
        self.assertEqual((locations["type"] == "install").sum(), 6)
        self.assertEqual(locations.loc[0, ["x", "y"]].tolist(), [10.0, -2.0])
        self.assertEqual(locations.loc[5, ["x", "y"]].tolist(), [14.0, 1.0])
        self.assertEqual((locations["type"] == "start").sum(), 1)
        self.assertEqual((locations["type"] == "end").sum(), 1)

    def test_prepared_scenario_loads_without_modifying_baseline(self) -> None:
        locations = build_grid_locations(4, 4)
        demands = pd.read_csv(config.DATA_DIR / "single_part" / "demands.csv")
        original = demands.copy(deep=True)
        demands.loc[0, "period2"] = 77
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = prepare_scenario_directory(
                config.DATA_DIR / "single_part",
                Path(temp_dir),
                locations,
                demands,
            )
            settings = config.build_config(
                problem_name="single_part",
                PROBLEM_NAME="editable_test",
                **paths,
            )
            instance = load_instance(settings)
        self.assertEqual(len(instance.install_locations), 16)
        self.assertEqual(instance.arc_demand[2, 0, 5], 77.0)
        baseline = pd.read_csv(config.DATA_DIR / "single_part" / "demands.csv")
        pd.testing.assert_frame_equal(baseline, original)


if __name__ == "__main__":
    unittest.main()
