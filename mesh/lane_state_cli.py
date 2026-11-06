"""CLI and checkpoint runner for lane_state; state decisions stay in lane_state."""
import argparse
import json
import os
import subprocess
import sys
import time
from typing import Optional

from lane_state import StateError, DONE, FAILED, PARKED, begin, complete_step, load, update

def run_step(lane_dir: str, step: str, argv: list) -> int:
    """Checkpoint, run one long step, record it done only when it exits 0."""
    if step in load(lane_dir).get("steps_done", []):
        print(f"lane_state: step {step} already done, skipped", file=sys.stderr)
        return 0
    update(lane_dir, step=step, step_started_epoch=time.time())
    rc = subprocess.run(argv, cwd=lane_dir).returncode
    if rc == 0:
        complete_step(lane_dir, step)
    return rc


def _args(argv: Optional[list]) -> argparse.Namespace:
    """Options before `--`, the lane's own command after it, split by hand: argparse's
    REMAINDER after a positional swallows the options too."""
    argv = list(sys.argv[1:] if argv is None else argv)
    cut = argv.index("--") if "--" in argv else len(argv)
    p = argparse.ArgumentParser(description="Lane checkpoint state")
    p.add_argument("cmd", choices=("begin", "run", "finish", "show"))
    p.add_argument("--dir", required=True)
    p.add_argument("--pid", type=int)
    p.add_argument("--step", default="start")
    p.add_argument("--linear")
    p.add_argument("--fresh", action="store_true")
    p.add_argument("--state", choices=(DONE, FAILED, PARKED))
    p.add_argument("--note", default="")
    a = p.parse_args(argv[:cut])
    a.rest = argv[cut + 1:]
    return a


def _main(argv: Optional[list] = None) -> int:
    a = _args(argv)
    if a.cmd == "begin":
        if not a.pid or not a.rest:
            raise SystemExit("begin needs --pid and the resume command after --")
        print(json.dumps(begin(a.dir, a.pid, a.rest, a.step, a.linear, fresh=a.fresh, token=os.environ.get("LANE_LAUNCH_TOKEN"))))
    elif a.cmd == "run":
        return run_step(a.dir, a.step, a.rest)
    elif a.cmd == "finish":
        if not a.state:
            raise SystemExit("finish needs --state")
        update(a.dir, state=a.state, note=a.note, finished_epoch=time.time())
    else:
        print(json.dumps(load(a.dir), indent=1))
    return 0


def main(argv=None) -> int:
    try:
        return _main(argv)
    except StateError as error:
        print(f"lane_state: {error}", file=sys.stderr)
        return 1
