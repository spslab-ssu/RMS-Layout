from __future__ import annotations

import unittest

import pandas as pd

from Src.sensitivity import (
    build_cost_cases,
    build_grid_cases,
    parse_numeric_levels,
    recommend_case,
)


class SensitivityTest(unittest.TestCase):
    def test_numeric_levels_are_sorted_and_deduplicated(self) -> None:
        self.assertEqual(parse_numeric_levels("5, 0, 1, 1"), [0.0, 1.0, 5.0])
        with self.assertRaises(ValueError):
            parse_numeric_levels("0, -1")

    def test_reconfiguration_level_scales_add_and_remove_costs(self) -> None:
        cases = build_cost_cases(
            "reconfiguration_cost",
            [25.0, 50.0],
            rows=4,
            columns=4,
            spacing=1.0,
            relocation_distance_cost=0.0,
            base_add_module_cost=50.0,
            base_remove_module_cost=25.0,
        )
        self.assertEqual(cases[0]["reconfiguration_multiplier"], 0.5)
        self.assertEqual(cases[0]["remove_module_cost"], 12.5)
        self.assertEqual(cases[1]["reconfiguration_multiplier"], 1.0)

    def test_grid_recommendation_uses_cost_then_relocation(self) -> None:
        cases = build_grid_cases(
            pd.DataFrame(
                [
                    {"m": 3, "n": 4, "coordinate_distance": 1.0},
                    {"m": 4, "n": 4, "coordinate_distance": 2.0},
                ]
            ),
            relocation_distance_cost=0.0,
        )
        frame = pd.DataFrame(
            [
                {**cases[0], "status": "OPTIMAL", "system_cost": 100.0, "relocation_count": 3, "grid_area": 12, "coordinate_distance": 1.0, "m": 3, "n": 4},
                {**cases[1], "status": "OPTIMAL", "system_cost": 100.0, "relocation_count": 1, "grid_area": 16, "coordinate_distance": 2.0, "m": 4, "n": 4},
            ]
        )
        recommendation = recommend_case(frame, "grid")
        self.assertEqual(recommendation["case"], cases[1]["case"])

    def test_cost_recommendation_finds_first_stable_tail(self) -> None:
        frame = pd.DataFrame(
            {
                "case": ["c0", "c1", "c2", "c3"],
                "status": ["OPTIMAL"] * 4,
                "analysis_value": [0.0, 1.0, 2.0, 5.0],
                "relocation_count": [5, 3, 1, 1],
                "reconfiguration_count": [2, 2, 2, 2],
            }
        )
        recommendation = recommend_case(frame, "relocation_cost")
        self.assertEqual(recommendation["value"], 2.0)


if __name__ == "__main__":
    unittest.main()
