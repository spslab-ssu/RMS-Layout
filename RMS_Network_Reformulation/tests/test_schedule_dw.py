from __future__ import annotations

import unittest

import config
from Src.data import load_instance
from Src.milp import solve_milp
from Src.schedule_dw import enumerate_schedule_columns, solve_schedule_dw


class ScheduleDantzigWolfeTest(unittest.TestCase):
    def test_multi_part_column_count(self) -> None:
        instance = load_instance(_settings("multi_part"))
        self.assertEqual(len(enumerate_schedule_columns(instance)), 2880)

    def test_single_part_lp_is_equivalent_to_network_flow(self) -> None:
        settings = _settings("single_part")
        instance = load_instance(settings)
        network = solve_milp(instance, settings)
        schedule = solve_schedule_dw(instance, settings)
        self.assertEqual(network.summary["status_name"], "OPTIMAL")
        self.assertEqual(schedule.summary["status_name"], "OPTIMAL")
        self.assertAlmostEqual(network.summary["objective"], schedule.summary["objective"], places=5)


def _settings(problem: str):
    return config.build_config(
        problem_name=problem, profile="network_mir", TIME_LIMIT=60,
        MIP_GAP=0.0, OUTPUT_FLAG=0, THREADS=1, LP_RELAXATION=True,
        USE_SHARED_RESOURCES=False, OPTIMIZE_SHARED_RESOURCE_CAPACITY=False,
    )


if __name__ == "__main__":
    unittest.main()
