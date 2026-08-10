from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from Src.adaptive_milp import solve_adaptive_milp
from Src.data import RMSInstance
from Src.network_adaptive import solve_network_adaptive_milp
from Src.online_adaptive import solve_online_adaptive


class AdaptiveFormulationEquivalenceTest(unittest.TestCase):
    def test_both_formulations_choose_the_same_relocation_plan(self) -> None:
        instance = _tiny_relocation_instance()
        settings = SimpleNamespace(
            TIME_LIMIT=30,
            MIP_GAP=0.0,
            OUTPUT_FLAG=0,
            SEED=1,
            THREADS=1,
            ADAPTIVE_MAX_ASSETS=2,
            NETWORK_BINARY_ARCS=True,
            RELOCATION_COST_PER_DISTANCE=0.1,
            RELOCATION_FIXED_COST=0.0,
            FIXED_PURCHASES=None,
        )

        paper = solve_adaptive_milp(instance, settings)
        network = solve_network_adaptive_milp(instance, settings)

        self.assertEqual(paper.summary["status_name"], "OPTIMAL")
        self.assertEqual(network.summary["status_name"], "OPTIMAL")
        self.assertAlmostEqual(paper.summary["objective"], network.summary["objective"], places=6)
        self.assertEqual(paper.summary["relocation_count"], 2)
        self.assertEqual(network.summary["relocation_count"], 2)
        self.assertEqual(paper.cost_breakdown, network.cost_breakdown)

    def test_period_one_decision_does_not_depend_on_unrevealed_period_two_demand(self) -> None:
        first_instance = _tiny_relocation_instance()
        changed_future = deepcopy(first_instance)
        changed_future.arc_demand = {
            key: value for key, value in changed_future.arc_demand.items() if key[0] == 1
        }
        settings = SimpleNamespace(
            TIME_LIMIT=30,
            MIP_GAP=0.0,
            OUTPUT_FLAG=0,
            SEED=1,
            THREADS=1,
            RELOCATION_COST_PER_DISTANCE=0.1,
            RELOCATION_FIXED_COST=0.0,
        )

        first = solve_online_adaptive(first_instance, settings)
        second = solve_online_adaptive(changed_future, settings)
        first_period_purchases = [
            (row["location"], row["configuration"], row["initial_operation"])
            for row in first.purchased_machines
            if row["period"] == 1
        ]
        changed_future_purchases = [
            (row["location"], row["configuration"], row["initial_operation"])
            for row in second.purchased_machines
            if row["period"] == 1
        ]
        self.assertEqual(first_period_purchases, changed_future_purchases)
        self.assertFalse(first.summary["period_solves"][0]["future_demand_used"])


def _tiny_relocation_instance() -> RMSInstance:
    # Period 1 route is START->1->2->END; period 2 reverses operations.
    # M1 can only perform op1 and M2 only op2, so the optimal adaptive plan
    # physically swaps the two machines between locations.
    locations = {
        1: {"x": 0.0, "y": 0.0, "type": "install"},
        2: {"x": 10.0, "y": 0.0, "type": "install"},
        3: {"x": -1.0, "y": 0.0, "type": "start"},
        4: {"x": 11.0, "y": 0.0, "type": "end"},
    }
    distance = {
        (p, q): abs(float(locations[p]["x"]) - float(locations[q]["x"]))
        for p in locations
        for q in locations
    }
    arc_demand = {
        (1, 0, 1): 1.0,
        (1, 1, 2): 1.0,
        (1, 2, 999): 1.0,
        (2, 0, 2): 1.0,
        (2, 2, 1): 1.0,
        (2, 1, 999): 1.0,
    }
    return RMSInstance(
        problem_name="tiny_relocation",
        location_file=Path("locations.csv"),
        configuration_file=Path("configurations.csv"),
        production_rate_file=Path("production_rates.csv"),
        demand_file=Path("demands.csv"),
        parameter_file=Path("parameters.csv"),
        shared_resource_file=None,
        resource_requirement_file=None,
        periods=[1, 2],
        install_locations=[1, 2],
        all_locations=[1, 2, 3, 4],
        operations=[1, 2],
        configurations=["j1", "j2"],
        feasible_pairs=[("j1", 1), ("j2", 2)],
        route_arcs=[(0, 1), (1, 2), (2, 999), (0, 2), (2, 1), (1, 999)],
        locations=locations,
        cost={"j1": 0.0, "j2": 0.0},
        machine={"j1": "M1", "j2": "M2"},
        basic_modules={"j1": set(), "j2": set()},
        auxiliary_modules={"j1": set(), "j2": set()},
        modules={"j1": set(), "j2": set()},
        shared_resource_capacity={},
        resource_requirement={},
        production_rate={("j1", 1): 1.0, ("j2", 2): 1.0},
        reconfiguration_cost={("j1", "j1"): 0.0, ("j2", "j2"): 0.0},
        distance=distance,
        arc_demand=arc_demand,
        parameters={"material_handling_cost": 1.0},
        start_location=3,
        end_location=4,
        start_operation=0,
        end_operation=999,
    )


if __name__ == "__main__":
    unittest.main()
