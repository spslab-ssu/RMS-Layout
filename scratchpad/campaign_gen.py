# -*- coding: utf-8 -*-
"""adaptive 이득 탐색 캠페인 — 시나리오 인스턴스 생성기.

시나리오 spec(dict) 하나를 받아 베이스 데이터셋을 변형한 CSV 묶음을
Result/adaptive_campaign/<id>/data/ 에 쓴다. 원본 Data/는 절대 건드리지 않는다.

spec 키 (전부 선택):
  id            : 폴더명
  base          : "youssef_2007" | "multi_part"
  demands       : [{"part":"A","periods":[..],"seq":"1>5>60>15"}, ...]  -> demands.csv 통째로 교체
  demand_scale  : 수요 배율 (demands 미지정 시 베이스 수요에 곱함)
  params        : {"material_handling_cost": 20, "period_count": 6, ...} -> parameters.csv 덮어쓰기
  grid          : {"cols":5,"rows":4,"start":[-2,1.5],"end":[6,1.5]}  또는 {"keep_rows":[0,1,2]} (베이스 격자에서 행만 남김)
  remove_rates  : [["MC15",16], ...]  production_rates.csv에서 (config,op) 제거
  keep_rates    : [["MC11",1], ...]   지정한 (config,op)만 남김 (remove_rates보다 우선)
  remove_configs: ["MC15"]            해당 config 행 전부 제거 (configurations + production_rates)
"""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO / "Result" / "adaptive_campaign"


def _read(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _write(path, rows, fieldnames=None):
    if not rows:
        raise ValueError("빈 표를 쓰려 함: %s" % path)
    fieldnames = fieldnames or list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def generate(spec: dict) -> Path:
    sid = spec["id"]
    base = spec.get("base", "youssef_2007")
    src = REPO / "Data" / base
    dst = OUT_ROOT / sid / "data"
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)

    # ---- parameters ----
    params = {r["parameter"]: r["value"] for r in _read(src / "parameters.csv")}
    for k, v in (spec.get("params") or {}).items():
        params[k] = str(v)
    T = int(float(params["period_count"]))

    # ---- demands ----
    if spec.get("demands"):
        drows = []
        for d in spec["demands"]:
            per = list(d["periods"])
            if len(per) != T:
                raise ValueError("%s: part %s 수요 길이 %d != period_count %d" % (sid, d["part"], len(per), T))
            row = {"part": d["part"]}
            for t in range(1, T + 1):
                row["period%d" % t] = per[t - 1]
            row["operation_sequence"] = d["seq"]
            drows.append(row)
    else:
        drows = _read(src / "demands.csv")
        base_T = len([k for k in drows[0] if k.startswith("period")])
        if base_T != T:
            raise ValueError("%s: period_count %d인데 베이스 수요는 %d기간. demands를 지정하라" % (sid, T, base_T))
        scale = float(spec.get("demand_scale", 1.0))
        if scale != 1.0:
            for r in drows:
                for t in range(1, T + 1):
                    r["period%d" % t] = round(float(r["period%d" % t]) * scale)
    dcols = ["part"] + ["period%d" % t for t in range(1, T + 1)] + ["operation_sequence"]
    _write(dst / "demands.csv", drows, dcols)

    # ---- locations ----
    g = spec.get("grid")
    if g and "cols" in g:
        rows = []
        n = 1
        for y in range(int(g["rows"])):
            for x in range(int(g["cols"])):
                rows.append({"location": n, "x": x, "y": y, "type": "install"}); n += 1
        sx, sy = g.get("start", [-2, (int(g["rows"]) - 1) / 2.0])
        ex, ey = g.get("end", [int(g["cols"]) + 1, (int(g["rows"]) - 1) / 2.0])
        rows.append({"location": n, "x": sx, "y": sy, "type": "start"}); params["start_location"] = str(n); n += 1
        rows.append({"location": n, "x": ex, "y": ey, "type": "end"}); params["end_location"] = str(n)
    elif g and "keep_rows" in g:
        keep = {float(v) for v in g["keep_rows"]}
        rows = []
        for r in _read(src / "locations.csv"):
            if r["type"] == "install" and float(r["y"]) not in keep:
                continue
            rows.append(r)
    else:
        rows = _read(src / "locations.csv")
    _write(dst / "locations.csv", rows, ["location", "x", "y", "type"])
    _write(dst / "parameters.csv", [{"parameter": k, "value": v} for k, v in params.items()], ["parameter", "value"])

    # ---- configurations / production_rates ----
    cfg = _read(src / "configurations.csv")
    rates = _read(src / "production_rates.csv")
    rm_cfg = set(spec.get("remove_configs") or [])
    if rm_cfg:
        cfg = [r for r in cfg if r["configuration"] not in rm_cfg]
        rates = [r for r in rates if r["configuration"] not in rm_cfg]
    if spec.get("keep_rates"):
        keep = {(str(c), int(o)) for c, o in spec["keep_rates"]}
        rates = [r for r in rates if (r["configuration"], int(r["operation"])) in keep]
    elif spec.get("remove_rates"):
        rm = {(str(c), int(o)) for c, o in spec["remove_rates"]}
        rates = [r for r in rates if (r["configuration"], int(r["operation"])) not in rm]
    # 완전 특화: (config, op) 쌍마다 별도 config + 별도 machine 타입 -> op 전환 불가, 재구성 불가.
    # 라우트에 쓰이는 op만 남긴다(안 쓰는 op 쌍은 폐기).
    if spec.get("specialize"):
        used_ops = set()
        for d in drows:
            used_ops.update(int(o) for o in str(d["operation_sequence"]).split(">"))
        cfg_by = {r["configuration"]: r for r in cfg}
        new_cfg, new_rates = [], []
        for r in rates:
            op = int(r["operation"])
            if op not in used_ops or float(r["production_rate"]) <= 0:
                continue
            c = r["configuration"]
            if c not in cfg_by:
                continue
            base_row = dict(cfg_by[c])
            name = "%s_%d" % (c, op)
            base_row["configuration"] = name
            base_row["machine"] = "%s_%d" % (base_row["machine"], op)   # 타입을 분리해 재구성 차단
            new_cfg.append(base_row)
            new_rates.append({"machine": base_row["machine"], "configuration": name,
                              "operation": op, "production_rate": r["production_rate"]})
        cfg, rates = new_cfg, new_rates
    _write(dst / "configurations.csv", cfg)
    _write(dst / "production_rates.csv", rates, ["machine", "configuration", "operation", "production_rate"])

    # module_costs: True면 베이스의 module_costs.csv.off를 활성화 (Youssef 논문 실제 단가).
    #   {"scale": k} 를 주면 그 단가에 k배. 활성화되면 parameters.csv의 add/remove는 무시된다(data.py).
    mc = spec.get("module_costs")
    if mc:
        src_mc = src / "module_costs.csv.off"
        if not src_mc.exists():
            src_mc = src / "module_costs.csv"
        if not src_mc.exists():
            raise FileNotFoundError("%s: module_costs 원본이 없음" % sid)
        rows = _read(src_mc)
        k = float(mc.get("scale", 1.0)) if isinstance(mc, dict) else 1.0
        for r in rows:
            r["add_cost"] = round(float(r["add_cost"]) * k, 2)
            r["remove_cost"] = round(float(r["remove_cost"]) * k, 2)
        _write(dst / "module_costs.csv", rows, ["module", "add_cost", "remove_cost"])

    (OUT_ROOT / sid / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    return dst


if __name__ == "__main__":
    import sys
    specs = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    for s in specs:
        p = generate(s)
        print("생성:", s["id"], "->", p)
