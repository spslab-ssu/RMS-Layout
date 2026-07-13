from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class RMSInstance:
    """MILP 모델이 바로 사용할 수 있도록 정리된 RMS Layout 인스턴스."""

    problem_name: str
    location_file: Path
    configuration_file: Path
    production_rate_file: Path
    demand_file: Path
    parameter_file: Path

    periods: list[int]
    install_locations: list[int]
    all_locations: list[int]
    operations: list[int]
    configurations: list[str]
    feasible_pairs: list[tuple[str, int]]
    route_arcs: list[tuple[int, int]]

    locations: dict[int, dict[str, float | str]]
    cost: dict[str, float]
    machine: dict[str, str]
    modules: dict[str, set[int]]          # basic+auxiliary 합본 (재구성 비용 계산용)
    resource_use: dict[str, set[int]]     # a_rj: configuration j가 사용하는 자원 r 집합 (현재 r=auxiliary module)
    resource_capacity: dict[int, float]   # Capa_r: {자원 r: 보유량}. 없는 자원은 무제한
    production_rate: dict[tuple[str, int], float]
    reconfiguration_cost: dict[tuple[str, str], float]
    distance: dict[tuple[int, int], float]
    arc_demand: dict[tuple[int, int, int], float]
    parameters: dict[str, float]

    start_location: int
    end_location: int
    start_operation: int
    end_operation: int


def load_instance(config) -> RMSInstance:
    """CSV 파일을 읽고 MILP 모델용 인스턴스로 전처리한다.

    이 파일이 CSV schema와 모델 사이의 완충층이다.
    CSV 구조가 바뀌면 가능하면 여기만 수정한다.
    """
    params = _read_parameters(config.PARAMETER_FILE) 
    locations_df = pd.read_csv(config.LOCATION_FILE)
    configs_df = pd.read_csv(config.CONFIGURATION_FILE)
    rates_df = pd.read_csv(config.PRODUCTION_RATE_FILE)
    demand_df = pd.read_csv(config.DEMAND_FILE)

    periods = _periods_from_demand(demand_df, params)
    start_location = int(params["start_location"])
    end_location = int(params["end_location"])
    start_operation = int(config.START_OPERATION)
    end_operation = int(config.END_OPERATION)

    locations = {
        int(row.location): {"x": float(row.x), "y": float(row.y), "type": str(row.type)}
        for row in locations_df.itertuples(index=False)
    }
    install_locations = sorted(p for p, row in locations.items() if row["type"] == "install")
    all_locations = sorted(locations)

    cost = {str(row.configuration): float(row.cost) for row in configs_df.itertuples(index=False)}
    machine = {str(row.configuration): str(row.machine) for row in configs_df.itertuples(index=False)}
    modules = {
        str(row.configuration): _parse_modules(row.basic_modules) | _parse_modules(row.auxiliary_modules)
        for row in configs_df.itertuples(index=False)
    }
    resource_use = {
        str(row.configuration): _parse_modules(row.auxiliary_modules)
        for row in configs_df.itertuples(index=False)
    }
    resource_capacity = _read_resource_capacities(getattr(config, "RESOURCE_CAPACITY_FILE", None))
    production_rate = {
        (str(row.configuration), int(row.operation)): float(row.production_rate)
        for row in rates_df.itertuples(index=False)
    }

    operations, route_arcs, arc_demand = _build_arc_demand(
        demand_df=demand_df,
        periods=periods,
        start_operation=start_operation,
        end_operation=end_operation,
    )

    feasible_pairs = sorted(
        (cfg, op)
        for (cfg, op), rate in production_rate.items()
        if op in operations and rate > 0
    )
    configurations = sorted({cfg for cfg, _ in feasible_pairs})

    missing_ops = sorted(set(operations) - {op for _, op in feasible_pairs})
    if missing_ops:
        raise ValueError(f"처리 가능한 configuration이 없는 operation: {missing_ops}")

    reconfiguration_cost = _build_reconfiguration_cost(
        configurations=configurations,
        machine=machine,
        modules=modules,
        add_cost=params["add_module_cost"],
        remove_cost=params["remove_module_cost"],
        same_machine_only=bool(config.SAME_MACHINE_RECONFIG_ONLY),
    )
    distance = {(p, q): _distance(locations, p, q) for p in all_locations for q in all_locations}

    return RMSInstance(
        problem_name=config.PROBLEM_NAME,
        location_file=config.LOCATION_FILE,
        configuration_file=config.CONFIGURATION_FILE,
        production_rate_file=config.PRODUCTION_RATE_FILE,
        demand_file=config.DEMAND_FILE,
        parameter_file=config.PARAMETER_FILE,
        periods=periods,                                #생산기간 T
        install_locations=install_locations,            #RMT 설치 가능한 위치 P
        all_locations=all_locations, 
        operations=operations,                          #필요한 operation L
        configurations=configurations,                  #사용가능한 configuration J
        feasible_pairs=feasible_pairs,                  #가능한 configurtion-operation pair (j,l)
        route_arcs=route_arcs,                          # 공정흐름 ex) start > 5 > 1 > 17 > end
        locations=locations,
        cost=cost,                                      #configuration별 cost c_j
        machine=machine,
        modules=modules,
        resource_use=resource_use,                      #a_rj: configuration별 사용 자원 집합 (현재 r=auxiliary module)
        resource_capacity=resource_capacity,            #Capa_r: 공유 자원 보유량 {r: capa}
        production_rate=production_rate,                #configuration-operation별 생산률 B_ij
        reconfiguration_cost=reconfiguration_cost,      #configuration 변경비용 r_ij
        distance=distance,                              #location별 Manhattan distance D_pp'    
        arc_demand=arc_demand,                          #period별 arc demand d_tll' (t,l,l')   
        parameters=params,                              #MHC, add/remove module cost, start/end location, period count 등
        start_location=start_location,
        end_location=end_location,
        start_operation=start_operation,
        end_operation=end_operation,
    )


