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
4. parks a lane that has already been relaunched max_attempts times, so a lane that
   dies on every start is not restarted forever;
5. writes one board line per decision (lane_board.py) and one log line per tick.

It never kills, stops or signals any process. A lane folder holding a STOP file is
skipped. Log: <root>\\.lane-supervisor\\supervisor.log; last tick: last-tick.json.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
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

ROOT = os.environ.get("LANE_ROOT", r"C:\agent-work")
MAX_LOCAL = int(os.environ.get("LANE_SUPERVISOR_MAX_LOCAL", "4"))
HOSTS = {"mini": "Mini", "macbook": "MacBook"}  # ssh alias -> board name


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
    """broken | idle | stopped | live | dead."""
    if isinstance(st, Exception):
        return "broken"
    if st["state"] != lane_state.RUNNING:
        return "idle"
    if (Path(lane_dir) / "STOP").exists():
        return "stopped"
    return "dead" if deps.alive(st.get("pid"), st.get("pid_started")) is False else "live"


def board_event(st: dict, action: str, deps: Deps, target: str = "") -> dict:
    lane, step = st["lane"], st.get("step", "start")
    who = f"{lane} ({st['linear_id']})" if st.get("linear_id") else lane
    tail = {"resumed": "resumed on PC", "handed_off": f"handed to {target}",
            "parked": f"parked after {st.get('attempts', 0)} relaunches, needs a person"}[action]
    note = (f"Lane folder {st.get('resume', {}).get('cwd')} on {st.get('host')}. Last step: {step}. "
            f"Steps done: {', '.join(st.get('steps_done', [])) or 'none'}. Saved command and history: "
            f"lane-state.json in that folder.")
    if action == "handed_off":
        note = f"Resume lane {lane} on {target} from step {step}. " + note
    return {"id": "PC-LANE-" + re.sub(r"[^A-Z0-9]+", "-", lane.upper()).strip("-"),
            "uid": f"{lane}:{action}:{int(deps.now())}:{st.get('attempts', 0)}", "lane": lane,
            "action": action, "target": target, "linear": st.get("linear_id"),
            "text": f"PC lane {who} stopped at step {step}: {tail}", "note": note}


def _history(st: dict, deps: Deps, **entry) -> None:
    st["history"] = (st.get("history", []) + [dict(epoch=deps.now(), **entry)])[-50:]


def relaunch(lane_dir: str, deps: Deps) -> Optional[dict]:
    """Start the lane's saved command again. None when the state changed under us."""
    with lane_state.locked(lane_dir):
        st = lane_state.load(lane_dir)
        if st["state"] != lane_state.RUNNING or deps.alive(st.get("pid"), st.get("pid_started")) is not False:
            return None  # the lane restarted itself, or finished, since the scan
        attempt = st.get("attempts", 0) + 1
        env = dict(os.environ, LANE_RESUMED="1", LANE_STATE_DIR=lane_dir, LANE_RESUME_ATTEMPT=str(attempt),
                   LANE_RESUME_STEP=st.get("step", "start"), LANE_STEPS_DONE=",".join(st.get("steps_done", [])))
        resume = st.get("resume", {})
        log_path = os.path.join(lane_dir, f"resume-{attempt}.log")
        old_pid, st["attempts"] = st.get("pid"), attempt
        try:
            pid = deps.spawn(resume["argv"], resume.get("cwd") or lane_dir, env, log_path)
        except (OSError, KeyError, TypeError) as e:
            _history(st, deps, action="relaunch_failed", error=str(e)[:300], old_pid=old_pid)
            lane_state.save(lane_dir, st)
            raise
        st.update(pid=pid, pid_started=deps.start_time(pid), resumed_epoch=deps.now())
        _history(st, deps, action="resumed", from_step=st.get("step"), old_pid=old_pid, pid=pid)
        lane_state.save(lane_dir, st)
        return st


def hand_off(lane_dir: str, deps: Deps) -> Optional[tuple]:
    host = next((h for h in deps.hosts if deps.reachable(h)), None)
    if host is None:
        return None
    target = HOSTS.get(host, host)
    with lane_state.locked(lane_dir):
        st = lane_state.load(lane_dir)
        st.update(state=lane_state.HANDED_OFF, handed_to=target)
        _history(st, deps, action="handed_off", target=target, from_step=st.get("step"))
        lane_state.save(lane_dir, st)
    return st, target


def decide(root: str, lane_dir: str, st: dict, live: int, deps: Deps) -> tuple:
    """Act on one dead lane. Returns (outcome, live lane count after it)."""
    if st.get("attempts", 0) >= st.get("max_attempts", 3):
        st = lane_state.update(lane_dir, state=lane_state.PARKED, note="relaunch limit reached")
        lane_board.queue(root, board_event(st, "parked", deps))
        return "parked", live
    if live < deps.max_local:
        try:
            new = relaunch(lane_dir, deps)
        except Exception as e:  # noqa: BLE001 - one bad lane must not stop the others
            log(root, f"{st['lane']}: relaunch failed: {e}")
            return "relaunch_failed", live
        if new is None:
            return "changed", live
        lane_board.queue(root, board_event(new, "resumed", deps))
        return "resumed", live + 1
    got = hand_off(lane_dir, deps)
    if got is None:
        return "waiting", live  # PC busy and no Mac reachable: try again next tick
    lane_board.queue(root, board_event(got[0], "handed_off", deps, got[1]))
    return "handed_off", live


def run_tick(root: str, deps: Deps) -> dict:
    lanes = [(d, st, classify(d, st, deps)) for d, st in scan(root)]
    live = sum(1 for _, _, c in lanes if c == "live")
    summary = {"epoch": deps.now(), "lanes": len(lanes), "live": live, "actions": {},
               "broken": [Path(d).name for d, _, c in lanes if c == "broken"]}
    dead = sorted((x for x in lanes if x[2] == "dead"), key=lambda x: x[1].get("updated_epoch", 0))
    for d, st, _ in dead:
        outcome, live = decide(root, d, st, live, deps)
        summary["actions"][Path(d).name] = outcome
    summary["board_sent"], summary["board_error"] = lane_board.flush(root, deps.send)
    summary["board_pending"] = lane_board.outbox(root).exists()
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
