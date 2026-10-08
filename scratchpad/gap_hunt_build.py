# -*- coding: utf-8 -*-
"""2026-10-07 '이득 큰 + 10분 안에 풀리는' 시나리오 큐 (multi_part 데이터 기반, off vs z joint).

세 가지 축으로 off–joint 차이를 키운다 (모두 작은 레이아웃 9~16슬롯).
  R: 같은 공정을 기간마다 반대 방향으로 흐르게 (흐름 역전·순환) — 캠페인에서 이득이 가장 컸던 조건
  L: 공정을 공유하지 않는 두 제품을 기간마다 교대 생산 (공정 비공유 + 제품 교대)
  _norc: 재구성 금지 — 정적 배치가 재구성으로 우회하는 길을 막는다 (재구성이 어렵거나 비싼 RMS)
기준값: M_seqrev_15slot (A 2>12>17 / Cr 8>11>12>2 교대, 15슬롯) = 이득 740 (4.57%), 양쪽 최적 증명.
출력: Result/adaptive_campaign/queue_gaphunt.json, plan_1007.json
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "Result" / "adaptive_campaign"

G15 = {"keep_rows": [0, 1, 2]}                                   # 5열 x 3행 (M_seqrev_15slot과 같은 격자)
G12 = {"cols": 4, "rows": 3, "start": [-2, 1.0], "end": [5, 1.0]}
G9 = {"cols": 3, "rows": 3, "start": [-2, 1.0], "end": [4, 1.0]}
G16 = {"cols": 4, "rows": 4, "start": [-2, 1.5], "end": [5, 1.5]}


def odd(d): return [d, 0, d, 0]
def even(d): return [0, d, 0, d]


def cell(sid, grid, demands, hyp, norc=False):
    s = {"id": sid, "base": "multi_part", "engine": "z", "grid": grid,
         "params": {"add_module_cost": 50, "remove_module_cost": 25},
         "demands": [{"part": p, "periods": per, "seq": seq} for p, per, seq in demands],
         "hypothesis": hyp}
    if norc:
        s["allow_reconfiguration"] = False
    return s


R3 = [("A", odd(40), "2>12>17"), ("Cr", even(40), "8>11>12>2")]           # = M_seqrev_15slot
R4 = [("P", odd(40), "2>12>11>8"), ("Pr", even(40), "8>11>12>2")]         # 같은 4공정 완전 역전
R4_60 = [("P", odd(60), "2>12>11>8"), ("Pr", even(60), "8>11>12>2")]
R4_B = R4 + [("B", [20, 20, 20, 20], "2>12>11")]                          # 매 기간 정방향 제품 추가
ROT = [("P1", [40, 0, 0, 40], "2>12>11"), ("P2", [0, 40, 0, 0], "12>11>2"), ("P3", [0, 0, 40, 0], "11>2>12")]
LALT = [("P", odd(40), "18>9>19"), ("Q", even(40), "13>16>8>12")]          # 공정 비공유 두 제품 교대
LOW = [("A", [10, 15, 8, 0], "18>9>19"), ("B", [25, 30, 22, 15], "10>1>17"), ("C", [0, 10, 20, 30], "13>16>8>12")]
HIGH = [("A", [10, 15, 8, 0], "2>12>17"), ("B", [25, 30, 22, 15], "2>12>11"), ("C", [0, 10, 20, 30], "2>12>11>8")]

CELLS = [
    cell("G_R4_15", G15, R4, "4공정 완전 역전 교대, 15슬롯"),
    cell("G_R4_15_norc", G15, R4, "4공정 완전 역전 교대, 15슬롯, 재구성 금지", norc=True),
    cell("G_R3_15_norc", G15, R3, "M_seqrev_15slot + 재구성 금지", norc=True),
    cell("G_Lalt_15", G15, LALT, "공정 비공유 두 제품 교대, 15슬롯"),
    cell("G_Lalt_15_norc", G15, LALT, "공정 비공유 두 제품 교대, 15슬롯, 재구성 금지", norc=True),
    cell("G_R4_12", G12, R4, "4공정 완전 역전 교대, 12슬롯(빡빡)"),
    cell("G_R4_9", G9, R4, "4공정 완전 역전 교대, 9슬롯(매우 빡빡)"),
    cell("G_R3_12", G12, R3, "M_seqrev 12슬롯"),
    cell("G_Lalt_12", G12, LALT, "공정 비공유 교대, 12슬롯"),
    cell("G_Lorig_12_norc", G12, LOW, "low overlap 원래 수요패턴 0.5x, 12슬롯, 재구성 금지 (F_3x4_p3_low_u050 짝)", norc=True),
    cell("G_Horig_12_norc", G12, HIGH, "high overlap 원래 수요패턴 0.5x, 12슬롯, 재구성 금지 (F_3x4_p3_high_u050 짝)", norc=True),
    cell("G_Rrot_15", G15, ROT, "3공정 순환(2>12>11 / 12>11>2 / 11>2>12), 15슬롯"),
    cell("G_Rrot_15_norc", G15, ROT, "3공정 순환, 15슬롯, 재구성 금지", norc=True),
    cell("G_R4_15_d60", G15, R4_60, "4공정 완전 역전 교대, 수요 60, 15슬롯"),
    cell("G_R4_15_withB", G15, R4_B, "4공정 역전 교대 + 매 기간 정방향 제품 B, 15슬롯"),
    cell("G_Lorig_16_norc", G16, LOW, "low overlap 원래 수요패턴 0.5x, 16슬롯, 재구성 금지", norc=True),
    cell("G_Horig_16_norc", G16, HIGH, "high overlap 원래 수요패턴 0.5x, 16슬롯, 재구성 금지", norc=True),
]


def main():
    q = OUT / "queue_gaphunt.json"
    q.write_text(json.dumps(CELLS, ensure_ascii=False, indent=1), encoding="utf-8")
    jobs = [{"kind": "campaign", "queue": "Result/adaptive_campaign/queue_gaphunt.json", "id": c["id"], "time": 600} for c in CELLS]
    jobs += [{"kind": "sweep", "id": "G_R4_15", "time": 240, "units": "20,50,100,200"},
             {"kind": "sweep", "id": "G_Lalt_15", "time": 240, "units": "20,50,100,200"}]
    deadline = (datetime.now() + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
    (OUT / "plan_1007.json").write_text(json.dumps({"deadline": deadline, "jobs": jobs}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("cells %d, jobs %d, deadline %s" % (len(CELLS), len(jobs), deadline))


if __name__ == "__main__":
    main()
