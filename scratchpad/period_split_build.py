# -*- coding: utf-8 -*-
"""기간 수 실험 (방식 ②: 같은 계획 기간을 더 잘게 나눔) — 2026-10-08.

현실 가정 탐색(RL_12_*)과 같은 설정에서 기간 수 T 만 2, 6, 8 로 바꾼다 (T=4 는 RL_12_* 결과 재사용).
  - 수요 = 생산 속도. Saffar 4기간 값을 각 기간 중앙(0.5, 1.5, 2.5, 3.5)의 값으로 두고 직선 보간,
    T 개 구간의 중앙에서 읽어 반올림 (양 끝은 가장 가까운 값으로 고정). T=4 는 원래 값과 같다.
  - 자재취급비 단가 = 4 x (4/T)  -> 계획 기간 전체의 운반비 총량이 T 와 무관하게 같아지도록.
  - 생산능력(B_jl), 재구성비 50/25, 이동비 1칸당 10, 12슬롯, 3부품: RL_12_* 와 같음.
출력: Result/adaptive_campaign/queue_periods.json, plan_periods.json
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "Result" / "adaptive_campaign"
GRID12 = {"cols": 4, "rows": 3, "start": [-2, 1.0], "end": [5, 1.0]}
ROUTES = {
    "high": {"A": "2>12>17", "B": "2>12>11", "C": "2>12>11>8"},
    "med": {"A": "2>9>19", "B": "2>1>17", "C": "2>16>8>12"},
    "low": {"A": "18>9>19", "B": "10>1>17", "C": "13>16>8>12"},
}
LIFE = {  # 4기간 기준 (x0.5 적용 전)
    "saffar": {"A": [20, 30, 15, 0], "B": [50, 60, 45, 30], "C": [0, 20, 40, 60]},
    "gen": {"A": [60, 40, 20, 0], "B": [30, 30, 30, 30], "C": [0, 20, 40, 60]},
}
SCALE = 0.5


def resample(v4, T):
    centers4 = [0.5, 1.5, 2.5, 3.5]
    out = []
    for k in range(T):
        x = (k + 0.5) * 4.0 / T
        if x <= centers4[0]:
            y = v4[0]
        elif x >= centers4[-1]:
            y = v4[-1]
        else:
            i = int(x - 0.5)
            w = (x - centers4[i])
            y = v4[i] * (1 - w) + v4[i + 1] * w
        out.append(int(round(y * SCALE)))
    return out


def main():
    cells = []
    for T in (2, 6, 8):
        for life in ("saffar", "gen"):
            for rt in ("low", "med", "high"):
                cells.append({
                    "id": "RT%d_12_%s_%s" % (T, rt, life), "base": "multi_part", "engine": "z", "grid": GRID12,
                    "params": {"add_module_cost": 50, "remove_module_cost": 25, "period_count": T,
                               "material_handling_cost": round(4.0 * 4 / T, 4)},
                    "move_cost_flat": 10,
                    "demands": [{"part": p, "periods": resample(LIFE[life][p], T), "seq": ROUTES[rt][p]} for p in ("A", "B", "C")],
                    "factors": {"T": T, "slots": 12, "route": rt, "life": life, "scale": SCALE, "move_cost": 10},
                    "hypothesis": "기간 %d개(같은 계획 기간 분할), 12슬롯, 공정 %s, 수명주기 %s, 이동비 10" % (T, rt, life),
                })
    (OUT / "queue_periods.json").write_text(json.dumps(cells, ensure_ascii=False, indent=1), encoding="utf-8")
    order = sorted(cells, key=lambda c: (c["factors"]["T"] != 2, c["factors"]["T"], c["factors"]["life"] != "saffar"))
    jobs = [{"kind": "campaign", "queue": "Result/adaptive_campaign/queue_periods.json", "id": c["id"], "time": 600} for c in order]
    deadline = (datetime.now() + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
    (OUT / "plan_periods.json").write_text(json.dumps({"deadline": deadline, "jobs": jobs}, ensure_ascii=False, indent=1), encoding="utf-8")
    for c in order:
        print(c["id"], "c_mh", c["params"]["material_handling_cost"], [(d["part"], d["periods"]) for d in c["demands"]])
    print("cells", len(cells), "deadline", deadline)


if __name__ == "__main__":
    main()
