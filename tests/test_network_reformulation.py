from __future__ import annotations

import unittest

import config
from Src.data import load_instance
from Src.milp import solve_milp


EXPECTED_LP = {
    "network": 22162.618038,
    "network_counting": 22612.662465,
    "network_theta": 22619.8,
    "network_mir": 22674.8,
}


class NetworkReformulationTest(unittest.TestCase):
    def test_example1_lp_bounds(self) -> None:
        for profile, expected in EXPECTED_LP.items():
            with self.subTest(profile=profile):
                solution = _solve(profile, lp_relaxation=True)
                self.assertEqual(solution.summary["status_name"], "OPTIMAL")
                self.assertAlmostEqual(solution.summary["objective"], expected, places=5)

    def test_network_mir_integer_optimum(self) -> None:
        solution = _solve("network_mir", lp_relaxation=False)
        self.assertEqual(solution.summary["status_name"], "OPTIMAL")
        self.assertEqual(solution.summary["objective"], 22910.0)
        self.assertEqual(solution.summary["model_size"]["binary_variables"], 832)


def _solve(profile: str, lp_relaxation: bool):
    settings = config.build_config(
        problem_name="single_part",
        profile=profile,
        TIME_LIMIT=60,
        MIP_GAP=0.0,
        OUTPUT_FLAG=0,
        LP_RELAXATION=lp_relaxation,
        USE_SHARED_RESOURCES=False,
    )
    return solve_milp(load_instance(settings), settings)


if __name__ == "__main__":
    unittest.main()
