#!/usr/bin/env python3
"""Red-main auto-owner watcher (RA-8174). Stdlib only, no model, no paid API.

    red_main_watch.py scan                      one cycle (launchd, every 5 min on the Mini)
    red_main_watch.py annotate < facts.txt      owner + age on AMBER/RED lines, red-main lines first
    red_main_watch.py lines                     the live red-main lines only
    red_main_watch.py claim <Org/Repo> <LINEAR-ID> "<agent on machine>"
    red_main_watch.py park <JOB-ID> <Org/Repo>  park a job until that repo's main is green

Env: RED_MAIN_LAUNCH=1 lets scan start lanes (off by default, so a manual or test run
never spawns a session). RED_MAIN_OPS, RED_MAIN_GH, RED_MAIN_HOSTS, RED_MAIN_REPOS,
RED_MAIN_STATE_DIR, RED_MAIN_NOW are test and deployment seams. See scripts/red_main/README.md.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from red_main import annotate, board, store, watch  # noqa: E402
from red_main.common import now  # noqa: E402


def _annotate(lines: list[str]) -> int:
    at = now()
    seen = store.load_state("red-main-annotate.json").get("seen", {})
    problems = store.load_state("red-main-watch.json").get("problems", [])
    result = {}

    def mutate(d):
        out, new_seen, changed = annotate.annotate(lines + problems, d, seen, at)
        result.update(out=out, seen=new_seen)
        return changed

    store.update_jobs(mutate)
    store.save_state("red-main-annotate.json", {"seen": result["seen"]})
    print("\n".join(result["out"]))
    return 0


def _board_edit(fn, *args) -> int:
    at = now()
    done = store.update_jobs(lambda d: fn(d, *args, at))
    print("updated" if done else "not changed (card missing, done, or bad arguments)")
    return 0 if done else 1


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "scan"
    if cmd == "scan":
        for line in watch.cycle():
            print(line)
        return 0
    if cmd == "annotate":
        return _annotate([x.rstrip("\n") for x in sys.stdin])
    if cmd == "lines":
        print("\n".join(annotate.red_main_lines(store.read_jobs(), now())))
        return 0
    if cmd == "claim" and len(argv) == 5:
        return _board_edit(board.claim, argv[2], argv[3], argv[4])
    if cmd == "park" and len(argv) == 4:
        return _board_edit(board.park, argv[2], argv[3])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
