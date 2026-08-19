from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

import config
from Src.data import RMSInstance
from Src.milp import solve_milp
from Src.output import save_solution
from Src.visualize import draw_layouts


class RelocationPolicyTest(unittest.TestCase):
    def test_relocation_improves_a_reversed_route(self) -> None:
        solution = _solve()
        self.assertEqual(solution.summary["status_name"], "OPTIMAL")
        self.assertEqual(solution.summary["relocation_count"], 2)
        self.assertAlmostEqual(solution.summary["objective"], 26.0)
        self.assertEqual(
            solution.summary["objective_hierarchy"],
            ["system_cost", "relocation_count"],
        )
        self.assertAlmostEqual(solution.summary["primary_stage"]["objective"], 26.0)
        self.assertEqual(solution.summary["relocation_stage"]["objective"], 2.0)
        self.assertTrue(solution.summary["lexicographic_optimal"])
        occupied = [
            (row["period"], row["location"]) for row in solution.machine_states
        ]
        self.assertEqual(len(occupied), len(set(occupied)))

    def test_secondary_stage_removes_cost_neutral_moves(self) -> None:
        instance = _tiny_relocation_instance()
        instance.parameters["material_handling_cost"] = 0.0
        solution = _solve(instance=instance, RELOCATION_DISTANCE_COST=0.0)
        self.assertEqual(solution.summary["objective"], 0.0)
        self.assertEqual(solution.summary["relocation_count"], 0)
        self.assertEqual(solution.summary["minimum_relocation_count"], 0.0)
        self.assertEqual(solution.summary["relocation_stage"]["status_name"], "OPTIMAL")

    def test_both_stage_results_and_comparison_figures_are_saved(self) -> None:
        instance = _tiny_relocation_instance()
        solution = _solve(instance=instance, RELOCATION_DISTANCE_COST=0.0)
        with tempfile.TemporaryDirectory() as temp_dir:
            result_dir = Path(temp_dir)
            save_solution(solution, result_dir)
            draw_layouts(result_dir, instance)
            self.assertTrue((result_dir / "stage_1_system_cost" / "machine_states.csv").exists())
            self.assertTrue((result_dir / "stage_2_min_relocation" / "machine_states.csv").exists())
            self.assertTrue(
                (
                    result_dir
                    / "figures"
                    / "stage_comparison"
                    / "stage_comparison_period_2.png"
                ).exists()
            )

    def test_stage_one_pool_keeps_multiple_equal_cost_configurations(self) -> None:
        instance = _tiny_relocation_instance()
        instance.parameters["material_handling_cost"] = 0.0
        solution = _solve(
            instance=instance,
            RELOCATION_DISTANCE_COST=0.0,
            STAGE_ONE_CONFIGURATION_LIMIT=4,
        )
        self.assertGreaterEqual(len(solution.stage_one_candidates), 2)
        self.assertTrue(
            all(candidate["system_cost"] == 0.0 for candidate in solution.stage_one_candidates)
        )

    def test_crew_capacity_prevents_an_in_place_two_machine_swap(self) -> None:
        solution = _solve(RELOCATION_CREW_CAPACITY=1)
        self.assertEqual(solution.summary["status_name"], "OPTIMAL")
        self.assertEqual(solution.summary["relocation_count"], 0)
        self.assertAlmostEqual(solution.summary["objective"], 44.0)

    def test_downtime_can_make_relocation_infeasible_for_full_load(self) -> None:
        solution = _solve(RELOCATION_DOWNTIME_FRACTION=0.25)
        self.assertEqual(solution.summary["relocation_count"], 0)
        self.assertAlmostEqual(solution.summary["objective"], 44.0)

    def test_reverse_swap_constraint_blocks_direct_exchange(self) -> None:
        solution = _solve(FORBID_REVERSE_SWAPS=True)
        self.assertEqual(solution.summary["relocation_count"], 0)

    def test_total_relocation_cap_is_enforced(self) -> None:
        solution = _solve(MAX_TOTAL_RELOCATIONS=0)
        self.assertEqual(solution.summary["status_name"], "OPTIMAL")
        self.assertEqual(solution.summary["relocation_count"], 0)
        self.assertAlmostEqual(solution.summary["objective"], 44.0)

    def test_convex_crew_slots_remove_the_bang_bang_move(self) -> None:
        low_friction = _solve(RELOCATION_CONGESTION_COST_STEP=1.0)
        high_friction = _solve(RELOCATION_CONGESTION_COST_STEP=7.0)
        self.assertEqual(low_friction.summary["relocation_count"], 2)
        self.assertEqual(high_friction.summary["relocation_count"], 0)
        self.assertEqual(low_friction.cost_breakdown["relocation_congestion_cost"], 3.0)


def _solve(instance=None, **overrides):
    settings_overrides = {
        "TIME_LIMIT": 30,
        "MIP_GAP": 0.0,
        "OUTPUT_FLAG": 0,
        "SEED": 1,
        "THREADS": 1,
        "USE_SHARED_RESOURCES": False,
        "ENABLE_RELOCATION": True,
        "RELOCATION_DISTANCE_COST": 0.1,
        "RELOCATION_FIXED_COST": 0.0,
    }
    settings_overrides.update(overrides)
    settings = config.build_config(
        problem_name="single_part",
        profile="network",
        **settings_overrides,
    )
    return solve_milp(instance or _tiny_relocation_instance(), settings)


def _tiny_relocation_instance() -> RMSInstance:
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
        operation_demand={(1, 1): 1.0, (1, 2): 1.0, (2, 1): 1.0, (2, 2): 1.0},
        parameters={"material_handling_cost": 1.0},
        start_location=3,
        end_location=4,
        start_operation=0,
        end_operation=999,
    )


if __name__ == "__main__":
    unittest.main()
