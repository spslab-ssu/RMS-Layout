# -*- coding: utf-8 -*-
"""이동비 스윕의 포락선 교차평가.

왜 필요한가
-----------
이동비를 올렸는데 목적값이 내려가거나 이득이 늘어나는 비단조 결과는
최적해라면 불가능하다. 미수렴(TIME_LIMIT) incumbent를 이동비별로 나란히
놓으면 생기는 인공물이다. 교수님 세미나 자료 p.41 표, 서훈 모델(이동비 0에서
35,712 / 거리당 1에서 35,675), 그리고 우리 alpha 스윕(0.01에서 92.2 /
0.02에서 227.8)이 전부 같은 현상이다.

고치는 법
---------
각 해 k는 이동비 계수 u에 대해 직선이다:  cost_k(u) = N_k + u * M_k
  N_k = 구매 + 재구성 + MHC        (u와 무관)
  M_k = 이동비 / u                  (그 해의 이동 구성으로 결정)
어떤 u에서 찾은 해든 다른 u에서 그대로 실행 가능하므로, 참 최적값의 상한은
포락선  UB(u) = min_k (N_k + u * M_k)  이다. 이것은 항상 단조 비감소이고
비단조 인공물이 사라진다.

off가 OPTIMAL로 증명돼 있으면  이득(u) >= OFF - UB(u)  가 유효 하한이 된다.

사용법
------
  python scratchpad/envelope_eval.py <off_obj> <id1> <id2> ...
    id는 campaign_results.json의 시나리오 id. spec.json에서 alpha/beta 또는
    move_cost_flat을 읽어 u를 정한다.
  python scratchpad/envelope_eval.py 15595 R_layers_12_a010 R_layers_12_a020
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "Result" / "adaptive_campaign"


def load(sid):
    rows = json.loads((ROOT / "campaign_results.json").read_text(encoding="utf-8"))
    r = next((x for x in rows if x.get("id") == sid), None)
    if r is None:
        raise SystemExit("결과에 없음: %s" % sid)
    spec = json.loads((ROOT / sid / "spec.json").read_text(encoding="utf-8"))
    j = r["joint"]
    # u 정의: alpha가 있으면 alpha (beta는 alpha에 비례해 묶었다고 가정),
    #         없으면 move_cost_flat.
    u = spec.get("alpha", spec.get("move_cost_flat", 0.0))
    N = (j.get("purchase") or 0) + (j.get("reconfig") or 0) + (j.get("mhc") or 0)
    mv = j.get("move") or 0.0
    if u and mv:
        M = mv / u
    elif not mv:
        M = None          # u=0에서 찾은 해는 이동비가 0이라 M을 역산할 수 없다
    else:
        M = None
    return {"id": sid, "u": u, "N": N, "move": mv, "M": M,
            "obj": j.get("obj"), "status": j.get("status"),
            "gap": j.get("gap"), "reloc": j.get("relocations"), "dist": j.get("move_distance")}


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    off = float(sys.argv[1])
    sols = [load(s) for s in sys.argv[2:]]

    print("off (OPTIMAL 가정) = %.1f\n" % off)
    print("%-22s %-7s %-10s %-9s %-9s %-7s %-6s %-8s" %
          ("id", "u", "N_k", "이동비", "M_k", "이동", "거리", "gap"))
    usable = []
    for s in sols:
        print("%-22s %-7s %-10.1f %-9.2f %-9s %-7s %-6s %-8s" %
              (s["id"], s["u"], s["N"], s["move"],
               ("%.1f" % s["M"]) if s["M"] is not None else "역산불가",
               s["reloc"], s["dist"],
               ("%.2f%%" % (100 * s["gap"])) if s["gap"] is not None else "-"))
        if s["M"] is not None:
            usable.append(s)
    if not usable:
        raise SystemExit("\nM_k를 역산할 수 있는 해가 없다 (이동비 0인 해만 있음).")

    print("\n포락선 UB(u) = min_k (N_k + u*M_k),  이득 >= off - UB(u)")
    print("%-9s %-11s %-9s %-8s %-22s" % ("u", "UB", "이득", "이득%", "채택 해"))
    grid = sorted({0.0} | {s["u"] for s in usable} |
                  {round(x * 0.005, 4) for x in range(1, 21)})
    for u in grid:
        ub, k = min((s["N"] + u * s["M"], s["id"]) for s in usable)
        g = off - ub
        mark = "  <- 보고값 %.1f" % (off - next(s["obj"] for s in usable if s["u"] == u)) \
            if any(abs(s["u"] - u) < 1e-12 for s in usable) else ""
        print("%-9.4f %-11.1f %-9.1f %-8.2f %-22s%s" % (u, ub, g, 100 * g / off, k, mark))

    best = min(usable, key=lambda s: s["M"])
    if best["M"] > 0:
        u_star = (off - best["N"]) / best["M"]
        print("\n이동이 가장 적은 해로 외삽: 이득(u) = %.1f - %.1f*u" % (off - best["N"], best["M"]))
        print("  손익분기 u* >= %.4f   (해 %s 기준. 더 나은 해가 있으면 u*는 더 커진다)"
              % (u_star, best["id"]))


if __name__ == "__main__":
    main()
