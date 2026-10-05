# -*- coding: utf-8 -*-
"""선행 실험이 끝나길 기다렸다가 큐들을 차례로 실행한다 (도구 시간 제한과 무관하게 독립 프로세스로 띄움).

사용법: python scratchpad/chain_runs.py WAIT_ID QUEUE1.json:LOG1 [QUEUE2.json:LOG2 ...]
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "Result" / "adaptive_campaign" / "campaign_results.json"
STATUS = REPO / "Result" / "adaptive_campaign" / "chain_status.txt"


def done_ids():
    try:
        return {r.get("id") for r in json.loads(RESULTS.read_text(encoding="utf-8"))}
    except Exception:
        return set()


def log(msg):
    with open(STATUS, "a", encoding="utf-8") as fh:
        fh.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))


def main():
    wait_id = sys.argv[1]
    log("대기 시작: %s" % wait_id)
    while wait_id not in done_ids():
        time.sleep(15)
    log("선행 완료: %s" % wait_id)
    env = dict(os.environ, PYTHONUTF8="1")
    for item in sys.argv[2:]:
        queue, out = item.split(":", 1)
        log("시작: %s" % queue)
        with open(REPO / out, "w", encoding="utf-8") as fh:
            rc = subprocess.call([sys.executable, "scratchpad/campaign_run.py", queue, "600"],
                                 cwd=REPO, stdout=fh, stderr=subprocess.STDOUT, env=env)
        log("종료: %s (exit %d)" % (queue, rc))
        if rc != 0:
            log("실패로 중단")
            return
    log("전체 완료")


if __name__ == "__main__":
    main()
