"""Helpers for runs that record only the initial LP relaxation."""

from types import SimpleNamespace


def make_lp_only_solution(model, instance, lp_bound):
    """Return the small solution-like object expected by experiment runners."""
    return SimpleNamespace(
        summary={
            "problem_name": instance.problem_name,
            "model_type": getattr(instance, "problem_name", "rms"),
            "status": 2,
            "status_name": "LP_OPTIMAL" if lp_bound is not None else "LP_NO_OPTIMUM",
            "lp_relaxation_bound": lp_bound,
            "lp_relaxation_seconds": getattr(model, "_lp_relaxation_seconds", None),
            "objective": None,
            "best_bound": None,
            "best_bound_c": None,
            "mip_gap": None,
            "runtime_seconds": None,
            "num_vars": int(model.NumVars),
            "num_constraints": int(model.NumConstrs),
        },
        cost_breakdown={},
    )
