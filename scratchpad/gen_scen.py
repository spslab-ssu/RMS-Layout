# -*- coding: utf-8 -*-
"""재반복(re-entrant) 시나리오 생성기 — 큐 JSON을 만든다.

구조:  head > {loop}*n > tail
  Youssef: 5 > {1>16}*n > 15      (op5·op16은 MC15 전용 = 병목)
  Saffar : 2 > {12>11}*n > 8      (전용 기계 없음)

믹스 축: alt(교대) / grad(점진) / fixed(고정)
부하 축: bal(기간별 총 공정방문 수 일정) / unbal(수요 숫자를 같게 둬 부하가 출렁)

사용: 이 모듈을 import 해서 build(...)로 spec dict를 만든다.
"""
from __future__ import annotations

import json
from pathlib import Path

PRESET = {
    "youssef_2007": {"head": 5, "loop": [1, 16], "tail": 15},
    "multi_part":   {"head": 2, "loop": [12, 11], "tail": 8},
}


def seq(base, n):
    p = PRESET[base]
    return ">".join(str(x) for x in [p["head"]] + p["loop"] * n + [p["tail"]])


def nops(base, n):
    return 2 + len(PRESET[base]["loop"]) * n


def mix_weights(mode, T=4):
    """기간별 제품 비중(합 1). 제품 수 K에 맞춰 선형 전환."""
    if mode == "fixed":
        return None
    return mode


def build(sid, base, layers, mix, load, total_load, grid, hypothesis,
          alpha=None, beta=None, T=4):
    """layers: [n1, n2, ...] 제품별 루프 반복 수 (제품 K개)
    mix: 'alt' | 'grad' | 'fixed'
    load: 'bal'(총 방문 수를 total_load로 고정) | 'unbal'(수요 숫자를 제품 간 동일)
    """
    K = len(layers)
    ops = [nops(base, n) for n in layers]
    # 기간별 제품 비중 w[t][k]
    W = []
    for t in range(T):
        if mix == "fixed":
            w = [1.0 / K] * K
        elif mix == "alt":
            w = [1.0 if k == (t % K) else 0.0 for k in range(K)]
        else:  # grad: 제품1 -> 제품K 로 선형 전환 (끝점에서도 0이 되지 않게 여유를 둔다)
            pos = t / (T - 1) * (K - 1)          # 0 .. K-1
            w = [max(0.0, 1.0 - abs(pos - k)) for k in range(K)]
            if True:                               # 바닥값을 깔아 모든 기간에 전 제품이 살아 있게 한다
                w = [x + 0.15 for x in w]
            s = sum(w)
            w = [x / s for x in w]
        W.append(w)
    demands = [[0] * T for _ in range(K)]
    for t in range(T):
        for k in range(K):
            if load == "bal":
                demands[k][t] = round(total_load * W[t][k] / ops[k])
            else:  # unbal: 비중을 그대로 '개수'로 (공정 수 차이가 부하 차이로 나타남)
                demands[k][t] = round(total_load / max(ops) * W[t][k] * K / 1.0)
    spec = {
        "id": sid, "base": base, "hypothesis": hypothesis,
        "demands": [{"part": "L%d" % layers[k], "periods": demands[k], "seq": seq(base, layers[k])}
                    for k in range(K)],
        "grid": grid,
    }
    if alpha is not None:
        spec["alpha"] = alpha
        spec["beta"] = beta if beta is not None else round(alpha / 5, 4)
    return spec


def loads(spec):
    """기간별 총 공정 방문 수."""
    T = len(spec["demands"][0]["periods"])
    out = []
    for t in range(T):
        out.append(sum(len(d["seq"].split(">")) * d["periods"][t] for d in spec["demands"]))
    return out


def write(path, specs):
    Path(path).write_text(json.dumps(specs, ensure_ascii=False, indent=1), encoding="utf-8")
    for s in specs:
        print("  %-18s %s  부하%s" % (s["id"], [d["periods"] for d in s["demands"]], loads(s)))
    print("->", path)
