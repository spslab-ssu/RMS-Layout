# -*- coding: utf-8 -*-
"""임의 라우트 시나리오 큐 생성기 (gen_scen보다 자유도가 높다).

제품마다 라우트를 직접 주고, 기간별 비중(믹스)과 총 작업량만 지정하면
수요를 역산해 준다. 밀도(기계 수)는 total_load로 조절한다.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def rates(base):
    by = defaultdict(dict)
    with open(REPO / "Data" / base / "production_rates.csv", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            by[int(r["operation"])][r["configuration"]] = float(r["production_rate"])
    return by


def machines_needed(base, routes, dem, t):
    """기간 t에 필요한 최소 기계 수(op별 최고효율 config 기준). 유효 하한."""
    R = rates(base)
    need = defaultdict(float)
    for seq, per in zip(routes, dem):
        for op in seq:
            need[op] += per[t]
    return sum(math.ceil(v / max(R[op].values())) for op, v in need.items())


def weights(mix, K, T=4, floor=0.15):
    W = []
    for t in range(T):
        if mix == "fixed":
            w = [1.0 / K] * K
        elif mix == "alt":
            w = [1.0 if k == (t % K) else 0.0 for k in range(K)]
        else:                                   # grad
            pos = t / (T - 1) * (K - 1)
            w = [max(0.0, 1.0 - abs(pos - k)) + floor for k in range(K)]
        s = sum(w)
        W.append([x / s for x in w])
    return W


def build(sid, base, routes, mix, total_load, grid, why, alpha=None, beta=None,
          names=None, T=4, balance=True):
    """routes: [[op,...], ...] 제품별 공정열.  total_load: 기간별 총 공정 방문 수 목표."""
    K = len(routes)
    W = weights(mix, K, T)
    dem = [[0] * T for _ in range(K)]
    for t in range(T):
        for k in range(K):
            denom = len(routes[k]) if balance else max(len(r) for r in routes)
            dem[k][t] = max(0, round(total_load * W[t][k] / denom))
    spec = {"id": sid, "base": base, "hypothesis": why, "grid": grid,
            "demands": [{"part": (names[k] if names else "R%d" % k),
                         "periods": dem[k],
                         "seq": ">".join(str(o) for o in routes[k])} for k in range(K)]}
    if alpha is not None:
        spec["alpha"] = alpha
        spec["beta"] = beta if beta is not None else round(alpha / 5, 4)
    spec["_loads"] = [sum(len(routes[k]) * dem[k][t] for k in range(K)) for t in range(T)]
    spec["_machines"] = [machines_needed(base, routes, dem, t) for t in range(T)]
    return spec


def write(path, specs, slots=None):
    clean = []
    for s in specs:
        ld, mc = s.pop("_loads", None), s.pop("_machines", None)
        occ = "" if (slots is None or mc is None) else "  점유 %s%%" % [round(100 * m / slots) for m in mc]
        print("  %-20s 부하%s 기계%s%s" % (s["id"], ld, mc, occ))
        clean.append(s)
    Path(path).write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding="utf-8")
    print("->", path, "(%d개)" % len(clean))
