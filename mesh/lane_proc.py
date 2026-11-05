"""Process facts the lane supervisor needs: is a lane's process still the one it saved (UNI-3291).

A saved pid alone is not enough after a reboot. Windows hands out low pids again, so an
old lane's pid can belong to some new, unrelated process. Each lane therefore saves its
process start time beside its pid, and a process only counts as the lane when both match.

`alive` answers True, False or None. None means "cannot tell" (access denied, an OS
without start times). The supervisor treats None as alive, the safe direction, as
left_running.py does: a lane is relaunched only when its process is PROVEN gone.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import Optional

_STILL_ACTIVE = 259
_QUERY_LIMITED = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION
_ERROR_INVALID_PARAMETER = 87  # OpenProcess on a pid that does not exist
_EPOCH_AS_FILETIME = 116444736000000000  # 1970-01-01 in 100 ns ticks since 1601
# Hidden, own process group, outside the Task Scheduler job so the lane outlives the tick.
_NO_WINDOW, _NEW_GROUP, _BREAKAWAY = 0x08000000, 0x00000200, 0x01000000


def _k32():
    import ctypes
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    k32.GetExitCodeProcess.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong))
    k32.GetProcessTimes.argtypes = (ctypes.c_void_p,) + (ctypes.POINTER(ctypes.c_ulonglong),) * 4
    k32.CloseHandle.argtypes = (ctypes.c_void_p,)
    k32.GetTickCount64.restype = ctypes.c_ulonglong
    return ctypes, k32


def _win_probe(pid: int) -> tuple:
    """(state, start) where state is True running, False gone, None unknown."""
    ctypes, k32 = _k32()
    handle = k32.OpenProcess(_QUERY_LIMITED, False, pid)
    if not handle:
        return (False if k32.GetLastError() == _ERROR_INVALID_PARAMETER else None), None
    try:
        code, times = ctypes.c_ulong(), [ctypes.c_ulonglong() for _ in range(4)]
        if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return None, None
        if code.value != _STILL_ACTIVE:
            return False, None
        ok = k32.GetProcessTimes(handle, *(ctypes.byref(t) for t in times))
        return True, (times[0].value if ok else None)
    finally:
        k32.CloseHandle(handle)


def start_time(pid: int) -> Optional[int]:
    """The process creation time as a Windows FILETIME integer, or None when unknown."""
    if os.name != "nt" or not 0 < pid <= 0xFFFFFFFF:
        return None
    return _win_probe(pid)[1]


def alive(pid: int, started: Optional[int]) -> Optional[bool]:
    """Is `pid` still the process that started at `started`? None means unknown."""
    if not isinstance(pid, int) or pid <= 0:
        return None
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except Exception:  # noqa: BLE001 - EPERM and the like: unknown
            return None
        return None if started is None else True
    state, now_started = _win_probe(pid)
    if state is not True or started is None or now_started is None:
        return state
    return now_started == started  # a different start time is a reused pid: the lane is gone


def boot_epoch() -> float:
    """When this machine last booted, in Unix seconds."""
    if os.name == "nt":
        return time.time() - _k32()[1].GetTickCount64() / 1000.0
    with open("/proc/uptime", encoding="ascii") as f:  # Linux CI; macOS lanes use launchd
        return time.time() - float(f.read().split()[0])


def filetime_to_epoch(ft: int) -> float:
    return (ft - _EPOCH_AS_FILETIME) / 1e7


def spawn(argv: list, cwd: str, env: dict, log_path: str) -> int:
    """Start a lane detached from the caller and return its pid. Never waits for it."""
    log = open(log_path, "ab")
    kw = dict(cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
    try:
        if os.name != "nt":
            return subprocess.Popen(argv, start_new_session=True, **kw).pid
        try:
            return subprocess.Popen(argv, creationflags=_NO_WINDOW | _NEW_GROUP | _BREAKAWAY, **kw).pid
        except OSError:  # the job forbids breakaway: start inside it rather than not at all
            return subprocess.Popen(argv, creationflags=_NO_WINDOW | _NEW_GROUP, **kw).pid
    finally:
        log.close()


def run_quiet(argv: list, stdin_text: str = "", timeout: float = 60) -> tuple:
    """Run a short helper (ssh) with no console window flashing over the operator (#783).
    Returns (exit code, output); a helper that cannot start or times out is exit 127/124."""
    flags = _NO_WINDOW if os.name == "nt" else 0
    try:
        r = subprocess.run(argv, input=stdin_text, capture_output=True, text=True, timeout=timeout,
                           creationflags=flags, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s"
    except OSError as e:
        return 127, str(e)
    return r.returncode, (r.stdout + r.stderr)[-2000:]


if __name__ == "__main__":  # `python lane_proc.py <pid>` prints what the supervisor would see
    p = int(sys.argv[1])
    print({"pid": p, "start_time": start_time(p), "alive": alive(p, start_time(p))})
