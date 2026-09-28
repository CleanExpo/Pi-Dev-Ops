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
    """False only when the process is proven gone. Anything else, including a pid the OS
    cannot even represent, is unknown and counts as alive."""
    if pid <= 0:
        return True
    try:
        if os.name == "nt":
            return _alive_windows(pid)
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except Exception:  # noqa: BLE001 — EPERM (someone else's), OverflowError, anything
        return True
    return True


def _load() -> list:
    if not os.path.lexists(PATH):  # lexists: a dangling link is present, not absent
        return []
    try:
        return [int(e["pid"]) for e in json.loads(PATH.read_text())]
    except Exception:  # noqa: BLE001 — present but unreadable: unknown, so it blocks
        return [0]


def _save(pids: list) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps([{"pid": p} for p in pids]))
    os.replace(tmp, PATH)


_UNRECORDED = [False]  # a record this process could not write: block for its lifetime


def _writable() -> bool:
    """The record can be written here; if not, its absence proves nothing."""
    probe = PATH.with_suffix(".probe")
    try:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("")
        probe.unlink()
        return True
    except OSError:
        return False


def track(rec) -> None:
    """Record an agent whose stop could not be proven (`reaped is False`). Never raises:
    it runs in the claim's cleanup path, which must still end the claim."""
    if rec is None or getattr(rec, "reaped", None) is not False:
        return
    proc = getattr(rec, "proc", None)
    try:
        _save(_load() + [int(getattr(proc, "pid", 0) or 0)])
    except Exception:  # noqa: BLE001 — never raise in claim cleanup; block instead
        _UNRECORDED[0] = True


def any_alive() -> bool:
    """True while any recorded agent may still be running. Prunes the ones proven gone.
    An unwritable record counts as alive: a relaunched runner could not have seen it."""
    try:
        if _UNRECORDED[0] or not _writable():
            return True
        pids = _load()
        live = [p for p in pids if _alive(p)]
        if pids and len(live) != len(pids):
            try:
                _save(live)
            except OSError:
                pass
        return bool(live)
    except Exception:  # noqa: BLE001 — an error here proves nothing gone
        return True
