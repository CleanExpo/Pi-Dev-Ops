"""Agents a runner could not stop, remembered across runner restarts (RA-7798).

A runner that cannot prove its agent exited leaves the claim and worktree in place.
Its own process may then end (MAX_CLAIMS, HARD_STOP, crash) and a new one start, so
the record must outlive the process: a small JSON list of pids. Self-update refuses
to move the runtime while any listed agent is alive.

Unknown counts as alive, the safe direction: a missing pid, a pid this user may not
inspect, or a file that exists but cannot be read all block the update. An operator
clears a stuck entry by deleting the file once the agent is known to be gone.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

PATH = Path(os.environ.get("MESH_LEFT_RUNNING", str(Path.home() / ".claude" / "mesh-left-running.json")))
_STILL_ACTIVE = 259  # Windows GetExitCodeProcess value for a running process


def _alive_windows(pid: int) -> bool:
    import ctypes
    k32 = ctypes.windll.kernel32
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return k32.GetLastError() != 87  # ERROR_INVALID_PARAMETER: no such process
    code = ctypes.c_ulong()
    ok = k32.GetExitCodeProcess(handle, ctypes.byref(code))
    k32.CloseHandle(handle)
    return not ok or code.value == _STILL_ACTIVE


def _alive(pid: int) -> bool:
    if pid <= 0:
        return True
    if os.name == "nt":
        return _alive_windows(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True  # e.g. EPERM: it exists, owned by someone else
    return True


def _load() -> list:
    if not PATH.exists():
        return []
    try:
        return [int(e["pid"]) for e in json.loads(PATH.read_text())]
    except (OSError, ValueError, KeyError, TypeError):
        return [0]  # present but unreadable: unknown, so it blocks


def _save(pids: list) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps([{"pid": p} for p in pids]))
    os.replace(tmp, PATH)


def track(rec) -> None:
    """Record an agent whose stop could not be proven (`reaped is False`)."""
    if rec is None or getattr(rec, "reaped", None) is not False:
        return
    proc = getattr(rec, "proc", None)
    _save(_load() + [int(getattr(proc, "pid", 0) or 0)])


def any_alive() -> bool:
    """True while any recorded agent may still be running. Prunes the ones proven gone."""
    pids = _load()
    live = [p for p in pids if _alive(p)]
    if pids and len(live) != len(pids):
        try:
            _save(live)
        except OSError:
            pass
    return bool(live)
