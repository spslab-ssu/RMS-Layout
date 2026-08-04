"""Gurobi MIP callback utilities for reproducible formulation comparisons."""

from __future__ import annotations

from math import isfinite

from gurobipy import GRB


class MIPProgressRecorder:
    """Record incumbent, bound, and gap without changing the optimization model."""

    def __init__(self, formulation: str, sample_interval: float = 5.0) -> None:
        self.formulation = formulation
        self.sample_interval = max(0.1, float(sample_interval))
        self.rows: list[dict] = []
        self._last_time = -self.sample_interval
        self._last_incumbent: float | None = None
        self._last_bound: float | None = None

    def __call__(self, model, where: int) -> None:
        if where != GRB.Callback.MIP:
            return
        runtime = float(model.cbGet(GRB.Callback.RUNTIME))
        incumbent = _finite_or_none(model.cbGet(GRB.Callback.MIP_OBJBST))
        bound = _finite_or_none(model.cbGet(GRB.Callback.MIP_OBJBND))
        incumbent_changed = _changed(incumbent, self._last_incumbent, improvement="down")
        bound_changed = _changed(bound, self._last_bound, improvement="up")
        periodic = runtime - self._last_time >= self.sample_interval
        if not (incumbent_changed or bound_changed or periodic):
            return
        self._append(
            runtime=runtime,
            incumbent=incumbent,
            bound=bound,
            node_count=float(model.cbGet(GRB.Callback.MIP_NODCNT)),
            solution_count=int(model.cbGet(GRB.Callback.MIP_SOLCNT)),
            event=(
                "incumbent"
                if incumbent_changed
                else "bound"
                if bound_changed
                else "interval"
            ),
        )

    def finish(self, model) -> None:
        incumbent = float(model.ObjVal) if model.SolCount else None
        bound = _finite_or_none(model.ObjBound)
        self._append(
            runtime=float(model.Runtime),
            incumbent=incumbent,
            bound=bound,
            node_count=float(model.NodeCount),
            solution_count=int(model.SolCount),
            event="final",
            force=True,
        )

    def _append(
        self,
        runtime: float,
        incumbent: float | None,
        bound: float | None,
        node_count: float,
        solution_count: int,
        event: str,
        force: bool = False,
    ) -> None:
        if not force and self.rows and runtime < self.rows[-1]["runtime_seconds"]:
            return
        gap = _relative_gap(incumbent, bound)
        self.rows.append(
            {
                "formulation": self.formulation,
                "runtime_seconds": round(runtime, 6),
                "incumbent": incumbent,
                "best_bound": bound,
                "relative_gap": gap,
                "gap_percent": None if gap is None else 100.0 * gap,
                "node_count": node_count,
                "solution_count": solution_count,
                "event": event,
            }
        )
        self._last_time = runtime
        if incumbent is not None:
            self._last_incumbent = incumbent
        if bound is not None:
            self._last_bound = bound


def _finite_or_none(value) -> float | None:
    value = float(value)
    return value if isfinite(value) and abs(value) < GRB.INFINITY else None


def _relative_gap(incumbent: float | None, bound: float | None) -> float | None:
    if incumbent is None or bound is None:
        return None
    return abs(incumbent - bound) / max(abs(incumbent), 1e-10)


def _changed(value: float | None, previous: float | None, improvement: str) -> bool:
    if value is None:
        return False
    if previous is None:
        return True
    tolerance = 1e-7 * max(1.0, abs(previous))
    return value < previous - tolerance if improvement == "down" else value > previous + tolerance
