"""Should this node take work right now? Preflight gate plus circuit breaker (RA-7802).

Before this, a runner claimed work whether or not it could do any. On 28/09 the
Mini claimed tickets with an agent that could not write files, and the PC claimed
tickets with a runner that raised before the agent started. Each failed, and each
kept claiming, one ticket every few seconds, because nothing counted failures.

`NodeHealth` holds two rules:
  * a node claims nothing until `preflight()` passes — the node proves on its own
    OS, with its own agent and its own permissions, that it can do a run;
  * `FAILURE_LIMIT` failed claims in a row quarantine the node. It claims nothing
    until preflight passes again, re-checked every `RECHECK_SECONDS`.
A blocked or quarantined node says so in its heartbeat, so the fleet view shows
it instead of it quietly burning the queue.
"""
from __future__ import annotations

import os
import time
from typing import Callable

FAILURE_LIMIT = int(os.environ.get("MESH_FAILURE_LIMIT", "2"))
RECHECK_SECONDS = float(os.environ.get("MESH_HEALTH_RECHECK_SECONDS", "600"))


class NodeHealth:
    """Tracks whether this node may claim. `preflight()` returns "" or the problem."""

    def __init__(self, preflight: Callable[[], str], clock: Callable[[], float] = time.monotonic,
                 limit: int = FAILURE_LIMIT, recheck: float = RECHECK_SECONDS):
        self._preflight = preflight
        self._clock = clock
        self._limit = max(1, limit)
        self._recheck = recheck
        self._checked_at: float | None = None
        self.failures = 0
        self.state = "unchecked"   # unchecked | healthy | blocked | quarantined
        self.reason = ""

    def may_claim(self) -> bool:
        """True when the node is healthy. Runs preflight first time, then again only
        once RECHECK_SECONDS have passed since a node went blocked or quarantined."""
        if self.state == "healthy":
            return True
        due = self._checked_at is None or self._clock() - self._checked_at >= self._recheck
        if not due:
            return False
        problem = self._run_preflight()
        self._checked_at = self._clock()
        if problem:
            self.state, self.reason = "blocked", problem
            return False
        self.state, self.reason, self.failures = "healthy", "", 0
        return True

    def record(self, results: list[dict]) -> None:
        """Count consecutive failed claims; a delivered one resets the count."""
        for result in results:
            if result.get("state") == "failed":
                self.failures += 1
                self.reason = result.get("error_code") or "failed"
            elif result.get("state") == "done":
                self.failures = 0
        if self.failures >= self._limit:
            self.state = "quarantined"
            self.reason = f"{self.failures} failed claims in a row, last: {self.reason}"
            self._checked_at = self._clock()

    def _run_preflight(self) -> str:
        """A preflight that raises is a failed preflight, never a pass."""
        try:
            return self._preflight() or ""
        except Exception as exc:  # noqa: BLE001 — any crash means the node is not proven
            return f"preflight raised {type(exc).__name__}"
