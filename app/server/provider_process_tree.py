"""Process-tree bookkeeping for stopping a model CLI call (UNI-3306).

A stop must leave nothing running. The CLI runs in its own process group, but a descendant
that calls setsid() leaves that group, so every descendant is also recorded by parent link and
stopped by pid. Anything still alive afterwards is logged with its pid and command.
"""
from __future__ import annotations
import logging
import os

_log = logging.getLogger(__name__)


def ps_table() -> dict[int, tuple[int, str, str]]:
    """pid -> (parent pid, state, command) for every process, read from ps; empty off POSIX."""
    import subprocess as _sp  # noqa: PLC0415
    if os.name != "posix":
        return {}
    try:
        rows = _sp.run(["ps", "-A", "-o", "pid=,ppid=,stat=,command="], capture_output=True,
                       text=True, timeout=5, check=False).stdout
    except (OSError, _sp.SubprocessError):
        return {}
    table = {}
    for row in rows.splitlines():
        parts = row.split(None, 3)
        if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit():
            table[int(parts[0])] = (int(parts[1]), parts[2], parts[3] if len(parts) > 3 else "")
    return table


def descendants(root: int) -> dict[int, str]:
    """Every descendant of root by parent link, so one that left the process group is still found."""
    table, children = ps_table(), {}
    for pid, (ppid, _, _) in table.items():
        children.setdefault(ppid, []).append(pid)
    found, todo = {}, [root]
    while todo:
        for pid in children.get(todo.pop(), []):
            if pid not in found:
                found[pid] = table[pid][2]
                todo.append(pid)
    return found


def live(known: dict[int, str]) -> dict[int, str]:
    """Recorded processes still running the same command (a reused pid is never ours)."""
    table = ps_table()
    return {pid: cmd for pid, cmd in known.items()
            if pid in table and not table[pid][1].startswith("Z") and table[pid][2] == cmd}


def kill_pid(pid: int, sig) -> None:
    try:
        os.kill(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def signal_all(group: int, known: dict[int, str], sig) -> None:
    try:
        os.killpg(group, sig)
    except (ProcessLookupError, PermissionError):
        pass
    for pid in live(known):
        kill_pid(pid, sig)


def report_survivors(known: dict[int, str]) -> None:
    import time as _time  # noqa: PLC0415
    settle = _time.monotonic() + 0.5  # let the killed processes be reaped
    survivors = live(known)
    while survivors and _time.monotonic() < settle:
        _time.sleep(0.05)
        survivors = live(known)
    for pid, cmd in survivors.items():
        _log.warning("model call stop: process %d is still running after the stop: %s", pid, cmd[:300])
