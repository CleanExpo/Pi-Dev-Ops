"""A lane's saved state: the one file the PC lane supervisor reads (UNI-3291).

Each lane folder under the agent-work root (C:\\agent-work\\<lane>) may hold
`lane-state.json`. A lane opts in by writing it BEFORE it starts its long work, so a
reboot or a killed process leaves a record of what was running, where it got to, and how
to start it again. Lanes without the file are never touched.

    python lane_state.py begin --dir D --pid PID [--step S] [--linear UNI-1] -- ARGV...
    python lane_state.py run   --dir D --step S -- ARGV...   # a checkpointed long step
    python lane_state.py finish --dir D --state done|failed|parked [--note TEXT]
    python lane_state.py show  --dir D

`run` is how a long step (a receipt run, a Codex review) writes its checkpoint before it
starts: a step already in `steps_done` is skipped, so a resumed lane does not redo it.
A resumed lane is started with LANE_RESUME_STEP and LANE_STEPS_DONE in its environment.

`load` never returns an empty dict for a file it could not read: a broken state file is a
StateError, so the supervisor reports it rather than treating it as "nothing running".
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterator, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lane_proc  # noqa: E402

SCHEMA = "lane-state/1"
FILE = "lane-state.json"
RUNNING, DONE, FAILED, PARKED, HANDED_OFF = "running", "done", "failed", "parked", "handed_off"
STATES = (RUNNING, DONE, FAILED, PARKED, HANDED_OFF)
LOCK_SECONDS = 10.0


class StateError(Exception):
    """The state file exists but cannot be trusted."""


def path(lane_dir: str) -> Path:
    return Path(lane_dir) / FILE


@contextlib.contextmanager
def locked(lane_dir: str) -> Iterator[None]:
    """One writer at a time per lane: the lane itself and the supervisor both write."""
    fd = os.open(str(Path(lane_dir) / "lane-state.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if os.name == "nt":
            import msvcrt
            deadline = time.monotonic() + LOCK_SECONDS
            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise StateError(f"lane lock held over {LOCK_SECONDS}s: {lane_dir}")
                    time.sleep(0.1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)  # closing the descriptor releases either lock


def load(lane_dir: str) -> dict:
    try:
        st = json.loads(path(lane_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise StateError(f"{path(lane_dir)}: {e}") from e
    if not isinstance(st, dict) or st.get("schema") != SCHEMA or st.get("state") not in STATES:
        raise StateError(f"{path(lane_dir)}: not a {SCHEMA} state")
    return st


def save(lane_dir: str, st: dict) -> None:
    """Write atomically: a reboot mid-write leaves the old file, never half a new one."""
    st["updated_epoch"] = time.time()
    tmp = path(lane_dir).with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1), encoding="utf-8")
    os.replace(tmp, path(lane_dir))


def new_state(lane_dir: str, pid: int, argv: list, step: str, linear: Optional[str]) -> dict:
    now = time.time()
    return {"schema": SCHEMA, "lane": Path(lane_dir).name, "linear_id": linear, "state": RUNNING,
            "host": socket.gethostname(),
            "pid": pid, "pid_started": lane_proc.start_time(pid), "step": step, "steps_done": [],
            "resume": {"argv": argv, "cwd": str(lane_dir)}, "attempts": 0, "max_attempts": 3,
            "created_epoch": now, "history": []}


def begin(lane_dir: str, pid: int, argv: list, step: str = "start", linear: Optional[str] = None) -> dict:
    """Record a starting (or restarting) lane. A restart keeps finished steps and history."""
    with locked(lane_dir):
        try:
            old = load(lane_dir)
        except StateError:
            old = None
        st = new_state(lane_dir, pid, argv, step, linear)
        if old and old.get("state") == RUNNING:  # a resumed lane re-registering itself
            for k in ("steps_done", "attempts", "created_epoch", "history", "max_attempts"):
                st[k] = old.get(k, st[k])
            st["linear_id"] = linear or old.get("linear_id")
        save(lane_dir, st)
        return st


def update(lane_dir: str, **fields) -> dict:
    with locked(lane_dir):
        st = load(lane_dir)
        st.update(fields)
        save(lane_dir, st)
        return st


def run_step(lane_dir: str, step: str, argv: list) -> int:
    """Checkpoint, run one long step, record it done only when it exits 0."""
    if step in load(lane_dir).get("steps_done", []):
        print(f"lane_state: step {step} already done, skipped", file=sys.stderr)
        return 0
    update(lane_dir, step=step, step_started_epoch=time.time())
    rc = subprocess.run(argv, cwd=lane_dir).returncode
    if rc == 0:
        with locked(lane_dir):
            st = load(lane_dir)
            st["steps_done"] = st.get("steps_done", []) + [step]
            save(lane_dir, st)
    return rc


def _args(argv: Optional[list]) -> argparse.Namespace:
    """Options before `--`, the lane's own command after it, split by hand: argparse's
    REMAINDER after a positional swallows the options too."""
    argv = list(sys.argv[1:] if argv is None else argv)
    cut = argv.index("--") if "--" in argv else len(argv)
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("cmd", choices=("begin", "run", "finish", "show"))
    p.add_argument("--dir", required=True)
    p.add_argument("--pid", type=int)
    p.add_argument("--step", default="start")
    p.add_argument("--linear")
    p.add_argument("--state", choices=(DONE, FAILED, PARKED))
    p.add_argument("--note", default="")
    a = p.parse_args(argv[:cut])
    a.rest = argv[cut + 1:]
    return a


def main(argv: Optional[list] = None) -> int:
    a = _args(argv)
    if a.cmd == "begin":
        if not a.pid or not a.rest:
            raise SystemExit("begin needs --pid and the resume command after --")
        print(json.dumps(begin(a.dir, a.pid, a.rest, a.step, a.linear)))
    elif a.cmd == "run":
        return run_step(a.dir, a.step, a.rest)
    elif a.cmd == "finish":
        if not a.state:
            raise SystemExit("finish needs --state")
        update(a.dir, state=a.state, note=a.note, finished_epoch=time.time())
    else:
        print(json.dumps(load(a.dir), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
