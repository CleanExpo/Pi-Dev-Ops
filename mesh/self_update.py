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

import left_running

RESTART_EXIT = 75  # EX_TEMPFAIL — non-zero, so every supervisor relaunches the runner
INTERVAL_SECONDS = float(os.environ.get("MESH_SELF_UPDATE_INTERVAL", "300"))
ENABLED = os.environ.get("MESH_SELF_UPDATE", "1") != "0"
RUNTIME = Path(__file__).resolve().parents[1]
_MAIN_REF = "refs/mesh-self-update/main"  # written only by this module
_last_check = [float("-inf")]


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, timeout=120)


def _clean(root: Path) -> bool:
    """Tracked tree unmodified. A status that failed proves nothing clean."""
    status = _git(root, "status", "--porcelain", "--untracked-files=no")
    return status.returncode == 0 and not status.stdout.strip()


def fast_forward(root: Path, may_move=None) -> str | None:
    """Move a clean, detached checkout to origin/main when that is a fast-forward.

    Returns the new HEAD, or None when nothing moved. Cleanliness is checked again
    after the fetch, which can take seconds, so an edit made meanwhile blocks the move."""
    try:
        if _git(root, "symbolic-ref", "-q", "HEAD").returncode != 1:  # 0 = on a branch, other = error
            return None
        if not _clean(root):
            return None
        # A private ref, not FETCH_HEAD: a concurrent fetch of another branch overwrites FETCH_HEAD.
        if _git(root, "fetch", "-q", "origin", f"+refs/heads/main:{_MAIN_REF}").returncode:
            return None
        head = _git(root, "rev-parse", "HEAD").stdout.strip()
        target = _git(root, "rev-parse", "--verify", "-q", f"{_MAIN_REF}^{{commit}}").stdout.strip()
        if not target or head == target:
            return None
        if _git(root, "merge-base", "--is-ancestor", head, target).returncode:
            return None
        if not _clean(root) or (may_move and not may_move()):  # asked only when a move is due
            return None
        if _git(root, "checkout", "-q", "--detach", target).returncode:
            return None
        return target
    except Exception:  # noqa: BLE001 — an update attempt must never take the runner down
        return None


def update_now(host: str, may_move=None) -> bool:
    """Fast-forward the runtime now. True means it moved and the runner must restart.

    Also run at startup, so a runner relaunched after its MAX_CLAIMS stop (a
    deliberate cost cap) never claims work on stale code. `may_move` vetoes the
    move, e.g. while an agent of this node may still be running."""
    if not ENABLED:
        return False
    _last_check[0] = time.monotonic()
    head = fast_forward(RUNTIME, lambda: not left_running.any_alive() and (may_move is None or may_move()))
    if head:
        print(json.dumps({"runner": host, "status": "UPDATED", "head": head}), flush=True)
    return bool(head)


def idle_tick(write_state, poll_seconds: float, host: str, *, skip: bool = False) -> bool:
    """Mark the node idle, wait one poll, then update when due. True means restart now."""
    write_state(None, "idle")
    time.sleep(poll_seconds)
    if skip or time.monotonic() - _last_check[0] < INTERVAL_SECONDS:
        return False
    return update_now(host)
