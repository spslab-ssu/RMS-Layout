"""생성된 RMS 실험 인스턴스를 네 모델로 순차 실행한다.

V2GRO의 batch 실행 방식처럼 manifest를 한 행씩 읽고, 각 행에서
base -> base_adaptive -> network -> network_adaptive 순서로 실행한다.
완료된 모델은 summary.csv를 기준으로 건너뛰므로 중단 후 재실행할 수 있다.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
# 직접 실행(`python exp/run_experiments.py`)할 때도 저장소 루트의 config와
# Src 패키지를 찾을 수 있도록 import 경로를 명시한다.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config as default_config
from Src.data.loader import load_instance
from Src.io.output import save_solution
from Src.models import base
from Src.models import milp_network
from Src.models import network_adaptive
import base_adaptive
MODEL_NAMES = ("base", "base_adaptive", "network", "network_adaptive")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RMS experiments sequentially")
    parser.add_argument("--manifest", type=Path, default=ROOT / "Data/demands/exp/manifest.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "Result/exp")
    parser.add_argument("--part", action="append", type=int, choices=(1, 3, 5, 7), dest="parts")
    parser.add_argument("--layout", action="append", choices=("layout_18", "layout_22", "layout_32", "layout_37"))
    parser.add_argument("--model", action="append", choices=MODEL_NAMES)
    parser.add_argument("--limit", type=int, default=None, help="manifest 행 제한; 점검용")
    parser.add_argument("--time-limit", type=float, default=30.0)
    parser.add_argument("--mip-gap", type=float, default=0.05)
    parser.add_argument("--output-flag", type=int, default=0)
    args = parser.parse_args()

    manifest_path = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    rows = list(csv.DictReader(manifest_path.open(newline="", encoding="utf-8-sig")))
    rows = [row for row in rows if not args.parts or int(row["part_count"]) in args.parts]
    rows = [row for row in rows if not args.layout or row["layout_name"] in args.layout]
    if args.limit is not None:
        rows = rows[:args.limit]
    selected_models = tuple(args.model or MODEL_NAMES)
    print(f"instances={len(rows)} models={','.join(selected_models)}", flush=True)

    for row in rows:
        part_dir = args.output / f"p{row['part_count']}"
        summary_path = part_dir / "summary.csv"
        completed = _completed(summary_path)
        for model_name in selected_models:
            key = (row["experiment_id"], row["layout_name"], model_name)
            if key in completed:
                print(f"SKIP {key}", flush=True)
                continue
            result_dir = part_dir / row["experiment_id"] / row["layout_name"] / model_name
            result_dir.mkdir(parents=True, exist_ok=True)
            started = time.perf_counter()
            record = _run_one(row, model_name, result_dir, args)
            record["elapsed_wall_seconds"] = round(time.perf_counter() - started, 6)
            _append_summary(summary_path, record)
            print(f"DONE {key} status={record.get('status_name')} objective={record.get('objective')}", flush=True)


def _run_one(row: dict[str, str], model_name: str, result_dir: Path, args) -> dict:
    cfg = _config_for(row, args)
    instance = load_instance(cfg)
    solver = {
        "base": base.solve_milp,
        "base_adaptive": base_adaptive.solve_milp,
        "network": milp_network.solve_milp,
        "network_adaptive": network_adaptive.solve_milp,
    }[model_name]
    try:
        solution = solver(instance, cfg)
        save_solution(solution, result_dir)
        # 이미지 렌더링은 결과 CSV가 정상적으로 생성된 뒤에만 시도한다.
        from Src.viz.visualize import draw_layouts
        draw_layouts(result_dir, instance)
        summary = dict(solution.summary)
        summary.update(solution.cost_breakdown or {})
        summary["error"] = ""
    except Exception as exc:  # noqa: BLE001 - batch가 한 인스턴스에서 중단되지 않도록 기록
        summary = {"status_name": "ERROR", "status": "ERROR", "objective": "", "error": repr(exc)}
        (result_dir / "error.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        relative_result_dir = str(result_dir.relative_to(ROOT))
    except ValueError:
        relative_result_dir = str(result_dir)
    summary.update({
        "experiment_id": row["experiment_id"],
        "part_count": row["part_count"],
        "overlap": row["overlap"],
        "utilization": row["utilization"],
        "seed": row["seed"],
        "layout_name": row["layout_name"],
        "model": model_name,
        "result_dir": relative_result_dir,
    })
    return summary


def _config_for(row: dict[str, str], args) -> SimpleNamespace:
    values = {name: getattr(default_config, name) for name in dir(default_config) if name.isupper()}
    cfg = SimpleNamespace(**values)
    part_count = int(row["part_count"])
    cfg.PROBLEM_TYPE = "single_part" if part_count == 1 else "multi_part"
    cfg.PROBLEM_NAME = cfg.PROBLEM_TYPE
    cfg.PARAMETER_NAME = cfg.PROBLEM_TYPE
    cfg.LOCATION_NAME = row["layout_name"]
    cfg.RMT_TABLE_NAME = row["rmt_table"]
    cfg.DEMAND_NAME = row["experiment_id"]
    cfg.LOCATION_FILE = ROOT / "Data/locations" / f"{cfg.LOCATION_NAME}.csv"
    cfg.CONFIGURATION_FILE = ROOT / "Data/rmt_tables" / cfg.RMT_TABLE_NAME / "configurations.csv"
    cfg.PRODUCTION_RATE_FILE = ROOT / "Data/rmt_tables" / cfg.RMT_TABLE_NAME / "production_rates.csv"
    cfg.DEMAND_FILE = ROOT / row["demand_file"]
    cfg.PARAMETER_FILE = ROOT / "Data/parameters" / f"{cfg.PARAMETER_NAME}.csv"
    cfg.RESULT_DIR = ROOT / "Result/exp" / f"p{part_count}"
    cfg.TIME_LIMIT = float(args.time_limit)
    cfg.MIP_GAP = float(args.mip_gap)
    cfg.OUTPUT_FLAG = int(args.output_flag)
    cfg.COMPUTE_LP_RELAXATION_BOUND = False
    cfg.USE_WARM_START = False
    cfg.USE_OBJECTIVE_CUTOFF = False
    cfg.RELOCATION_COST_PER_DISTANCE = 1.0
    cfg.RELOCATION_FIXED_COST = 0.0
    cfg.MAX_RELOCATION_DISTANCE = None
    cfg.ADAPTIVE_MODE = "joint"
    cfg.MOVE_COST_FLAT = 1.0
    cfg.ALPHA = 0.0
    cfg.BETA = 0.0
    return cfg


def _completed(path: Path) -> set[tuple[str, str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    with path.open(newline="", encoding="utf-8-sig") as file:
        completed_statuses = {"OPTIMAL", "TIME_LIMIT", "INFEASIBLE"}
        return {_row_key(row) for row in csv.DictReader(file)
                if row.get("status_name") in completed_statuses}


def _append_summary(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if path.exists() and path.stat().st_size:
        with path.open(newline="", encoding="utf-8-sig") as file:
            existing = list(csv.DictReader(file))
    # 같은 실험 key가 재실행되면 이전 행을 교체한다. 중단 후 재개해도
    # summary.csv가 중복 행으로 오염되지 않도록 한다.
    rows_by_key = {_row_key(item): item for item in existing}
    normalized = {key: _csv_value(value) for key, value in row.items()}
    rows_by_key[_row_key(normalized)] = normalized
    existing = list(rows_by_key.values())
    fieldnames = sorted({key for item in existing for key in item})
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(existing)


def _row_key(row: dict) -> tuple[str, str, str]:
    return (str(row.get("experiment_id", "")), str(row.get("layout_name", "")), str(row.get("model", "")))


def _csv_value(value):
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return value


if __name__ == "__main__":
    main()
