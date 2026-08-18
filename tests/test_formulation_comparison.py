from __future__ import annotations

import unittest

import config
from Src.base_milp import solve_base_milp
from Src.data import load_instance
from Src.milp import solve_milp


class FormulationComparisonTest(unittest.TestCase):
    def test_base_and_network_have_same_integer_optimum(self) -> None:
        base = _solve("base", lp_relaxation=False)
        network = _solve("network_mir", lp_relaxation=False)
        self.assertEqual(base.summary["status_name"], "OPTIMAL")
        self.assertEqual(network.summary["status_name"], "OPTIMAL")
        self.assertEqual(base.summary["objective"], 22910.0)
        self.assertEqual(network.summary["objective"], base.summary["objective"])
        self.assertEqual(base.summary["model_size"]["binary_variables"], 1856)
        self.assertEqual(network.summary["model_size"]["binary_variables"], 832)

    def test_network_lp_bound_dominates_base(self) -> None:
        base = _solve("base", lp_relaxation=True)
        network = _solve("network", lp_relaxation=True)
        strengthened = _solve("network_mir", lp_relaxation=True)
        self.assertLess(base.summary["objective"], network.summary["objective"])
        self.assertLess(network.summary["objective"], strengthened.summary["objective"])


def _solve(formulation: str, lp_relaxation: bool):
    profile = "network_mir" if formulation == "network_mir" else "network"
    settings = config.build_config(
        problem_name="single_part",
        profile=profile,
        TIME_LIMIT=120,
        MIP_GAP=0.0,
        OUTPUT_FLAG=0,
        SEED=1,
        THREADS=0,
        LP_RELAXATION=lp_relaxation,
        USE_SHARED_RESOURCES=False,
    )
    instance = load_instance(settings)
    return (
        solve_base_milp(instance, settings)
        if formulation == "base"
        else solve_milp(instance, settings)
    )


if __name__ == "__main__":
    unittest.main()
