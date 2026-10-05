"""Agents a runner could not stop, remembered across runner restarts (RA-7798).

A runner that cannot prove its agent exited leaves the claim and worktree in place.
Its own process may then end (MAX_CLAIMS, HARD_STOP, crash) and a new one start, so
the record must outlive the process: a small JSON list of pids, plus the agent's
process group (`pgid`) when it had one, so a descendant that outlived an exited agent
still counts (estate audit rank 13). Self-update refuses to move the runtime while any
listed agent or group is alive.

Unknown counts as alive, the safe direction: a missing pid, a pid this user may not
inspect, or a file that exists but cannot be read all block the update. An operator
clears a stuck entry by deleting the file once the agent is known to be gone, and the
`.unrecorded` marker beside it, written when an agent could not be recorded at all.
"""
from __future__ import annotations

import contextlib
import json
import os
import time
from pathlib import Path

PATH = Path(os.environ.get("MESH_LEFT_RUNNING", str(Path.home() / ".claude" / "mesh-left-running.json")))
_STILL_ACTIVE = 259  # Windows GetExitCodeProcess value for a running process
LOCK_SECONDS = 10.0  # a lock held longer than this fails closed, as msvcrt.LK_LOCK does


def _alive_windows(pid: int) -> bool:
    if not 0 < pid <= 0xFFFFFFFF:  # a DWORD pid: OpenProcess would silently ask about a truncated one
        return True
    import ctypes
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = ctypes.c_void_p  # a HANDLE is pointer-sized; the default int truncates it
    k32.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    k32.GetExitCodeProcess.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong))
    k32.CloseHandle.argtypes = (ctypes.c_void_p,)
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


def _group_alive(pgid: int) -> bool:
    """False only when no process is left in the group. Unknown counts as alive."""
    if pgid <= 0 or not hasattr(os, "killpg"):
        return True
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except Exception:  # noqa: BLE001 — EPERM (a zombie on darwin, or someone else's), anything
        return True
    return True


def _entry_alive(entry: tuple) -> bool:
    kind, number = entry
    return _group_alive(number) if kind == "pgid" else _alive(number)


def _load() -> list:
    """The recorded entries as ("pid" | "pgid", number) pairs."""
    if not os.path.lexists(PATH):  # lexists: a dangling link is present, not absent
        return []
    try:
        return [("pgid", int(e["pgid"])) if "pgid" in e else ("pid", int(e["pid"]))
                for e in json.loads(PATH.read_text())]
    except Exception:  # noqa: BLE001 — present but unreadable: unknown, so it blocks
        return [("pid", 0)]


def _save(entries: list) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps([{kind: number} for kind, number in entries]))
    os.replace(tmp, PATH)


@contextlib.contextmanager
def _locked():
    """Serialise every read-modify-write of the record across runner processes: an old and
    a replacement runner can overlap, and an unlocked prune erases a pid tracked meanwhile.
    A lock that cannot be taken raises, and every caller fails closed."""
    PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PATH.with_suffix(".lock"), "a+") as fh:
        if os.name == "nt":
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)  # retries ~10 s, then raises
        else:
            import fcntl
            deadline = time.monotonic() + LOCK_SECONDS
            while True:  # bounded: a holder that never lets go must not hang claim cleanup
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("left-running record lock held elsewhere") from None
                    time.sleep(0.05)
        try:
            yield
        finally:
            if os.name == "nt":
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)  # POSIX: released on close


_UNRECORDED = [False]  # a record this process could not write: block for its lifetime


def _marker() -> Path:
    """Written when an agent could not be recorded; blocks every runner until an operator
    deletes it, once that agent is known to be gone."""
    return PATH.with_suffix(".unrecorded")


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
    pgid = getattr(rec, "pgid", None)
    entries = [("pid", int(getattr(proc, "pid", 0) or 0))]
    if isinstance(pgid, int):  # the agent may have exited while a descendant did not
        entries.append(("pgid", pgid))
    try:
        with _locked():
            _save(_load() + entries)
    except Exception:  # noqa: BLE001 — never raise in claim cleanup; block instead
        _UNRECORDED[0] = True
        try:  # memory dies with this runner; the marker blocks its successors too
            _marker().write_text(str(getattr(proc, "pid", "")))
        except Exception:  # noqa: BLE001 — unwritable here: _writable() blocks the next runner
            pass


def any_alive() -> bool:
    """True while any recorded agent may still be running. Prunes the ones proven gone.
    An unwritable record counts as alive: a relaunched runner could not have seen it."""
    try:
        if _UNRECORDED[0] or not _writable():
            return True
        with _locked():
            pids = _load()
            live = [p for p in pids if _entry_alive(p)]
            if pids and len(live) != len(pids):
                try:
                    _save(live)
                except OSError:
                    pass
            # again last: a track() that failed while this scan ran published only these
            return bool(live) or _UNRECORDED[0] or os.path.lexists(_marker())
    except Exception:  # noqa: BLE001 — an error here proves nothing gone
        return True
