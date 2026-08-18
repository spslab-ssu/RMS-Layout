from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from math import ceil, floor

import gurobipy as gp


PROFILE_FAMILIES = {
    "network": (),
    "network_counting": ("counting",),
    "network_theta": ("counting", "theta"),
    "network_mir": ("counting", "theta", "mir"),
}


@dataclass(frozen=True)
class CutSpec:
    family: str
    operation: int
    period: int
    theta: float
    rhs: float
    coefficients: tuple[tuple[str, float], ...]


@dataclass
class StrengtheningStats:
    profile: str
    families: tuple[str, ...]
    generated: int = 0
    added: int = 0
    pruned: int = 0
    generated_by_family: dict[str, int] | None = None
    added_by_family: dict[str, int] | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def resolve_profile(config) -> tuple[str, tuple[str, ...]]:
    profile = str(getattr(config, "STRENGTHENING_PROFILE", "network"))
    if profile not in PROFILE_FAMILIES:
        valid = ", ".join(PROFILE_FAMILIES)
        raise ValueError(f"Unknown STRENGTHENING_PROFILE={profile!r}. Choose one of: {valid}")
    return profile, PROFILE_FAMILIES[profile]


def add_strengthening_cuts(model, w, instance, config) -> StrengtheningStats:
    """PDF의 counting, theta, MIR valid inequalities를 추가한다."""
    profile, families = resolve_profile(config)
    stats = StrengtheningStats(
        profile=profile,
        families=families,
        generated_by_family={family: 0 for family in families},
        added_by_family={family: 0 for family in families},
    )
    if not families:
        return stats

    candidates: list[CutSpec] = []
    for period in instance.periods:
        for operation in instance.operations:
            demand = instance.operation_demand.get((period, operation), 0.0)
            if demand <= 0:
                continue
            rates = {
                configuration: instance.production_rate[configuration, operation]
                for configuration, feasible_operation in instance.feasible_pairs
                if feasible_operation == operation
            }
            candidates.extend(_cut_candidates(operation, period, demand, rates, families, config))

    stats.generated = len(candidates)
    for cut in candidates:
        stats.generated_by_family[cut.family] += 1

    if bool(getattr(config, "PRUNE_DOMINATED_CUTS", True)):
        selected = _nondominated(candidates)
    else:
        selected = candidates
    stats.pruned = len(candidates) - len(selected)

    for index, cut in enumerate(selected):
        coefficients = dict(cut.coefficients)
        expression = gp.quicksum(
            coefficient * w[location, configuration, cut.operation, cut.period]
            for configuration, coefficient in coefficients.items()
            for location in instance.install_locations
        )
        theta_label = f"{cut.theta:g}".replace(".", "p")
        model.addConstr(
            expression >= cut.rhs,
            name=(
                f"{cut.family}_cut[{cut.operation},{cut.period},"
                f"{theta_label},{index}]"
            ),
        )
        stats.added_by_family[cut.family] += 1
    stats.added = len(selected)
    return stats


def _cut_candidates(
    operation: int,
    period: int,
    demand: float,
    rates: dict[str, float],
    families: tuple[str, ...],
    config,
) -> list[CutSpec]:
    cuts: list[CutSpec] = []
    max_rate = max(rates.values())
    if "counting" in families:
        cuts.append(
            CutSpec(
                family="counting",
                operation=operation,
                period=period,
                theta=max_rate,
                rhs=float(_ceil_ratio(demand, max_rate)),
                coefficients=tuple((configuration, 1.0) for configuration in sorted(rates)),
            )
        )

    if not ({"theta", "mir"} & set(families)):
        return cuts

    configured = getattr(config, "THETA_VALUES", None)
    theta_values = (
        sorted({float(value) for value in configured if float(value) > 0})
        if configured
        else sorted({float(rate) for rate in rates.values()})
    )
    for theta in theta_values:
        rhs = float(_ceil_ratio(demand, theta))
        if "theta" in families:
            cuts.append(
                CutSpec(
                    family="theta",
                    operation=operation,
                    period=period,
                    theta=theta,
                    rhs=rhs,
                    coefficients=tuple(
                        (configuration, float(_ceil_ratio(rate, theta)))
                        for configuration, rate in sorted(rates.items())
                    ),
                )
            )

        if "mir" in families:
            scaled_demand = demand / theta
            fraction = scaled_demand - floor(scaled_demand)
            if fraction <= 1e-9 or 1.0 - fraction <= 1e-9:
                continue
            coefficients = []
            for configuration, rate in sorted(rates.items()):
                scaled_rate = rate / theta
                integer_part = floor(scaled_rate + 1e-9)
                rate_fraction = max(0.0, scaled_rate - integer_part)
                coefficient = integer_part + min(1.0, rate_fraction / fraction)
                coefficients.append((configuration, coefficient))
            cuts.append(
                CutSpec(
                    family="mir",
                    operation=operation,
                    period=period,
                    theta=theta,
                    rhs=rhs,
                    coefficients=tuple(coefficients),
                )
            )
    return cuts


def _ceil_ratio(numerator: float, denominator: float) -> int:
    return int(ceil(numerator / denominator - 1e-9))


def _nondominated(cuts: list[CutSpec]) -> list[CutSpec]:
    """같은 operation-period에서 정규화 계수가 더 약한 cut을 제거한다."""
    grouped: dict[tuple[int, int], list[CutSpec]] = defaultdict(list)
    for cut in cuts:
        grouped[cut.operation, cut.period].append(cut)

    kept: list[CutSpec] = []
    for group in grouped.values():
        nondominated: list[CutSpec] = []
        for candidate in group:
            if any(_dominates(existing, candidate) for existing in nondominated):
                continue
            nondominated = [
                existing for existing in nondominated if not _dominates(candidate, existing)
            ]
            nondominated.append(candidate)
        kept.extend(nondominated)
    return kept


def _dominates(left: CutSpec, right: CutSpec, tolerance: float = 1e-9) -> bool:
    left_coefficients = dict(left.coefficients)
    right_coefficients = dict(right.coefficients)
    if left_coefficients.keys() != right_coefficients.keys():
        return False
    left_normalized = {
        key: value / left.rhs for key, value in left_coefficients.items()
    }
    right_normalized = {
        key: value / right.rhs for key, value in right_coefficients.items()
    }
    no_weaker = all(
        left_normalized[key] <= right_normalized[key] + tolerance
        for key in left_normalized
    )
    strictly_stronger = any(
        left_normalized[key] < right_normalized[key] - tolerance
        for key in left_normalized
    )
    equivalent = all(
        abs(left_normalized[key] - right_normalized[key]) <= tolerance
        for key in left_normalized
    )
    return no_weaker and (strictly_stronger or equivalent)
