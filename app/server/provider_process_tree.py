"""Process-tree bookkeeping for stopping a model CLI call (UNI-3306).

A stop must leave nothing running. The CLI runs in its own process group, but a descendant
that calls setsid() leaves that group, so every descendant is also recorded by parent link and
stopped by pid. Anything still alive afterwards, and any failure to read the process list, is
logged as a warning; an unreadable list is never treated as an empty one. A process is
identified by pid, start time and command together, so a reused pid is never signalled.
"""
from __future__ import annotations
import logging
import os
import signal
import subprocess
import time

PS = "/bin/ps"
LSOF = "/usr/sbin/lsof"
_log = logging.getLogger(__name__)


def ps_table(timeout_s: float) -> dict[int, tuple[int, str, str]] | None:
    """pid -> (parent pid, state, "start time | command"); None when the list could not be read."""
    if os.name != "posix":
        return {}
    try:
        res = subprocess.run([PS, "-A", "-o", "pid=,ppid=,stat=,lstart=,command="], capture_output=True,
                             text=True, timeout=max(0.05, timeout_s), check=False,
                             env={**os.environ, "LC_ALL": "C", "TZ": "UTC"})
    except (OSError, subprocess.SubprocessError):
        return None
    table = {}
    for row in res.stdout.splitlines() if res.returncode == 0 else ():
        parts = row.split(None, 8)  # lstart is five words: "Sun Nov  8 14:00:01 2026"
        if len(parts) >= 8 and parts[0].isdigit() and parts[1].isdigit():
            ident = " ".join(parts[3:8]) + " | " + (parts[8] if len(parts) > 8 else "")
            table[int(parts[0])] = (int(parts[1]), parts[2], ident)
    return table or None  # a readable list always holds at least this process


def descendants(root: int, timeout_s: float) -> dict[int, str] | None:
    """Every descendant of root by parent link, so one that left the process group is still found."""
    table = ps_table(timeout_s)
    if table is None:
        return None
    children: dict[int, list[int]] = {}
    for pid, (ppid, _, _) in table.items():
        children.setdefault(ppid, []).append(pid)
    found, todo = {}, [root]
    while todo:
        for pid in children.get(todo.pop(), []):
            if pid not in found:
                found[pid] = table[pid][2]
                todo.append(pid)
    return found


def live(known: dict[int, str], timeout_s: float) -> dict[int, str] | None:
    """Recorded processes still alive with the same start time and command (a reused pid is never ours)."""
    table = ps_table(timeout_s)
    if table is None:
        return None
    return {pid: cmd for pid, cmd in known.items()
            if pid in table and not table[pid][1].startswith("Z") and table[pid][2] == cmd}


def pipe_holders(fds, timeout_s: float) -> dict[int, str] | None:
    """Processes holding the other end of our output pipes, found even after they were reparented.

    A child that calls setsid() and outlives the CLI is no longer a descendant by parent link,
    but it still holds the call's stdout/stderr; lsof finds it by the pipe's address. When the
    process list cannot be read, a holder is returned with an empty identity. It is never
    signalled (its pid may already belong to another process); the warning names it instead.
    """
    me = os.getpid()
    ends = set()
    for fd in fds:
        own = _lsof(["-a", "-p", str(me), "-d", str(fd)], timeout_s)
        if own is None:
            return None
        ends |= {v for _, kind, v in own if kind in ("d", "n->")}
    rows = _lsof(["-u", str(os.getuid())], timeout_s)
    if rows is None or not ends:
        return None
    pids = {pid for pid, kind, v in rows if pid != me and v in ends}
    table = ps_table(timeout_s)
    if table is None:
        return dict.fromkeys(pids, "")
    return {pid: table[pid][2] for pid in pids if pid in table}


def _lsof(args, timeout_s: float) -> list[tuple[int, str, str]] | None:
    """(pid, 'd' or 'n->', pipe address) rows from lsof -F pdn; None when lsof failed."""
    try:
        res = subprocess.run([LSOF, "-nP", *args, "-F", "pdn"], capture_output=True, text=True,
                             timeout=max(0.05, timeout_s), check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode not in (0, 1) or not res.stdout:
        return None
    rows, pid = [], 0
    for line in res.stdout.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pid = int(line[1:])
        elif line.startswith("d0x"):
            rows.append((pid, "d", line[1:]))
        elif line.startswith("n->0x"):
            rows.append((pid, "n->", line[3:]))
    return rows


def kill_pid(pid: int, sig) -> None:
    try:
        os.kill(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _signal(group: int, pids, sig) -> None:
    try:
        os.killpg(group, sig)
    except (ProcessLookupError, PermissionError):
        pass
    for pid in pids:
        kill_pid(pid, sig)


def stop_tree(proc, known: dict[int, str], *, budget_s: float, grace_s: float, fds=()) -> None:
    """Freeze the group, record the tree, then end the group and every recorded descendant.

    Every step shares one deadline, so a slow or missing ps cannot stretch the stop.
    """
    end = time.monotonic() + budget_s

    def left(cap: float) -> float:
        return max(0.05, min(cap, end - time.monotonic()))

    pids: list[int] = []
    unnamed: list[int] = []
    found = holders = targets = None
    try:
        _signal(proc.pid, (), signal.SIGSTOP)  # nothing in the group exits or spawns while it is read
        found = descendants(proc.pid, left(0.75))
        holders = pipe_holders(fds, left(0.75)) if fds else {}
        unnamed = [pid for pid, ident in (holders or {}).items() if not ident]
        known = {**known, **(found or {}), **(holders or {})}
        targets = live(known, left(0.75))
        pids = list(targets or {})  # only processes identified by pid, start time and command
        _signal(proc.pid, pids, signal.SIGTERM)
        _signal(proc.pid, pids, signal.SIGCONT)
        try:
            proc.wait(timeout=left(grace_s))
        except subprocess.TimeoutExpired:
            pass
    finally:
        _signal(proc.pid, pids, signal.SIGKILL)  # children can outlive a parent that exited
    _report(known, found is None or holders is None or targets is None or bool(unnamed), left)


def _report(known: dict[int, str], unreadable: bool, left) -> None:
    survivors = live(known, left(0.5))
    settle = time.monotonic() + left(0.5)  # let the killed processes be reaped
    while survivors and time.monotonic() < settle:
        time.sleep(0.05)
        survivors = live(known, left(0.5))
    if unreadable or survivors is None:
        _log.warning("model call stop: the process list could not be read; a process outside the "
                     "group may still be running. Recorded: %s",
                     "; ".join(f"process {p}: {c[:200] or 'command unknown'}" for p, c in known.items()) or "none")
    for pid, cmd in (survivors or {}).items():
        _log.warning("model call stop: process %d is still running after the stop: %s", pid, cmd[:300])
