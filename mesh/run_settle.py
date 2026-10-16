"""What a held mesh run settles WITH, split out of run_journal.py at the 300-line convention (UNI-2963).

Review r4: when a run's ending is held (its worktree would not go, or the server refused
the update), the journal's later settlement used to post a bare `released`. The server
then put a `done` run, whose work was already pushed, back in the queue for a second
delivery; dropped a `failed` run's Linear comment and skip window; and lost a quota
release's `agent_quota`. So the ending journals the terminal update it intends to send
(`Outcome.record`) BEFORE any cleanup, and settlement sends that exact update
(`replay`). A bare `released` is only for a run that recorded nothing: one killed
before its ending began.
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Optional

_TERMINAL = ("done", "failed", "released")
_IDENTITY = ("linear_id", "claim_id", "host", "branch", "run_id")
_KEYS = _IDENTITY + ("state", "duration_s", "exit_code", "error_code")  # r5: nothing else is replayed
# r5: outcomes this process knows but could not journal, by run id. Settlement in the same
# runner (the Ticker) sends them; a runner that died with one pending leaves `ending` in its
# journal, and that journal is held, never released bare.
PENDING: dict = {}
# r6/r7: runs for which this process PROVED that no agent process exists (see no_agent). Only
# with this proof, and only for its own journal with a PENDING outcome, does the runner settle a
# journal that names no agent pid; every other such journal holds, as does every journal after a
# restart, when this memory is gone.
NEVER_LAUNCHED: set = set()


def no_agent(held: list) -> bool:
    """True only when the run's own RunRecord proves no agent process exists (review r7). One rule
    for every path out of run_agent, taken once, in the ending:

      * no RunRecord at all: run_agent was never called (worktree add failed, or anything
        before it) or could not build one, so Popen never ran;
      * a RunRecord without a process: building the command raised (the `launching` write,
        the prompt, the argv) or Popen raised an Exception, and Popen reaps a child that
        failed to exec;
      * a process that stop() proved gone, its whole group included (`reaped` True).

    An interrupt inside Popen (`unseen_agent`) may have left a child nobody saw: never proof."""
    rec = held[0] if held else None
    if rec is None:
        return True
    if getattr(rec, "proc", None) is not None:  # r10: a saved handle is proof only once stop() reaped it,
        return getattr(rec, "reaped", None) is True  # even if its start was interrupted (unseen_agent)
    return not getattr(rec, "unseen_agent", False)  # no handle: proof unless a child may exist unseen


# Journal file I/O, moved here from run_journal.py (which re-exports it) at the 300-line limit.
def path(base_dir: Path, run_id: str) -> Path:
    return Path(base_dir) / "mesh-runs" / f"{run_id}.json"


def write(base_dir: Path, run_id: str, entry: dict) -> bool:
    """Replace the journal atomically, owner-only. Never raises; False means not written."""
    target = path(base_dir, run_id)
    tmp = target.with_name(f".{run_id}.json.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(entry))
            fh.flush()
            os.fsync(fh.fileno())  # r4: the bytes, then the rename, must survive a power cut
        os.replace(tmp, target)
        _fsync_dir(target.parent)
        return True
    except Exception:  # noqa: BLE001 — any failure, including a planted link at tmp
        return False


def _fsync_dir(directory: Path) -> None:
    """Make the rename durable; raising when it cannot (r5: unsynced is not written). Windows
    cannot open a directory at all, so there the replace stands alone."""
    if os.name == "nt":
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def clear(base_dir: Path, run_id: str) -> None:
    try:
        path(base_dir, run_id).unlink(missing_ok=True)
    except OSError:
        pass


class Outcome:
    """A run's terminal update, built once, sent by the ending and journaled before cleanup."""

    def __init__(self, beat: Any, build: Callable[[], dict]):
        self._beat, self._build, self._payload = beat, build, None

    def __call__(self) -> dict:
        if self._payload is None:
            self._payload = self._build()
        return self._payload

    def record(self) -> Optional[str]:
        """Journal that the ending began, then its payload, before any cleanup. None once both
        are on disk; otherwise why not, which holds the whole ending (review r5): no removal,
        no report. The payload stays in PENDING so this runner's Ticker can still send it."""
        payload = self()
        PENDING[self._beat.run_id] = payload
        if no_agent(self._beat.held):  # r7: the one place the no-agent proof is taken
            NEVER_LAUNCHED.add(self._beat.run_id)
        if self._beat.note(ending=True) and self._beat.note(outcome=payload):
            return None
        print(f"mesh: run {self._beat.run_id} could not journal its terminal update; "
              "its ending is held", file=sys.stderr)
        return "terminal update not journaled"


def replay(entry: dict) -> Optional[dict]:
    """The journaled terminal update, if it is one and belongs to this very claim, else None."""
    sent = entry.get("outcome")
    if not isinstance(sent, dict) or sent.get("state") not in _TERMINAL:
        return None
    if not all(sent.get(k) == entry.get(k) for k in _IDENTITY):
        return None
    return {k: sent[k] for k in _KEYS if k in sent}


@contextlib.contextmanager
def settling(journal: Path):
    """Yield True while this process alone holds the journal's settlement lock, else False."""
    try:
        import fcntl
    except ImportError:  # no flock (Windows): such journals hold anyway, having no process group
        yield False
        return
    with open(journal.with_suffix(".lock"), "a+") as fh:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        yield True
