"""PC lane supervisor: resume or hand off lanes a reboot or a crash left dead (UNI-3291).

The Task Scheduler task NexusLaneSupervisor runs `lane_supervisor.py tick` at logon and
every 5 minutes (mesh/windows/register_lane_supervisor.ps1). Each tick:

1. reads `<root>\\<lane>\\lane-state.json` for every lane folder (lane_state.py);
2. finds lanes whose state is `running` but whose saved process is PROVEN gone: the pid
   is free, or it now belongs to a process with a different start time (a reused pid
   after a reboot). A process it cannot inspect counts as alive, so it is left alone;
3. relaunches each dead lane from its saved command, with its last step in the
   environment, while the PC runs fewer than LANE_SUPERVISOR_MAX_LOCAL live lanes;
   past that it hands the lane to the first reachable of Mini or MacBook instead;
4. parks a lane that has already been relaunched max_attempts times, or whose last
   relaunch started a process that was never recorded, so nothing runs twice;
5. writes one board line per decision (lane_board.py) and one log line per tick.

Every decision goes through lane_state.recover: under the lane's lock it reloads the state and
acts only if it is still the same dead lane the scan saw (same pid, start time, attempt
count and launch marker). The board line is saved inside the lane's state in that same
write and removed only when the Mini confirms it, so no decision loses its line. A
relaunch saves a `launching` marker BEFORE it starts the process.

It never kills, stops or signals any process. A lane folder holding a STOP file is
skipped. Log: <root>\\.lane-supervisor\\supervisor.log; last tick: last-tick.json.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lane_board  # noqa: E402
import lane_proc  # noqa: E402
import lane_state  # noqa: E402
from lane_board import board_event  # noqa: E402,F401 - re-exported for callers and tests

ROOT = os.environ.get("LANE_ROOT", r"C:\agent-work")
MAX_LOCAL = int(os.environ.get("LANE_SUPERVISOR_MAX_LOCAL", "4"))
HOSTS = {"mini": "Mini", "macbook": "MacBook"}  # ssh alias -> board name
UNRECORDED = "a relaunch started a process that was never recorded; check for a running copy first"


def _reachable(host: str) -> bool:
    return lane_proc.run_quiet(lane_board.SSH + [host, "true"], timeout=20)[0] == 0


@dataclass
class Deps:
    """Everything a tick touches outside its own files, so tests can stand in for it."""
    alive: Callable = lane_proc.alive
    start_time: Callable = lane_proc.start_time
    spawn: Callable = lane_proc.spawn
    reachable: Callable = _reachable
    send: Callable = lane_board.ssh_send
    now: Callable = time.time
    max_local: int = MAX_LOCAL
    hosts: list = field(default_factory=lambda: [h for h in os.environ.get(
        "LANE_SUPERVISOR_HANDOFF_HOSTS", "mini,macbook").split(",") if h])


def sup_dir(root: str) -> Path:
    d = Path(root) / ".lane-supervisor"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log(root: str, msg: str) -> None:
    with open(sup_dir(root) / "supervisor.log", "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S AEST ") + msg + "\n")


@contextlib.contextmanager
def tick_lock(root: str) -> Iterator[bool]:
    """True when this tick owns the lock. The OS frees it if the tick dies."""
    fd = os.open(str(sup_dir(root) / "tick.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        yield True
    finally:
        os.close(fd)


def scan(root: str) -> list:
    """[(lane_dir, state dict or StateError)] for every lane folder that opted in."""
    out = []
    for d in sorted(Path(root).iterdir()) if Path(root).is_dir() else []:
        if d.is_dir() and not d.name.startswith((".", "_")) and lane_state.path(str(d)).exists():
            try:
                out.append((str(d), lane_state.load(str(d))))
            except lane_state.StateError as e:
                out.append((str(d), e))
    return out


def classify(lane_dir: str, st, deps: Deps) -> str:
    """broken | idle | stopped | live | dead | unrecorded."""
    if isinstance(st, Exception):
        return "broken"
    if st["state"] != lane_state.RUNNING:
        return "idle"
    if (Path(lane_dir) / "STOP").exists():
        return "stopped"
    if deps.alive(st.get("pid"), st.get("pid_started")) is not False:
        return "live"
    return "unrecorded" if st.get("launching") else "dead"


def park(lane_dir: str, seen: dict, deps: Deps, why: str) -> Optional[dict]:
    return lane_state.recover(lane_dir, seen, deps, "parked", why=why)


def hand_off(lane_dir: str, seen: dict, deps: Deps, target: str) -> Optional[dict]:
    return lane_state.recover(lane_dir, seen, deps, "handed_off", target=target)


def _settle(lane_dir: str, marker: dict, deps: Deps, pid: Optional[int], error: str = "") -> dict:
    return lane_state.settle(lane_dir, marker, deps, pid, error)


def _prepare_spawn(lane_dir: str, st: dict) -> tuple:
    n = st["attempts"]
    env = dict(os.environ, LANE_RESUMED="1", LANE_STATE_DIR=lane_dir, LANE_RESUME_ATTEMPT=str(n),
               LANE_LAUNCH_TOKEN=st["launching"]["token"], LANE_RESUME_STEP=st.get("step", "start"),
               LANE_STEPS_DONE=",".join(st.get("steps_done", [])))
    resume = st["resume"]
    return resume["argv"], resume.get("cwd") or lane_dir, env, os.path.join(lane_dir, f"resume-{n}.log")


def relaunch(lane_dir: str, seen: dict, deps: Deps) -> Optional[dict]:
    """Mark the launch, start the saved command, record its pid. None if the lane changed."""
    st = lane_state.recover(lane_dir, seen, deps, "launch")
    if st is None:
        return None
    marker = st["launching"]
    try:
        args = _prepare_spawn(lane_dir, st)
        if not lane_state.launch_current(lane_dir, marker):
            return None
        pid = deps.spawn(*args)
    except (OSError, KeyError, TypeError) as e:
        _settle(lane_dir, marker, deps, None, error=f"{type(e).__name__}: {e}")
        raise
    return _settle(lane_dir, marker, deps, pid)


def decide(root: str, lane_dir: str, seen: dict, kind: str, live: int, deps: Deps) -> tuple:
    """Act on one dead lane. Returns (outcome, live lane count after it)."""
    limit = seen.get("attempts", 0) >= seen.get("max_attempts", 3)
    if kind == "unrecorded" or limit:
        why = UNRECORDED if kind == "unrecorded" else f"relaunch limit reached after {seen.get('attempts')} relaunches"
        return ("parked" if park(lane_dir, seen, deps, why) else "changed"), live
    if live < deps.max_local:
        try:
            new = relaunch(lane_dir, seen, deps)
        except Exception as e:  # noqa: BLE001 - one bad lane must not stop the others
            log(root, f"{seen['lane']}: relaunch failed: {e}")
            return "relaunch_failed", live
        return ("resumed", live + 1) if new else ("changed", live)
    host = next((h for h in deps.hosts if deps.reachable(h)), None)
    if host is None:
        return "waiting", live  # PC busy and no Mac reachable: try again next tick
    return ("handed_off" if hand_off(lane_dir, seen, deps, HOSTS.get(host, host)) else "changed"), live


def _clear_sent(lane_dir: str, uids: set) -> None:
    lane_state.clear_sent(lane_dir, uids)


def flush_board(lane_dirs: list, deps: Deps) -> tuple:
    """Send every saved board line in one board edit. Returns (sent, error, still pending)."""
    events = []
    for d in lane_dirs:
        with contextlib.suppress(lane_state.StateError):
            events += lane_state.load(d).get("pending_events", [])
    if not events:
        return 0, "", False
    ok, out = deps.send(events)
    if not ok:
        return 0, out.strip()[-300:] or "board write not confirmed", True
    for d in lane_dirs:  # a failed clear only means a resend, which the Mini ignores by uid
        with contextlib.suppress(lane_state.StateError, OSError):
            _clear_sent(d, {e["uid"] for e in events})
    return len(events), "", False


def run_tick(root: str, deps: Deps) -> dict:
    lanes = [(d, st, classify(d, st, deps)) for d, st in scan(root)]
    live = sum(1 for _, _, c in lanes if c == "live")
    summary = {"epoch": deps.now(), "lanes": len(lanes), "live": live, "actions": {},
               "broken": [Path(d).name for d, _, c in lanes if c == "broken"]}
    dead = sorted((x for x in lanes if x[2] in ("dead", "unrecorded")), key=lambda x: x[1].get("updated_epoch", 0))
    for d, st, kind in dead:
        try:
            outcome, live = decide(root, d, st, kind, live, deps)
        except Exception as e:  # noqa: BLE001 - a failed save changes nothing; next tick decides again
            log(root, f"{Path(d).name}: decision not saved: {type(e).__name__}: {e}")
            outcome = "error"
        summary["actions"][Path(d).name] = outcome
    sent, err, pending = flush_board([d for d, st, _ in lanes if isinstance(st, dict)], deps)
    summary.update(board_sent=sent, board_error=err, board_pending=pending)
    return summary


def tick(root: str = ROOT, deps: Optional[Deps] = None) -> dict:
    deps = deps or Deps()
    with tick_lock(root) as mine:
        if not mine:
            log(root, "tick skipped: another tick holds the lock")
            return {"skipped": True}
        s = run_tick(root, deps)
        (sup_dir(root) / "last-tick.json").write_text(json.dumps(s, indent=1), encoding="utf-8")
        log(root, f"tick lanes={s['lanes']} live={s['live']} actions={s['actions'] or 'none'} "
                  f"broken={s['broken'] or 'none'} board_sent={s['board_sent']} pending={s['board_pending']}"
                  + (f" board_error={s['board_error']!r}" if s["board_error"] else ""))
        return s


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description="PC lane supervisor (UNI-3291)")
    p.add_argument("cmd", choices=("tick", "status"))
    p.add_argument("--root", default=ROOT)
    a = p.parse_args(argv)
    if a.cmd == "status":  # read-only: what a tick would see, acting on nothing
        deps = Deps()
        for d, st in scan(a.root):
            print(Path(d).name, classify(d, st, deps), "" if isinstance(st, dict) else st)
        return 0
    try:
        tick(a.root)
    except Exception:  # noqa: BLE001 - pythonw has no console: the log is the only witness
        log(a.root, "tick crashed: " + traceback.format_exc().replace("\n", " | "))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
