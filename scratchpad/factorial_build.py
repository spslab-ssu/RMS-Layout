# -*- coding: utf-8 -*-
"""요인실험 큐 생성기 (multi_part 기반, off vs z joint, 1회씩).

요인: 부품 수 {1,3,5} x 레이아웃 {3x4,4x4,4x5,5x6,5x7} x 겹침 {low,high} x utilization {0.5,0.75,1.0,1.25}
- 레이아웃 RxC = 행 R x 열 C (원본 multi_part 20슬롯 = 4x5). 도크는 가운데 행 높이, 좌 -2 / 우 C+1.
- utilization 기준 (b): 부품 수와 무관하게 1.0x 의 총수요(전 부품·전 기간 합)를 원본 multi_part 총수요 370 에 맞춘다.
- 1부품 = B (2>12>11), 겹침 요인 없음.
- 재구성비 50/25 (Saffar 원값).
- 기계 대수 하한(공정별 ceil(수요/최고 생산율)의 기간별 합의 최대)이 슬롯 수를 넘으면 풀지 않고 INFEASIBLE 로 기록.

출력: Result/adaptive_campaign/queue_factorial.json (작은 레이아웃부터), factorial_skipped.csv
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "Result" / "adaptive_campaign"

BASE_TOTAL = 370  # 원본 multi_part 총수요 (A 65 + B 185 + C 120)

DEMAND = {  # 정규화 전 수요 패턴
    "A": [20, 30, 15, 0],
    "B": [50, 60, 45, 30],
    "C": [0, 20, 40, 60],
    "D": [0, 30, 40, 10],    # 신규: 중간 정점
    "E": [40, 30, 15, 5],    # 신규: 점감 (phase-out)
}
SEQ = {
    "high": {"A": "2>12>17", "B": "2>12>11", "C": "2>12>11>8",
             "D": "2>12>8", "E": "2>12>17>8"},
    "low":  {"A": "18>9>19", "B": "10>1>17", "C": "13>16>8>12",
             "D": "3>11>6", "E": "4>20>14>5"},
}
PARTS = {1: ["B"], 3: ["A", "B", "C"], 5: ["A", "B", "C", "D", "E"]}
LAYOUTS = [(3, 4), (4, 4), (4, 5), (5, 6), (5, 7)]
UTILS = [0.5, 0.75, 1.0, 1.25]


def best_rates():
    best = defaultdict(int)
    with open(REPO / "Data" / "multi_part" / "production_rates.csv", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            best[int(r["operation"])] = max(best[int(r["operation"])], int(r["production_rate"]))
    return best


def machine_lb(demands, best):
    peak = 0
    for t in range(4):
        load = defaultdict(int)
        for d in demands:
            for o in d["seq"].split(">"):
                load[int(o)] += d["periods"][t]
        peak = max(peak, sum(math.ceil(v / best[o]) for o, v in load.items()))
    return peak


def main():
    best = best_rates()
    queue, skipped = [], []
    for rows, cols in LAYOUTS:
        slots = rows * cols
        for n in (1, 3, 5):
            for ov in (["-"] if n == 1 else ["low", "high"]):
                parts = PARTS[n]
                raw_total = sum(sum(DEMAND[p]) for p in parts)
                for u in UTILS:
                    k = u * BASE_TOTAL / raw_total
                    seqs = SEQ["high" if ov == "-" else ov]
                    demands = [{"part": p, "periods": [int(round(x * k)) for x in DEMAND[p]], "seq": seqs[p]}
                               for p in parts]
                    sid = "F_%dx%d_p%d_%s_u%03d" % (rows, cols, n, ov if ov != "-" else "na", int(u * 100))
                    lb = machine_lb(demands, best)
                    spec = {
                        "id": sid, "base": "multi_part", "engine": "z",
                        "params": {"add_module_cost": 50, "remove_module_cost": 25},
                        "grid": {"cols": cols, "rows": rows,
                                 "start": [-2, (rows - 1) / 2], "end": [cols + 1, (rows - 1) / 2]},
                        "demands": demands,
                        "factors": {"layout": "%dx%d" % (rows, cols), "slots": slots, "parts": n,
                                    "overlap": ov, "util": u, "machine_lb": lb},
                        "hypothesis": "factorial %dx%d parts=%d overlap=%s util=%.2f" % (rows, cols, n, ov, u),
                    }
                    if lb > slots:
                        skipped.append({"id": sid, "slots": slots, "machine_lb": lb})
                    else:
                        queue.append(spec)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "queue_factorial.json", "w", encoding="utf-8") as fh:
        json.dump(queue, fh, ensure_ascii=False, indent=1)
    with open(OUT / "factorial_skipped.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "slots", "machine_lb"])
        w.writeheader()
        w.writerows(skipped)
    by_layout = defaultdict(lambda: [0, 0])
    for s in queue:
        by_layout[s["factors"]["layout"]][0] += 1
    for s in skipped:
        by_layout[s["id"].split("_")[1]][1] += 1
    print("run %d / skipped %d" % (len(queue), len(skipped)))
    for lay, (r, s) in by_layout.items():
        print("  %s: run %d, skip %d" % (lay, r, s))
    for s in skipped:
        print("  skip", s)


if __name__ == "__main__":
    main()
