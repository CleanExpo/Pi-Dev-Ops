"""Single owner of lane transitions, launch identity and durable decision events."""
from __future__ import annotations

import contextlib
import json
import os
import secrets
import socket
import sys
import time
from pathlib import Path
from typing import Iterator, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lane_proc  # noqa: E402
from lane_board import board_event  # noqa: E402

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
            "created_epoch": now, "history": [], "pending_events": []}


# Source -> destination for every lifecycle operation; guards run under the lock.
TRANSITIONS = {
    "begin": dict.fromkeys((None,) + STATES, RUNNING),
    "parked": {RUNNING: PARKED}, "handed_off": {RUNNING: HANDED_OFF},
    "launch": {RUNNING: RUNNING}, "settle": {RUNNING: RUNNING},
    "finish": {RUNNING: (DONE, FAILED, PARKED)},
}
SAME = ("state", "pid", "pid_started", "attempts", "launching")
KEEP = ("steps_done", "attempts", "created_epoch", "history", "max_attempts", "pending_events")


def _begin_allowed(old: dict, token: Optional[str], fresh: bool) -> None:
    source = old["state"]
    if source not in TRANSITIONS["begin"]:
        raise StateError("invalid begin transition")
    if source in (PARKED, HANDED_OFF) and not fresh:
        raise StateError(f"{source} requires --fresh")
    launch = old.get("launching")
    if launch:
        if source != RUNNING or not token or launch.get("token") != token:
            raise StateError("begin requires the current launch token")
    elif token:
        raise StateError("launch token expired or already registered")
    elif source == RUNNING and lane_proc.alive(old.get("pid"), old.get("pid_started")) is not False:
        raise StateError("recorded process is alive or liveness is unknown")


def begin(lane_dir: str, pid: int, argv: list, step: str = "start", linear: Optional[str] = None,
          *, fresh: bool = False, token: Optional[str] = None) -> dict:
    with locked(lane_dir):
        old = load(lane_dir) if path(lane_dir).exists() else None
        if old:
            _begin_allowed(old, token, fresh)
        elif token:
            raise StateError("launch token has no saved intent")
        st = new_state(lane_dir, pid, argv, step, linear)
        if old:
            reset = fresh and old["state"] in (DONE, FAILED)
            for key in (("pending_events",) if reset else KEEP):
                st[key] = old.get(key, st[key])
            st["linear_id"] = linear or old.get("linear_id")
            if token:
                st["last_launch"] = old.get("launching") or old.get("last_launch")
                st["launch_registered"] = True
        save(lane_dir, st)
        return st


def update(lane_dir: str, **fields) -> dict:
    with locked(lane_dir):
        st = load(lane_dir)
        if "state" in fields:
            if fields["state"] not in TRANSITIONS["finish"].get(st["state"], ()):
                raise StateError("invalid finish transition")
            if st.get("launching"):
                st["last_launch"] = st.pop("launching")
                st["launch_registered"] = True
        st.update(fields)
        save(lane_dir, st)
        return st


def _record(st: dict, deps, action: str, **entry) -> None:
    st["history"] = (st.get("history", []) + [dict(epoch=deps.now(), action=action, **entry)])[-50:]


def _announce(st: dict, deps, action: str, **kw) -> None:
    st["pending_events"] = st.get("pending_events", []) + [board_event(st, action, deps.now(), **kw)]


def recover(lane_dir: str, seen: dict, deps, action: str, **details) -> Optional[dict]:
    """One guarded decision, including its outbox line, in one atomic write."""
    with locked(lane_dir):
        st = load(lane_dir)
        if st["state"] not in TRANSITIONS[action] or any(st.get(k) != seen.get(k) for k in SAME):
            return None
        if (Path(lane_dir) / "STOP").exists() or deps.alive(st.get("pid"), st.get("pid_started")) is not False:
            return None
        _recover_change(st, deps, action, details)
        save(lane_dir, st)
        return st


def _recover_change(st: dict, deps, action: str, details: dict) -> None:
    if action == "launch":
        st["attempts"] = st.get("attempts", 0) + 1
        st["launching"] = dict(attempt=st["attempts"], token=secrets.token_hex(16),
                               epoch=deps.now(), old_pid=st.get("pid"))
        return
    st["state"] = action
    if action == PARKED:
        st["note"] = details["why"]
        if st.get("launching"):
            st["last_launch"] = st.pop("launching")
            st["launch_registered"] = True
    else:
        st["handed_to"] = details["target"]
    history = dict(details, from_step=st.get("step")) if action == HANDED_OFF else details
    _record(st, deps, action, **history)
    _announce(st, deps, action, **details)


def launch_current(lane_dir: str, marker: dict) -> bool:
    """Recheck the exact durable intent after preparing the spawn arguments."""
    with locked(lane_dir):
        st = load(lane_dir)
        return st["state"] == RUNNING and st.get("launching") == marker and not (Path(lane_dir) / "STOP").exists()


def settle(lane_dir: str, marker: dict, deps, pid: Optional[int], error: str = "") -> dict:
    with locked(lane_dir):
        st = load(lane_dir)
        mine = st.get("launching") == marker
        registered = st.get("last_launch") == marker and st.get("launch_registered") and st.get("pid") == pid
        if st["state"] not in TRANSITIONS["settle"] or not (mine or registered):
            return st
        if mine and error:
            st.pop("launching")
            st["last_launch"] = marker
            st["launch_registered"] = True
        if error:
            _record(st, deps, "relaunch_failed", attempt=marker["attempt"], error=error[:300])
        else:
            if mine:
                # Only begin consumes the token; a child may register after this save.
                st.update(pid=pid, pid_started=deps.start_time(pid))
            st["resumed_epoch"] = deps.now()
            _record(st, deps, "resumed", attempt=marker["attempt"], from_step=st.get("step"),
                    pid=pid, old_pid=marker.get("old_pid"))
            _announce(st, deps, "resumed")
        save(lane_dir, st)
        return st


def clear_sent(lane_dir: str, uids: set) -> None:
    with locked(lane_dir):
        st = load(lane_dir)
        st["pending_events"] = [e for e in st.get("pending_events", []) if e.get("uid") not in uids]
        save(lane_dir, st)


def complete_step(lane_dir: str, step: str) -> None:
    with locked(lane_dir):
        st = load(lane_dir)
        if step not in st.get("steps_done", []):
            st["steps_done"] = st.get("steps_done", []) + [step]
            save(lane_dir, st)


def run_step(*args) -> int:
    from lane_state_cli import run_step as run
    return run(*args)


def main(argv=None) -> int:
    from lane_state_cli import main as cli
    return cli(argv)


if __name__ == "__main__":
    # Avoid a second module instance when the CLI imports lane_state.
    sys.modules["lane_state"] = sys.modules[__name__]
    sys.exit(main())
