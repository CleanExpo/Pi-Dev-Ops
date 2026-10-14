"""How a mesh claim starts and ends on this machine (UNI-2796, review rounds 15-16).

Split out of run_record.py at the 300-line convention. The invariant: from the
moment `run_claim` reports a claim `working`, every way out of it — success,
failure, any exception, even an interrupt — ends in one of two states, and the
runner is marked idle either way, each step running even if the one before it raised:

  * ended: the work is kept, the worktree is removed, and only then the terminal
    update is sent and the run journal cleared;
  * held (UNI-2963): the work could not be kept, the worktree would not go, an agent
    could not be stopped, or the server refused the update. Nothing terminal is sent
    over a worktree still on disk; the claim stays `working`, and the run journal,
    which carries the intended terminal update, lets `run_journal.Ticker` finish it later.
"""
from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

REPORT_ATTEMPTS = 3
GIT_TIMEOUT = 120  # seconds; the same bound ship_run puts on every git call


def temp_root() -> Path:
    """The platform temp dir under its long, real name (RA-7801).

    A scheduled task on Windows can get TEMP as an 8.3 short path
    (`C:\\Users\\DISAST~1\\...`). Claude matches workspace trust on the long
    path, so an agent started under the short one reads as untrusted."""
    return Path(os.path.realpath(tempfile.gettempdir()))


def worktree_path(linear_id: str, run_id: str) -> Path:
    """Where a run's worktree goes: the platform temp dir, not `/tmp` (RA-7801).

    `/tmp` does not exist on Windows, so the PC's worktree landed in `\\tmp` on
    whatever drive the runner started from."""
    return temp_root() / f"mesh-{linear_id}-{run_id}"


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


def remove_worktree(repo_dir: Path, worktree: Path) -> bool:
    """`git worktree remove --force`, never raising: cleanup failing must not strand the claim.

    Any exception, not only OSError: a claim id with a NUL byte makes subprocess
    raise ValueError before git ever starts. Bounded by GIT_TIMEOUT (UNI-2963 r3): the poll
    loop's reconcile calls this, and a hung git must not stall the runner; a timed-out remove
    leaves the path, so it reads as not removed.
    """
    try:
        subprocess.run(
            ["git", "-C", str(repo_dir), "worktree", "remove", "--force", str(worktree)],
            capture_output=True, check=False, timeout=GIT_TIMEOUT,
        )
    except Exception:  # noqa: BLE001 — cleanup is best-effort; the terminal update is not
        pass
    return not os.path.lexists(worktree)  # UNI-2963 r2: True only once nothing is left there


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


class SigintHold:
    """Hold Ctrl-C (SIGINT) from construction until `restore` (UNI-2963 review r5). run_claim
    starts one as the first thing in its finally, so an interrupt landing before end() begins
    is held too instead of skipping the ending. Off the main thread nothing can be installed."""

    def __init__(self):
        self.caught: list = []
        try:
            self._previous, self.active = signal.signal(signal.SIGINT, lambda *_: self.caught.append(True)), True
        except ValueError:
            self.active = False

    def restore(self) -> None:
        if self.active:
            signal.signal(signal.SIGINT, self._previous)
            self.active = False

    def __enter__(self) -> "SigintHold":
        return self

    def __exit__(self, exc_type, *_exc) -> None:
        """Always restore, even when end() never ran; raise a held Ctrl-C nobody raised yet."""
        self.restore()
        if self.caught and exc_type is None:
            self.caught.clear()
            raise KeyboardInterrupt


@contextlib.contextmanager
def _sigint_deferred(hold: "SigintHold | None" = None):
    """Hold a Ctrl-C (SIGINT) that arrives while a claim is ending, then raise it.

    Review rounds 12-20 each found one more point where a KeyboardInterrupt cut
    the end of a claim short. A real KeyboardInterrupt only comes from SIGINT, so
    catching the signal for the length of the ending closes the whole class: the
    report, the removal and the idle state all run, then the interrupt is raised.
    Off the main thread a handler cannot be installed, and the ending runs as before.
    """
    hold = hold if hold is not None else SigintHold()
    try:
        yield
    finally:
        hold.restore()
    if hold.caught:
        hold.caught.clear()  # raised once, here; the runner's `with` must not raise it again
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
        first: Callable[[], None] = lambda: None, preserve: Callable[[], Any] = lambda: None,
        forget: Callable[[], None] = lambda: None, held: "SigintHold | None" = None) -> None:
    """End a claim: keep its uncommitted work (`preserve`), remove its worktree, report it
    terminal only once `remove` returned True (UNI-2963 review r3: never a finished claim
    over a worktree still on disk), `forget` its run journal once the report was accepted,
    mark the runner idle, then run `then` (which re-raises an interrupt held while the
    claim was ending). A step that did not succeed holds everything after it except idle.

    An agent that could not be stopped keeps its claim, its worktree, its journal and the
    runner's `working` breadcrumb: reporting the claim terminal would free the
    ticket for another node while this agent still writes to that worktree.
    """
    with _sigint_deferred(held):
        first()  # RA-7798: recording an unstopped agent is part of the ending, never before it
        if agent_alive:
            print("mesh: the agent could not be stopped; its claim and worktree are left in place",
                  file=sys.stderr)
            return then()
        # UNI-2963: `preserve` returns None once the work is kept, `remove` True once the
        # worktree is gone. Anything else (an error, or an interrupt) sends nothing and keeps
        # the journal for the poll loop's retry (reviews r1-r3).
        kept: list = []
        gone: list = []
        sent: list = []
        finish(lambda: kept.append(preserve()),
               lambda: gone.append(remove()) if kept == [None] else _hold(kept),
               lambda: sent.append(report(send, pause)) if gone == [True] else _held_by(kept, gone),
               lambda: forget() if sent == [True] else None, idle, then)


def _held_by(kept: list, gone: list) -> None:
    if kept != [None]:
        return  # the work was not kept, and _hold already said so
    why = "would not go" if gone else "removal raised"  # r4: a raised removal is logged too
    print(f"mesh: the worktree {why}; its claim stays working and its journal is kept",
          file=sys.stderr)


def _hold(kept: list) -> None:
    print(f"mesh: the run's work could not be kept ({kept[0] if kept else 'interrupted'}); "
          "its claim, worktree and journal are left in place", file=sys.stderr)