def _read_parameters(path: Path) -> dict[str, float]:
    """parameter,value CSV를 dict로 읽는다."""
    df = pd.read_csv(path)
    return {str(row.parameter): float(row.value) for row in df.itertuples(index=False)}


def _read_resource_capacities(path) -> dict[int, float]:
    """resource,capacity CSV를 dict로 읽는다. 파일이 없으면 빈 dict(=제약 없음)."""
    if path is None or not Path(path).exists():
        return {}
    df = pd.read_csv(path)
    return {int(row.resource): float(row.capacity) for row in df.itertuples(index=False)}


def _parse_modules(value) -> set[int]:
    """'1;5;13' 형태의 module 문자열을 set[int]로 변환한다."""
    if pd.isna(value) or str(value).strip() == "":
        return set()
    text = str(value).replace(",", ";").replace("/", ";").replace(" ", "")
    return {int(token) for token in text.split(";") if token}


def _periods_from_demand(demand_df: pd.DataFrame, params: dict[str, float]) -> list[int]:
    """period_count가 있으면 그 값을 우선하고, 없으면 demand 컬럼에서 period를 찾는다."""
    if "period_count" in params:
        return list(range(1, int(params["period_count"]) + 1))
    period_cols = [col for col in demand_df.columns if col.startswith("period")]
    return sorted(int(col.replace("period", "")) for col in period_cols)


def _build_arc_demand(
    demand_df: pd.DataFrame,
    periods: list[int],
    start_operation: int,
    end_operation: int,
) -> tuple[list[int], list[tuple[int, int]], dict[tuple[int, int, int], float]]:
    """part별 route와 demand를 route arc별 demand로 집계한다.

    단일부품도 parts가 1개인 다중부품으로 취급한다.
    따라서 MILP 모델은 single/multi를 구분하지 않고 arc_demand만 사용한다.
    """
    operations: set[int] = set()
    route_arcs: set[tuple[int, int]] = set()
    arc_demand: dict[tuple[int, int, int], float] = defaultdict(float)

    for row in demand_df.itertuples(index=False):
        route = [int(op) for op in str(row.operation_sequence).split(">")]
        operations.update(route)
        full_route = [start_operation] + route + [end_operation]
        arcs = list(zip(full_route[:-1], full_route[1:]))
        route_arcs.update(arcs)

        for t in periods:
            demand_value = float(getattr(row, f"period{t}"))
            if demand_value <= 0:
                continue
            for left, right in arcs:
                arc_demand[(t, left, right)] += demand_value

    return sorted(operations), sorted(route_arcs), dict(arc_demand)


def _build_reconfiguration_cost(
    configurations: list[str],
    machine: dict[str, str],
    modules: dict[str, set[int]],
    add_cost: float,
    remove_cost: float,
    same_machine_only: bool,
) -> dict[tuple[str, str], float]:
    """module 추가/제거 비용으로 r_jj'를 계산한다."""
    costs: dict[tuple[str, str], float] = {}
    for prev in configurations:
        for nxt in configurations:
            if same_machine_only and machine[prev] != machine[nxt]:
                continue
            prev_modules = modules[prev]
            next_modules = modules[nxt]
            costs[(prev, nxt)] = add_cost * len(next_modules - prev_modules) + remove_cost * len(prev_modules - next_modules)
    return costs


def _distance(locations: dict[int, dict[str, float | str]], p: int, q: int) -> float:
    """논문 정의의 Manhattan distance D_pp'."""
    return abs(float(locations[p]["x"]) - float(locations[q]["x"])) + abs(
        float(locations[p]["y"]) - float(locations[q]["y"])
    )
