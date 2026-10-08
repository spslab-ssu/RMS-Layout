# -*- coding: utf-8 -*-
"""2026-10-08 현실적 가정의 '재배치 이득 조건' 탐색 큐 (multi_part 데이터, off vs z joint).

현실성 원칙
  - 수요: 점진적인 제품 수명주기만 (켰다 껐다 하는 교대 없음)
  - 공정 순서: 실제 제품군 구조 (같은 제품의 순서를 뒤집지 않음)
  - 재구성 허용, Saffar 단가 50/25
  - 이동비 > 0 이 기본: 1칸당 10 (본 실행), 30 (스윕). 0 은 상한 참고용 스윕
요인
  공정 구조  high: Saffar 원래 (모든 제품이 2>12 공유)
            med : 공통 첫 공정(2) + 제품별 전용 공정
            low : 제품군별 전용 공정 (공유 없음)
  수명주기   mild  : 모든 제품이 계속 생산, 완만한 증감
            saffar: Saffar 예제 2 패턴 (A 단종, B 유지·감소, C 도입)
            gen   : 세대 교체 (A 60→0 감소, C 0→60 증가, B 일정)
  레이아웃   15슬롯(5열x3행), 12슬롯(4열x3행), 수요는 0.5배
출력: Result/adaptive_campaign/queue_realistic.json, plan_1008.json
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "Result" / "adaptive_campaign"

GRIDS = {
    "15": {"cols": 5, "rows": 3, "start": [-2, 1.0], "end": [6, 1.0]},
    "12": {"cols": 4, "rows": 3, "start": [-2, 1.0], "end": [5, 1.0]},
}
ROUTES = {
    "high": {"A": "2>12>17", "B": "2>12>11", "C": "2>12>11>8"},
    "med": {"A": "2>9>19", "B": "2>1>17", "C": "2>16>8>12"},
    "low": {"A": "18>9>19", "B": "10>1>17", "C": "13>16>8>12"},
}
LIFE = {
    "mild": {"A": [25, 25, 20, 20], "B": [50, 55, 50, 45], "C": [15, 20, 25, 25]},
    "saffar": {"A": [20, 30, 15, 0], "B": [50, 60, 45, 30], "C": [0, 20, 40, 60]},
    "gen": {"A": [60, 40, 20, 0], "B": [30, 30, 30, 30], "C": [0, 20, 40, 60]},
}
SCALE = 0.5
MOVE_MAIN = 10


def main():
    cells = []
    for g in ("15", "12"):
        for life in ("saffar", "gen", "mild"):
            for rt in ("low", "med", "high"):
                cells.append({
                    "id": "RL_%s_%s_%s" % (g, rt, life), "base": "multi_part", "engine": "z",
                    "grid": GRIDS[g], "params": {"add_module_cost": 50, "remove_module_cost": 25},
                    "move_cost_flat": MOVE_MAIN,
                    "demands": [{"part": p, "periods": [int(round(x * SCALE)) for x in LIFE[life][p]], "seq": ROUTES[rt][p]}
                                for p in ("A", "B", "C")],
                    "factors": {"slots": int(g), "route": rt, "life": life, "scale": SCALE, "move_cost": MOVE_MAIN},
                    "hypothesis": "현실 가정: %s슬롯, 공정구조 %s, 수명주기 %s, 이동비 1칸당 %d" % (g, rt, life, MOVE_MAIN),
                })
    (OUT / "queue_realistic.json").write_text(json.dumps(cells, ensure_ascii=False, indent=1), encoding="utf-8")
    jobs = [{"kind": "campaign", "queue": "Result/adaptive_campaign/queue_realistic.json", "id": c["id"], "time": 600} for c in cells]
    jobs += [{"kind": "sweep", "id": c["id"], "time": 240, "units": "30"} for c in cells]
    jobs += [{"kind": "sweep", "id": c["id"], "time": 240, "units": "0"} for c in cells]
    deadline = (datetime.now() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
    (OUT / "plan_1008.json").write_text(json.dumps({"deadline": deadline, "jobs": jobs}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("cells %d, jobs %d, deadline %s" % (len(cells), len(jobs), deadline))


if __name__ == "__main__":
    main()
