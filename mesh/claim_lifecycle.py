"""How a mesh claim starts and ends on this machine (UNI-2796, review rounds 15-16).

Split out of run_record.py at the 300-line convention. The invariant: from the
moment `run_claim` reports a claim `working`, every way out of it — success,
failure, any exception, even an interrupt — sends one terminal update, removes
the worktree and marks the runner idle, each step running even if the one
before it raised. The single exception is an agent that could not be stopped:
its claim and its worktree are left in place, because the agent is still in it.
"""
from __future__ import annotations

import contextlib
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

REPORT_ATTEMPTS = 3


def worktree_path(linear_id: str, run_id: str) -> Path:
    """Where a run's worktree goes: the platform temp dir, not `/tmp` (RA-7801).

    `/tmp` does not exist on Windows, so the PC's worktree landed in `\\tmp` on
    whatever drive the runner started from."""
    return Path(tempfile.gettempdir()) / f"mesh-{linear_id}-{run_id}"


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


def terminate(proc: subprocess.Popen, grace: float) -> None:
    """Terminate an in-flight agent cleanly, escalating to kill only after `grace` seconds."""
    proc.terminate()
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def deliver(settle: Callable[[], None], plan: dict) -> None:
    """Run RA-7780's ship step. One that raised (a git timeout, an interrupt mid-push) did not
    deliver, so the run fails; an interrupt still propagates after the plan says so."""
    try:
        settle()
    except Exception:  # noqa: BLE001 — the reason stays local; the server gets the closed-set code
        plan.update(state="failed", error_code="runner_exception")
    except BaseException:
        plan.update(state="failed", error_code="runner_exception")
        raise


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


@contextlib.contextmanager
def _sigint_deferred():
    """Hold a Ctrl-C (SIGINT) that arrives while a claim is ending, then raise it.

    Review rounds 12-20 each found one more point where a KeyboardInterrupt cut
    the end of a claim short. A real KeyboardInterrupt only comes from SIGINT, so
    catching the signal for the length of the ending closes the whole class: the
    report, the removal and the idle state all run, then the interrupt is raised.
    Off the main thread a handler cannot be installed, and the ending runs as before.
    """
    caught: list = []
    with sigint_held(caught):
        yield
    if caught:
        raise KeyboardInterrupt


@contextlib.contextmanager
def sigint_held(caught: list):
    """Hold a Ctrl-C (SIGINT) for the block and note it in `caught` instead of raising,
    so the caller can end its claim first and raise after (RA-7798, plan lane).
    Off the main thread a handler cannot be installed, and the block runs unshielded."""
    try:
        previous = signal.signal(signal.SIGINT, lambda *_: caught.append(True))
    except ValueError:
        yield
        return
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, previous)


def end(send: Callable[[], Any], remove: Callable[[], None], idle: Callable[[], None],
        *, agent_alive: bool, pause: float, then: Callable[[], None] = lambda: None,
        first: Callable[[], None] = lambda: None) -> None:
    """End a claim: report it, remove its worktree, mark the runner idle, then run `then`
    (which re-raises an interrupt held while the claim was ending).

    An agent that could not be stopped keeps its claim, its worktree and the
    runner's `working` breadcrumb: reporting the claim terminal would free the
    ticket for another node while this agent still writes to that worktree.
    """
    with _sigint_deferred():
        first()  # RA-7798: recording an unstopped agent is part of the ending, never before it
        if agent_alive:
            print("mesh: the agent could not be stopped; its claim and worktree are left in place",
                  file=sys.stderr)
            return then()
        finish(lambda: report(send, pause), remove, idle, then)
