from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def apply_warm_start(model_vars: dict[str, Any], warm_start_dir: Path) -> dict[str, int]:
    """Result 형식의 CSV 파일을 읽어 Gurobi MIP start 값을 지정한다.

    warm_start_dir에는 필요한 파일만 있어도 된다.
    - purchased_machines.csv: x[p,j,l] 시작값
    - machine_states.csv: s[p,j,l,t], v[p,l,t] 시작값
    - reconfigurations.csv: y[p,j_prev,j_next,l,t] 시작값
    - material_flows.csv: f[p,left,q,right,t] 시작값

    논문 Figure 4 해를 CSV로 전사해두면 같은 방식으로 warm start에 사용할 수 있다.
    """
    warm_start_dir = Path(warm_start_dir)
    if not warm_start_dir.exists():
        raise FileNotFoundError(f"Warm start directory does not exist: {warm_start_dir}")

    x = model_vars["x"]
    s = model_vars["s"]
    y = model_vars["y"]
    v = model_vars["v"]
    f = model_vars["f"]

    assigned = {"x": 0, "s": 0, "y": 0, "v": 0, "f": 0}

    # CSV에 없는 변수는 Gurobi가 직접 보완하도록 둔다.
    # 이렇게 해야 Figure 4(a)처럼 일부 period만 전사한 partial start도 사용할 수 있다.

    assigned["x"] += _apply_purchased_machines(warm_start_dir / "purchased_machines.csv", x)
    state_counts = _apply_machine_states(warm_start_dir / "machine_states.csv", s, v)
    assigned["s"] += state_counts["s"]
    assigned["v"] += state_counts["v"]
    assigned["y"] += _apply_reconfigurations(warm_start_dir / "reconfigurations.csv", y)
    assigned["f"] += _apply_material_flows(warm_start_dir / "material_flows.csv", f)
    return assigned


def _read_optional_csv(path: Path) -> pd.DataFrame | None:
    """없거나 비어 있는 CSV는 건너뛴다."""
    if not path.exists() or path.stat().st_size == 0:
        return None
    return pd.read_csv(path)


def _apply_purchased_machines(path: Path, x) -> int:
    df = _read_optional_csv(path)
    if df is None:
        return 0

    count = 0
    for row in df.itertuples(index=False):
        key = (int(row.location), str(row.configuration), int(row.initial_operation))
        if key in x:
            x[key].Start = 1
            count += 1
    return count


def _apply_machine_states(path: Path, s, v) -> dict[str, int]:
    df = _read_optional_csv(path)
    if df is None:
        return {"s": 0, "v": 0}

    counts = {"s": 0, "v": 0}
    for row in df.itertuples(index=False):
        period = int(row.period)
        location = int(row.location)
        configuration = str(row.configuration)
        operation = int(row.operation)
        state_key = (location, configuration, operation, period)
        flow_key = (location, operation, period)

        if state_key in s:
            s[state_key].Start = 1
            counts["s"] += 1
        if hasattr(row, "flow") and flow_key in v:
            v[flow_key].Start = float(row.flow)
            counts["v"] += 1
    return counts


def _apply_reconfigurations(path: Path, y) -> int:
    df = _read_optional_csv(path)
    if df is None:
        return 0

    count = 0
    for row in df.itertuples(index=False):
        key = (
            int(row.location),
            str(row.from_configuration),
            str(row.to_configuration),
            int(row.operation),
            int(row.period),
        )
        if key in y:
            y[key].Start = 1
            count += 1
    return count


def _apply_material_flows(path: Path, f) -> int:
    df = _read_optional_csv(path)
    if df is None:
        return 0

    count = 0
    for row in df.itertuples(index=False):
        key = (
            int(row.from_location),
            int(row.from_operation),
            int(row.to_location),
            int(row.to_operation),
            int(row.period),
        )
        if key in f:
            f[key].Start = float(row.flow)
            count += 1
    return count
