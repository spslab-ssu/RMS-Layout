"""Relocation extension for the lifecycle-network formulation.

All constraints in this module belong to layer (ii), the cross-location
coupling layer.  Keeping them here prevents the baseline lifecycle equations
from being mixed with experimental physical-policy assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from math import isfinite
from typing import Any, Mapping

import gurobipy as gp
from gurobipy import GRB


TransitionKey = tuple[int, int, str, int, str, int, int]


@dataclass(frozen=True)
class RelocationPolicy:
    enabled: bool
    distance_cost: float
    fixed_cost: float
    downtime_fraction: float
    crew_capacity: int | Mapping[int, int] | None
    forbid_reverse_swaps: bool
    congestion_cost_step: float

    @classmethod
    def from_config(cls, config: Any) -> "RelocationPolicy":
        policy = cls(
            enabled=bool(getattr(config, "ENABLE_RELOCATION", False)),
            distance_cost=float(getattr(config, "RELOCATION_DISTANCE_COST", 1.0)),
            fixed_cost=float(getattr(config, "RELOCATION_FIXED_COST", 0.0)),
            downtime_fraction=float(getattr(config, "RELOCATION_DOWNTIME_FRACTION", 0.0)),
            crew_capacity=getattr(config, "RELOCATION_CREW_CAPACITY", None),
            forbid_reverse_swaps=bool(getattr(config, "FORBID_REVERSE_SWAPS", False)),
            congestion_cost_step=float(getattr(config, "RELOCATION_CONGESTION_COST_STEP", 0.0)),
        )
        policy.validate()
        return policy

    def validate(self) -> None:
        if self.distance_cost < 0 or self.fixed_cost < 0:
            raise ValueError("Relocation distance/fixed costs must be nonnegative.")
        if not 0.0 <= self.downtime_fraction <= 1.0:
            raise ValueError("RELOCATION_DOWNTIME_FRACTION must be in [0, 1].")
        if self.congestion_cost_step < 0:
            raise ValueError("RELOCATION_CONGESTION_COST_STEP must be nonnegative.")
        capacities = (
            self.crew_capacity.values()
            if isinstance(self.crew_capacity, Mapping)
            else [self.crew_capacity]
        )
        if any(
            value is not None
            and (not isfinite(float(value)) or int(value) != value or value < 0)
            for value in capacities
        ):
            raise ValueError("Relocation crew capacities must be nonnegative integers or None.")

    def crew_limit(self, period: int) -> int | None:
        if isinstance(self.crew_capacity, Mapping):
            value = self.crew_capacity.get(period)
        else:
            value = self.crew_capacity
        return None if value is None else int(value)

    def to_dict(self) -> dict[str, Any]:
        crew = dict(self.crew_capacity) if isinstance(self.crew_capacity, Mapping) else self.crew_capacity
        return {
            "enabled": self.enabled,
            "distance_cost": self.distance_cost,
            "fixed_cost": self.fixed_cost,
            "downtime_fraction": self.downtime_fraction,
            "crew_capacity": crew,
            "forbid_reverse_swaps": self.forbid_reverse_swaps,
            "congestion_cost_step": self.congestion_cost_step,
        }


def build_transition_keys(instance: Any, policy: RelocationPolicy) -> tuple[list[TransitionKey], list[TransitionKey]]:
    """Return detailed stay and move arcs for the time-expanded network."""
    periods = list(zip(instance.periods[:-1], instance.periods[1:]))
    stay: list[TransitionKey] = []
    move: list[TransitionKey] = []
    destination_locations = instance.install_locations if policy.enabled else []
    for p_prev in instance.install_locations:
        next_locations = [p_prev] + [p for p in destination_locations if p != p_prev]
        for p_next in next_locations:
            target = stay if p_prev == p_next else move
            for j_prev, l_prev in instance.feasible_pairs:
                for j_next, l_next in instance.feasible_pairs:
                    if (j_prev, j_next) not in instance.reconfiguration_cost:
                        continue
                    for _, next_t in periods:
                        target.append((p_prev, p_next, j_prev, l_prev, j_next, l_next, next_t))
    return stay, move


def add_transition_variables(
    model: gp.Model,
    stay_keys: list[TransitionKey],
    move_keys: list[TransitionKey],
) -> dict[TransitionKey, gp.Var]:
    stay = model.addVars(stay_keys, lb=0.0, ub=1.0, name="lifecycle_transition")
    move = model.addVars(
        move_keys,
        lb=0.0,
        ub=1.0,
        name="relocation_transition",
    )
    return {**stay, **move}


def effective_capacity(
    instance: Any,
    w: Any,
    z: Mapping[TransitionKey, gp.Var],
    move_keys: list[TransitionKey],
    p: int,
    operation: int,
    period: int,
    downtime_fraction: float,
) -> gp.LinExpr:
    """Capacity after charging downtime to machines arriving in this period."""
    nominal = gp.quicksum(
        instance.production_rate[j, operation] * w[p, j, operation, period]
        for j, l in instance.feasible_pairs
        if l == operation
    )
    if downtime_fraction <= 0 or period == instance.periods[0]:
        return nominal
    lost = gp.quicksum(
        instance.production_rate[j_next, operation] * z[key]
        for key in move_keys
        for p_prev, p_next, _j_prev, _l_prev, j_next, l_next, next_t in [key]
        if p_next == p and l_next == operation and next_t == period
    )
    return nominal - downtime_fraction * lost


def add_relocation_policy(
    model: gp.Model,
    instance: Any,
    z: Mapping[TransitionKey, gp.Var],
    move_keys: list[TransitionKey],
    policy: RelocationPolicy,
    lp_relaxation: bool,
) -> tuple[gp.LinExpr, gp.LinExpr, dict[int, gp.LinExpr]]:
    """Add layer-(ii) physical constraints and return relocation cost terms."""
    if not policy.enabled:
        return gp.LinExpr(0.0), gp.LinExpr(0.0), {
            t: gp.LinExpr(0.0) for t in instance.periods[1:]
        }

    # A binary choice at (origin, destination, previous configuration,
    # next configuration, period) prevents continuous detailed arcs from
    # splitting one physical machine across multiple transitions. Operation
    # indices remain continuous and are pinned by the binary occupied states.
    grouped_arcs: dict[tuple[int, int, str, str, int], list[TransitionKey]] = defaultdict(list)
    for key in z:
        p, q, j_prev, _l_prev, j_next, _l_next, t = key
        grouped_arcs[p, q, j_prev, j_next, t].append(key)
    transition_keys = sorted(grouped_arcs)
    indicator_type = GRB.CONTINUOUS if lp_relaxation else GRB.BINARY
    transition_choice = model.addVars(
        transition_keys,
        lb=0.0,
        ub=1.0,
        vtype=indicator_type,
        name="physical_transition_choice",
    )
    for key in transition_keys:
        model.addConstr(
            transition_choice[key] == gp.quicksum(z[arc] for arc in grouped_arcs[key]),
            name=f"physical_transition_link[{','.join(map(str, key))}]",
        )

    moves_by_period = {
        t: gp.quicksum(
            transition_choice[key]
            for key in transition_keys
            if key[0] != key[1] and key[-1] == t
        )
        for t in instance.periods[1:]
    }

    for t, move_count in moves_by_period.items():
        limit = policy.crew_limit(t)
        if limit is not None:
            model.addConstr(move_count <= limit, name=f"relocation_crew_capacity[{t}]")

    if policy.forbid_reverse_swaps:
        for t in instance.periods[1:]:
            for index, p in enumerate(instance.install_locations):
                for q in instance.install_locations[index + 1 :]:
                    forward = gp.quicksum(
                        transition_choice[key]
                        for key in transition_keys
                        if key[0] == p and key[1] == q and key[-1] == t
                    )
                    reverse = gp.quicksum(
                        transition_choice[key]
                        for key in transition_keys
                        if key[0] == q and key[1] == p and key[-1] == t
                    )
                    model.addConstr(forward + reverse <= 1, name=f"no_reverse_swap[{p},{q},{t}]")

    direct_cost = gp.quicksum(
        (policy.distance_cost * instance.distance[p, q] + policy.fixed_cost)
        * transition_choice[p, q, j_prev, j_next, t]
        for p, q, j_prev, j_next, t in transition_keys
        if p != q
    )

    # Breakthrough extension: an ordered set of increasingly expensive crew
    # slots gives a convex, endogenous congestion penalty.  Unlike a hard R,
    # this avoids an artificial all-or-nothing sensitivity response.
    congestion_cost = gp.LinExpr(0.0)
    if policy.congestion_cost_step > 0 and move_keys:
        slot_keys = [
            (t, rank)
            for t in instance.periods[1:]
            for rank in range(1, len(instance.install_locations) + 1)
        ]
        slot_type = GRB.CONTINUOUS if lp_relaxation else GRB.BINARY
        slots = model.addVars(slot_keys, lb=0.0, ub=1.0, vtype=slot_type, name="relocation_crew_slot")
        for t in instance.periods[1:]:
            model.addConstr(
                moves_by_period[t]
                == gp.quicksum(slots[t, rank] for rank in range(1, len(instance.install_locations) + 1)),
                name=f"relocation_slot_count[{t}]",
            )
            for rank in range(1, len(instance.install_locations)):
                model.addConstr(slots[t, rank] >= slots[t, rank + 1], name=f"relocation_slot_order[{t},{rank}]")
        congestion_cost = gp.quicksum(
            policy.congestion_cost_step * rank * slots[t, rank]
            for t, rank in slot_keys
        )

    return direct_cost, congestion_cost, moves_by_period
