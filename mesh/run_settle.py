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
import sys
from pathlib import Path
from typing import Any, Callable, Optional

_TERMINAL = ("done", "failed", "released")
_IDENTITY = ("linear_id", "claim_id", "host", "branch")


class Outcome:
    """A run's terminal update, built once, sent by the ending and journaled before cleanup."""

    def __init__(self, beat: Any, build: Callable[[], dict]):
        self._beat, self._build, self._payload = beat, build, None

    def __call__(self) -> dict:
        if self._payload is None:
            self._payload = self._build()
        return self._payload

    def record(self) -> None:
        """Journal the payload before cleanup. A failed write is reported, never raised: the
        ending then still sends the update itself if its worktree goes."""
        if not self._beat.note(outcome=self()):
            print(f"mesh: run {self._beat.run_id} could not journal its terminal update; "
                  "a held ending would settle as a plain release", file=sys.stderr)


def replay(entry: dict) -> Optional[dict]:
    """The journaled terminal update, if it is one and belongs to this very claim, else None."""
    sent = entry.get("outcome")
    if not isinstance(sent, dict) or sent.get("state") not in _TERMINAL:
        return None
    return sent if all(sent.get(k) == entry.get(k) for k in _IDENTITY) else None


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
