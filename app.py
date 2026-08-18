"""Research-friendly Streamlit UI for RMS relocation experiments."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import config
from Src.data import load_instance
from Src.milp import solve_milp
from Src.output import save_solution
from Src.scenario import build_grid_locations, prepare_scenario_directory
from Src.sensitivity import (
    build_cost_cases,
    build_grid_cases,
    parse_numeric_levels,
    recommend_case,
    run_sensitivity,
)
from Src.visualize import draw_layouts


st.set_page_config(page_title="RMS relocation 실험실", layout="wide")
st.title("RMS relocation 실험실")
st.caption("시스템 비용을 먼저 최소화하고, 같은 비용의 배치 중 위치 이동이 가장 적은 해를 찾습니다.")


@st.cache_data
def _read_demands(problem: str, period_count: int) -> pd.DataFrame:
    demands = pd.read_csv(config.DATA_DIR / problem / "demands.csv")
    existing = [column for column in demands.columns if column.startswith("period")]
    for period in range(1, period_count + 1):
        column = f"period{period}"
        if column not in demands:
            demands[column] = 0.0
    keep = ["part", *[f"period{period}" for period in range(1, period_count + 1)], "operation_sequence"]
    return demands.drop(columns=[column for column in existing if column not in keep]).loc[:, keep]


@st.cache_data
def _read_parameters(problem: str) -> dict[str, float]:
    frame = pd.read_csv(config.DATA_DIR / problem / "parameters.csv")
    return {str(row.parameter): float(row.value) for row in frame.itertuples(index=False)}


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip())
    return cleaned.strip("_") or "scenario"


def _timestamped_dir(category: str, name: str) -> Path:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    return config.BASE_DIR / "results" / category / f"{_safe_name(name)}_{run_id}"


with st.sidebar:
    st.header("공통 실험 설정")
    part_mode = st.segmented_control(
        "수요 구조", ["싱글 파트", "멀티 파트"], default="싱글 파트", required=True, width="stretch"
    )
    problem = "multi_part" if part_mode == "멀티 파트" else "single_part"
    period_count = st.number_input("생산 기간 수", min_value=1, max_value=12, value=4, step=1)
    time_limit = st.number_input("한 번의 최적화 제한시간(초)", min_value=10, value=180, step=10)
    scenario_name = st.text_input("실험 이름", value=f"{problem}_experiment")
    st.caption("원본 Data 파일은 변경하지 않습니다.")


input_tab, result_tab, sensitivity_tab = st.tabs(["1. 실험 조건", "2. 최적화 결과", "3. 민감도 분석"])

with input_tab:
    st.subheader("배치 공간")
    st.caption("좌하단을 (0, 0)으로 고정하고, 행 m·열 n·좌표 사이 거리만 설정합니다.")
    grid_inputs = st.columns(3, border=True, vertical_alignment="bottom")
    with grid_inputs[0]:
        grid_rows = st.number_input("행 m", min_value=1, max_value=8, value=4, step=1)
    with grid_inputs[1]:
        grid_columns = st.number_input("열 n", min_value=1, max_value=8, value=4, step=1)
    with grid_inputs[2]:
        coordinate_distance = st.number_input("좌표 사이 거리", min_value=0.1, value=1.0, step=0.1)

    default_locations = build_grid_locations(
        int(grid_rows), int(grid_columns), spacing_x=float(coordinate_distance), spacing_y=float(coordinate_distance)
    )
    locations = st.data_editor(
        default_locations,
        key=f"locations_{int(grid_rows)}_{int(grid_columns)}_{coordinate_distance}",
        disabled=["location", "type"],
        hide_index=True,
        width="stretch",
        column_config={
            "location": st.column_config.NumberColumn("위치 번호"),
            "x": st.column_config.NumberColumn("X 좌표", format="%.2f"),
            "y": st.column_config.NumberColumn("Y 좌표", format="%.2f"),
            "type": st.column_config.TextColumn("위치 종류"),
        },
    )

    st.subheader("수요")
    st.caption("각 기간의 수요와 공정 순서를 수정할 수 있습니다.")
    demands = st.data_editor(
        _read_demands(problem, int(period_count)),
        key=f"demands_{problem}_{int(period_count)}",
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        column_config={
            "part": st.column_config.TextColumn("파트"),
            "operation_sequence": st.column_config.TextColumn("공정 순서"),
        },
    )

    st.subheader("위치 이동 조건")
    st.caption("처음에는 이동비용을 0으로 두면, 시스템 비용을 유지하면서 불필요한 이동만 제거합니다.")
    cost_inputs = st.columns(2, border=True, vertical_alignment="bottom")
    with cost_inputs[0]:
        relocation_distance_cost = st.number_input("거리 1당 위치 이동비용", min_value=0.0, value=0.0, step=0.5)
    with cost_inputs[1]:
        relocation_fixed_cost = st.number_input("1회당 고정 위치 이동비용", min_value=0.0, value=0.0, step=0.5)

    advanced = st.toggle("추가 이동 제약 보기", value=False)
    if advanced:
        constraint_inputs = st.columns(2, border=True, vertical_alignment="bottom")
        with constraint_inputs[0]:
            crew_capacity = st.number_input("기간당 최대 이동 횟수", min_value=0, value=2, step=1)
        with constraint_inputs[1]:
            forbid_swaps = st.toggle("두 기계의 직접 맞교환 금지", value=False)
    else:
        crew_capacity = None
        forbid_swaps = False

    if int(grid_rows) * int(grid_columns) > 36:
        st.warning("설치 위치가 36개를 넘으면 풀이시간이 급격히 늘어날 수 있습니다.")
    run_clicked = st.button("1·2단계 최적화 실행", type="primary", icon=":material/play_arrow:", width="stretch")
    if run_clicked:
        try:
            run_dir = _timestamped_dir("interactive", scenario_name)
            paths = prepare_scenario_directory(
                config.DATA_DIR / problem, run_dir / "input", pd.DataFrame(locations), pd.DataFrame(demands)
            )
            settings = config.build_config(
                problem_name=problem,
                profile="network_mir",
                result_dir=run_dir,
                PROBLEM_NAME=_safe_name(scenario_name),
                PROBLEM_DIR=run_dir / "input",
                ENABLE_RELOCATION=True,
                MINIMIZE_RELOCATIONS_SECONDARY=True,
                RELOCATION_DISTANCE_COST=float(relocation_distance_cost),
                RELOCATION_FIXED_COST=float(relocation_fixed_cost),
                RELOCATION_DOWNTIME_FRACTION=0.0,
                RELOCATION_CREW_CAPACITY=(int(crew_capacity) if crew_capacity is not None else None),
                FORBID_REVERSE_SWAPS=bool(forbid_swaps),
                RELOCATION_CONGESTION_COST_STEP=0.0,
                TIME_LIMIT=float(time_limit),
                MIP_GAP=0.0,
                STAGE_ONE_CONFIGURATION_LIMIT=6,
                OUTPUT_FLAG=0,
                **paths,
            )
            with st.status("최적화를 진행하고 있습니다...", expanded=True) as status:
                instance = load_instance(settings)
                solution = solve_milp(instance, settings)
                status.write("Stage 1·2 결과를 저장하고 있습니다.")
                save_solution(solution, run_dir)
                if solution.machine_states:
                    status.write("기간별 배치 그림을 만들고 있습니다.")
                    draw_layouts(run_dir, instance)
                status.update(label="최적화가 완료되었습니다.", state="complete", expanded=False)
            st.session_state["last_result_dir"] = str(run_dir)
            st.success("2. 최적화 결과 탭에서 두 단계를 비교하세요.")
        except Exception as exc:
            st.exception(exc)


with result_tab:
    result_value = st.session_state.get("last_result_dir")
    if not result_value:
        st.info("1. 실험 조건 탭에서 먼저 최적화를 실행하세요.")
    else:
        result_dir = Path(result_value)
        summary = json.loads((result_dir / "solution_summary.json").read_text(encoding="utf-8"))
        periods = [int(period) for period in summary.get("periods", [])]
        selected_period = st.select_slider("비교할 생산 기간", options=periods, value=periods[0])
        stage_one_dir = result_dir / "stage_1_system_cost"
        stage_two_dir = result_dir / "stage_2_min_relocation"
        stage_one_summary = json.loads((stage_one_dir / "solution_summary.json").read_text(encoding="utf-8"))
        stage_two_summary = json.loads((stage_two_dir / "solution_summary.json").read_text(encoding="utf-8")) if stage_two_dir.exists() else None
        left, right = st.columns(2)
        with left.container(border=True):
            st.subheader("Stage 1 · 같은 최소비용 배치들")
            candidates_dir = stage_one_dir / "candidates"
            index_path = candidates_dir / "index.json"
            candidates = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else [
                {"candidate_id": 1, "system_cost": stage_one_summary.get("objective"), "relocation_count": stage_one_summary.get("relocation_count")}
            ]
            selected_candidate = st.selectbox("배치 후보", [int(row["candidate_id"]) for row in candidates], format_func=lambda value: f"후보 {value}")
            candidate = next(row for row in candidates if int(row["candidate_id"]) == selected_candidate)
            with st.container(horizontal=True):
                st.metric("시스템 비용", f"{float(candidate.get('system_cost', 0)):,.2f}", border=True)
                st.metric("위치 이동", f"{float(candidate.get('relocation_count', 0)):g}회", border=True)
            candidate_dir = candidates_dir / f"configuration_{selected_candidate:02d}"
            display_dir = candidate_dir if candidate_dir.exists() else stage_one_dir
            st.image(str(display_dir / "figures" / f"layout_period_{selected_period}.png"), width="stretch")
        with right.container(border=True):
            st.subheader("Stage 2 · 위치 이동이 가장 적은 배치")
            if stage_two_summary is None:
                st.warning("Stage 1의 최적성이 증명되지 않아 Stage 2를 시작하지 않았습니다.")
            else:
                with st.container(horizontal=True):
                    st.metric("유지한 시스템 비용", f"{float(stage_two_summary.get('system_cost', 0)):,.2f}", border=True)
                    st.metric("최소 위치 이동", f"{float(stage_two_summary.get('relocation_count', 0)):g}회", border=True)
                st.image(str(stage_two_dir / "figures" / f"layout_period_{selected_period}.png"), width="stretch")
        st.caption(f"결과 폴더: {result_dir}")


with sensitivity_tab:
    st.subheader("민감도 분석")
    st.caption("비용의 안정 구간과 격자 구조를 여러 번 독립적으로 풀어 비교합니다.")
    analysis_label = st.segmented_control(
        "비교할 항목",
        ["위치 이동비용", "Configuration 변경비용", "격자 구조"],
        default="위치 이동비용",
        required=True,
        width="stretch",
    )
    analysis_type = {"위치 이동비용": "relocation_cost", "Configuration 변경비용": "reconfiguration_cost", "격자 구조": "grid"}[analysis_label]
    parameters = _read_parameters(problem)

    if analysis_type == "relocation_cost":
        st.info("거리 1당 이동비용을 바꾸며 이동 횟수가 안정되는 구간을 찾습니다.")
        levels_text = st.text_input("비용 후보", value="0, 0.5, 1, 2, 5, 10")
        grid_candidates = None
    elif analysis_type == "reconfiguration_cost":
        st.info("Configuration 변경에 필요한 모듈 추가비용을 바꾸며 재구성 횟수가 안정되는 구간을 찾습니다. 제거비용은 기준 비율로 같이 조정됩니다.")
        levels_text = st.text_input("모듈 추가비용 후보", value="0, 25, 50, 75, 100, 150")
        grid_candidates = None
    else:
        st.info("여러 m × n과 좌표 사이 거리를 비교합니다. 원하는 후보 행을 추가하거나 삭제하세요.")
        grid_candidates = st.data_editor(
            pd.DataFrame([
                {"m": 3, "n": 4, "coordinate_distance": 1.0},
                {"m": 4, "n": 4, "coordinate_distance": 1.0},
                {"m": 4, "n": 5, "coordinate_distance": 1.0},
                {"m": 4, "n": 4, "coordinate_distance": 2.0},
            ]),
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            column_config={
                "m": st.column_config.NumberColumn("행 m", min_value=1, step=1),
                "n": st.column_config.NumberColumn("열 n", min_value=1, step=1),
                "coordinate_distance": st.column_config.NumberColumn("좌표 사이 거리", min_value=0.1, format="%.2f"),
            },
        )
        levels_text = ""

    sensitivity_time = st.number_input("실험 1개당 제한시간(초)", min_value=10, value=60, step=10)
    estimated_cases = len(grid_candidates) if grid_candidates is not None else len([x for x in levels_text.split(",") if x.strip()])
    st.caption(f"최대 예상 실행시간: {estimated_cases * int(sensitivity_time):,}초 · 최적성이 빨리 증명되면 더 일찍 종료됩니다.")
    sensitivity_clicked = st.button("민감도 분석 실행", type="primary", icon=":material/experiment:", width="stretch")
    if sensitivity_clicked:
        try:
            if analysis_type == "grid":
                cases = build_grid_cases(pd.DataFrame(grid_candidates), relocation_distance_cost=float(relocation_distance_cost))
            else:
                cases = build_cost_cases(
                    analysis_type,
                    parse_numeric_levels(levels_text),
                    rows=int(grid_rows),
                    columns=int(grid_columns),
                    spacing=float(coordinate_distance),
                    relocation_distance_cost=float(relocation_distance_cost),
                    base_add_module_cost=float(parameters["add_module_cost"]),
                    base_remove_module_cost=float(parameters["remove_module_cost"]),
                )
            sensitivity_dir = _timestamped_dir("sensitivity", f"{scenario_name}_{analysis_type}")
            with st.status("민감도 분석을 시작합니다...", expanded=True) as status:
                def update_progress(index: int, total: int, case: dict) -> None:
                    status.write(f"{index}/{total} · {case['case']}")

                sensitivity_frame = run_sensitivity(
                    problem=problem,
                    demands=pd.DataFrame(demands),
                    cases=cases,
                    result_dir=sensitivity_dir,
                    time_limit_per_case=float(sensitivity_time),
                    relocation_fixed_cost=float(relocation_fixed_cost),
                    progress=update_progress,
                )
                status.update(label="민감도 분석이 완료되었습니다.", state="complete", expanded=False)
            st.session_state["sensitivity_frame"] = sensitivity_frame
            st.session_state["sensitivity_type"] = analysis_type
            st.session_state["sensitivity_dir"] = str(sensitivity_dir)
        except Exception as exc:
            st.exception(exc)

    sensitivity_frame = st.session_state.get("sensitivity_frame")
    stored_type = st.session_state.get("sensitivity_type")
    if isinstance(sensitivity_frame, pd.DataFrame) and stored_type == analysis_type:
        recommendation = recommend_case(sensitivity_frame, analysis_type)
        with st.container(border=True):
            st.subheader("분석 결론")
            if recommendation.get("case"):
                st.metric("추천 후보", recommendation.get("value", recommendation["case"]))
            else:
                st.warning("현재 실험 범위만으로는 하나의 추천값을 정할 수 없습니다.")
            st.write(recommendation["reason"])

        valid = sensitivity_frame[sensitivity_frame["status"] == "OPTIMAL"].copy()
        if not valid.empty:
            if analysis_type == "grid":
                chart = alt.Chart(valid).mark_bar().encode(
                    x=alt.X("case:N", title="격자 후보", sort="-y"),
                    y=alt.Y("system_cost:Q", title="시스템 비용", scale=alt.Scale(zero=False)),
                    tooltip=["case", "m", "n", "coordinate_distance", "system_cost", "relocation_count"],
                )
            else:
                count_column = "relocation_count" if analysis_type == "relocation_cost" else "reconfiguration_count"
                y_title = "위치 이동 횟수" if analysis_type == "relocation_cost" else "Configuration 변경 횟수"
                chart = alt.Chart(valid).mark_line(point=True).encode(
                    x=alt.X("analysis_value:Q", title="비용 후보"),
                    y=alt.Y(f"{count_column}:Q", title=y_title),
                    tooltip=["case", "analysis_value", count_column, "system_cost"],
                )
            st.altair_chart(chart, width="stretch")

        display_columns = [
            "case", "status", "m", "n", "coordinate_distance", "analysis_value", "system_cost",
            "reconfiguration_count", "relocation_count", "total_relocation_distance", "runtime_seconds", "error",
        ]
        st.dataframe(sensitivity_frame[[column for column in display_columns if column in sensitivity_frame]], hide_index=True, width="stretch")
        if not valid.empty:
            st.subheader("후보별 배치 확인")
            selected_case = st.selectbox("확인할 후보", valid["case"].tolist())
            selected_case_dir = Path(st.session_state["sensitivity_dir"]) / selected_case
            selected_summary = json.loads(
                (selected_case_dir / "solution_summary.json").read_text(encoding="utf-8")
            )
            selected_case_period = st.select_slider(
                "확인할 생산 기간",
                options=[int(period) for period in selected_summary.get("periods", [])],
                key="sensitivity_period",
            )
            selected_stage_dir = (
                selected_case_dir / "stage_2_min_relocation"
                if (selected_case_dir / "stage_2_min_relocation").exists()
                else selected_case_dir
            )
            selected_image = selected_stage_dir / "figures" / f"layout_period_{selected_case_period}.png"
            if selected_image.exists():
                st.image(str(selected_image), width="stretch")
        st.caption(f"민감도 결과 폴더: {st.session_state.get('sensitivity_dir')}")
