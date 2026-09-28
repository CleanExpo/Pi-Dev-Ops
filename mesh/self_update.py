"""Runner self-update (RA-7798) — every node runs the code on origin/main.

Nothing moved a node's runtime checkout forward, so after #800 merged all three
runners kept running older code and the fastest one won every claim race on it:
it wrote no run record and stranded RA-7796 In Progress. Each node now
fast-forwards its own runtime while idle and exits so its supervisor relaunches
it on the new code (launchd KeepAlive{SuccessfulExit:false} on the Macs, the
5-minute watchdog trigger on the PC).

Only a clean, detached runtime that main has moved strictly ahead of is ever
touched. A checkout on a branch is somebody's working copy; local edits or a
diverged HEAD mean someone changed it on purpose. Any git failure leaves the
node running what it has.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

RESTART_EXIT = 75  # EX_TEMPFAIL — non-zero, so every supervisor relaunches the runner
INTERVAL_SECONDS = float(os.environ.get("MESH_SELF_UPDATE_INTERVAL", "300"))
ENABLED = os.environ.get("MESH_SELF_UPDATE", "1") != "0"
RUNTIME = Path(__file__).resolve().parents[1]
_last_check = [float("-inf")]


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, timeout=120)


def fast_forward(root: Path) -> str | None:
    """Move a clean, detached checkout to origin/main when that is a fast-forward.

    Returns the new HEAD, or None when nothing moved."""
    try:
        if _git(root, "symbolic-ref", "-q", "HEAD").returncode != 1:  # 0 = on a branch, other = error
            return None
        status = _git(root, "status", "--porcelain", "--untracked-files=no")
        if status.returncode or status.stdout.strip():  # a status that failed proves nothing clean
            return None
        if _git(root, "fetch", "-q", "origin", "main").returncode:
            return None
        head = _git(root, "rev-parse", "HEAD").stdout.strip()
        target = _git(root, "rev-parse", "FETCH_HEAD").stdout.strip()
        if not target or head == target:
            return None
        if _git(root, "merge-base", "--is-ancestor", head, target).returncode:
            return None
        if _git(root, "checkout", "-q", "--detach", target).returncode:
            return None
        return target
    except (OSError, subprocess.SubprocessError):
        return None


def idle_tick(write_state, poll_seconds: float, host: str, *, skip: bool = False) -> bool:
    """Mark the node idle, wait one poll, then update when due. True means restart now."""
    write_state(None, "idle")
    time.sleep(poll_seconds)
    if skip or not ENABLED or time.monotonic() - _last_check[0] < INTERVAL_SECONDS:
        return False
    _last_check[0] = time.monotonic()
    head = fast_forward(RUNTIME)
    if head:
        print(json.dumps({"runner": host, "status": "UPDATED", "head": head}), flush=True)
    return bool(head)
