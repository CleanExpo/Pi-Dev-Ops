"""How a mesh claim starts and ends on this machine (UNI-2796, review rounds 15-16).

Split out of run_record.py at the 300-line convention. The invariant: from the
moment `run_claim` reports a claim `working`, every way out of it — success,
failure, any exception, even an interrupt — sends one terminal update, removes
the worktree and marks the runner idle, each step running even if the one
before it raised. The single exception is an agent that could not be stopped:
its claim and its worktree are left in place, because the agent is still in it.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

REPORT_ATTEMPTS = 3


def add_worktree(repo_dir: Path, branch: str, worktree: Path) -> bool:
    """`git worktree add -b`; False if git failed or could not start. An interrupt propagates."""
    try:
        added = subprocess.run(
            ["git", "-C", str(repo_dir), "worktree", "add", "-b", branch, str(worktree)],
            capture_output=True, text=True, check=False,
        )
    except Exception:  # noqa: BLE001 — git could not start (OSError) or refused the args (ValueError)
        return False
    return getattr(added, "returncode", 0) == 0


def deliver(settle: Callable[[], None], plan: dict) -> None:
    """Run RA-7780's ship step. One that raised (a git timeout, say) did not deliver, so the run fails."""
    try:
        settle()
    except Exception:  # noqa: BLE001 — the reason stays local; the server gets the closed-set code
        plan.update(state="failed", error_code="runner_exception")


def remove_worktree(repo_dir: Path, worktree: Path) -> None:
    """`git worktree remove --force`, never raising: cleanup failing must not strand the claim.

    Any exception, not only OSError: a claim id with a NUL byte makes subprocess
    raise ValueError before git ever starts.
    """
    try:
        subprocess.run(
            ["git", "-C", str(repo_dir), "worktree", "remove", "--force", str(worktree)],
            capture_output=True, check=False,
        )
    except Exception:  # noqa: BLE001 — cleanup is best-effort; the terminal update is not
        pass


def finish(*steps: Callable[[], Any]) -> None:
    """Run every step in order, even when one raises; a failure propagates only after the last step ran."""
    if not steps:
        return
    try:
        steps[0]()
    finally:
        finish(*steps[1:])


def report(send: Callable[[], Any], pause: float) -> bool:
    """Send the terminal update, retrying one the server rejected; True once it was accepted.

    `_api` never raises for a server-side failure, it returns `{"error": ...}`,
    and the server answers a claim change it could not store with an error
    (review round 16) — so an error reply means the claim is still `working`.
    """
    for attempt in range(REPORT_ATTEMPTS):
        reply = send()
        if not (isinstance(reply, dict) and reply.get("error")):
            return True
        if attempt + 1 < REPORT_ATTEMPTS:
            time.sleep(pause)
    print("mesh: the server did not accept the terminal update; the claim may stay working",
          file=sys.stderr)
    return False


def end(send: Callable[[], Any], remove: Callable[[], None], idle: Callable[[], None],
        *, agent_alive: bool, pause: float, then: Callable[[], None] = lambda: None) -> None:
    """End a claim: report it, remove its worktree, mark the runner idle, then run `then`
    (which re-raises an interrupt held while the claim was ending).

    An agent that could not be stopped keeps its claim, its worktree and the
    runner's `working` breadcrumb: reporting the claim terminal would free the
    ticket for another node while this agent still writes to that worktree.
    """
    if agent_alive:
        print("mesh: the agent could not be stopped; its claim and worktree are left in place",
              file=sys.stderr)
        return then()
    finish(lambda: report(send, pause), remove, idle, then)
