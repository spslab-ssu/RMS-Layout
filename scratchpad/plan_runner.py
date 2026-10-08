# -*- coding: utf-8 -*-
"""작업 목록(plan JSON)을 마감 시각 안에서 순서대로 실행한다. 독립 프로세스로 띄우는 용도.

plan 형식:
  {"deadline": "2026-10-06 07:15:00",
   "jobs": [{"kind": "cutoff",   "id": "F_...", "time": 3600},
            {"kind": "campaign", "queue": "Result/.../queue.json", "id": "F_..._r100", "time": 600}]}
각 작업 시작 전에 남은 시간을 확인해, 최대 소요(cutoff: time+3분, campaign: off+joint 2*time+3분)가
마감을 넘으면 건너뛴다. 진행 기록은 Result/adaptive_campaign/plan_status.txt.

사용법: python scratchpad/plan_runner.py PLAN.json
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STATUS = REPO / "Result" / "adaptive_campaign" / "plan_status.txt"
LOG = REPO / "Result" / "adaptive_campaign" / "plan_run.out"


def log(msg):
    with open(STATUS, "a", encoding="utf-8") as fh:
        fh.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))


def main():
    plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    deadline = datetime.strptime(plan["deadline"], "%Y-%m-%d %H:%M:%S")
    env = dict(os.environ, PYTHONUTF8="1")
    log("시작: 작업 %d개, 마감 %s" % (len(plan["jobs"]), plan["deadline"]))
    for i, job in enumerate(plan["jobs"], 1):
        t = int(job["time"])
        if job["kind"] == "cutoff":
            need = t + 180
        elif job["kind"] == "sweep":
            need = t * len(job["units"].split(",")) + 180
        else:
            need = 2 * t + 180
        remaining = (deadline - datetime.now()).total_seconds()
        name = "[%d/%d] %s %s" % (i, len(plan["jobs"]), job["kind"], job["id"])
        if remaining < need:
            log("건너뜀 %s (남은 %ds < 필요 %ds)" % (name, remaining, need))
            continue
        log("시작 %s (최대 %ds)" % (name, need))
        if job["kind"] == "cutoff":
            cmd = [sys.executable, "scratchpad/off_cutoff_run.py", job["id"], str(t)]
        elif job["kind"] == "sweep":
            cmd = [sys.executable, "scratchpad/move_cost_sweep.py", job["id"], str(t), job["units"]]
        else:
            cmd = [sys.executable, "scratchpad/campaign_run.py", job["queue"], str(t), job["id"]]
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write("\n##### %s %s\n" % (time.strftime("%H:%M:%S"), name))
            fh.flush()
            rc = subprocess.call(cmd, cwd=REPO, stdout=fh, stderr=subprocess.STDOUT, env=env)
        log("종료 %s (exit %d)" % (name, rc))
    log("전체 완료")


if __name__ == "__main__":
    main()
