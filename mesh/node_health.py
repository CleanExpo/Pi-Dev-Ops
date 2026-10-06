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

A third hold, `quota` (RA-7930): the agent's account is out of quota. It is not
the node's fault or the ticket's, so it never counts toward FAILURE_LIMIT; the
node claims nothing until the reset `quota.py` read, then preflight runs again.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import quota  # noqa: E402

FAILURE_LIMIT = int(os.environ.get("MESH_FAILURE_LIMIT", "2"))
RECHECK_SECONDS = float(os.environ.get("MESH_HEALTH_RECHECK_SECONDS", "600"))


class NodeHealth:
    """Tracks whether this node may claim. `preflight()` returns "" or the problem."""

    def __init__(self, preflight: Callable[[], str], clock: Callable[[], float] = time.monotonic,
                 limit: int = FAILURE_LIMIT, recheck: float = RECHECK_SECONDS,
                 wall: Callable[[], float] = time.time):
        self._preflight = preflight
        self._clock = clock
        self._wall = wall  # a quota resets at a wall-clock time
        self.quota_until: float | None = None
        self._limit = max(1, limit)
        self._recheck = recheck
        self._checked_at: float | None = None
        self.failures = 0
        self.state = "unchecked"   # unchecked | healthy | blocked | quarantined | quota
        self.reason = ""

    def may_claim(self) -> bool:
        """True when the node is healthy. Runs preflight first time, then again only
        once RECHECK_SECONDS have passed since a node went blocked or quarantined, or
        once the quota a `quota` hold waits on has reset."""
        if self.state == "healthy":
            return True
        if self.state == "quota":
            due = self._wall() >= (self.quota_until or 0)
        else:
            due = self._checked_at is None or self._clock() - self._checked_at >= self._recheck
        if not due:
            return False
        problem = self._run_preflight()
        self._checked_at = self._clock()
        if until := quota.held_until(problem):
            self.hold_quota(until)
            return False
        if problem:
            self.state, self.reason = "blocked", problem
            return False
        self.state, self.reason, self.failures, self.quota_until = "healthy", "", 0, None
        return True

    def hold_quota(self, until: float) -> None:
        """Claim nothing until `until` (epoch seconds), then prove the node with preflight."""
        self.state, self.quota_until, self.reason = "quota", until, quota.problem(until)

    def record(self, results: list[dict]) -> None:
        """Count consecutive failed claims; a delivered one resets the count."""
        for result in results:
            if result.get("quota_until"):  # released, not failed: the account's fault, not the ticket's
                self.hold_quota(result["quota_until"])
            elif result.get("state") == "failed":
                self.failures += 1
                self.reason = result.get("error_code") or "failed"
            elif result.get("state") == "done":
                self.failures = 0
        if self.state != "quota" and self.failures >= self._limit:
            self.state = "quarantined"
            self.reason = f"{self.failures} failed claims in a row, last: {self.reason}"
            self._checked_at = self._clock()

    def run_batch(self, work: list[dict], run: Callable[[dict], dict],
                  release: Callable[[dict], object]) -> list[dict]:
        """Run claims one at a time, counting each as it ends. Once the node is
        quarantined or out of quota, the rest of the batch is handed back unrun, not failed one by one."""
        results: list[dict] = []
        for n, claim in enumerate(work):
            if self.state in ("quarantined", "quota"):
                for rest in work[n:]:
                    release(rest)
                break
            results.append(run(claim))
            self.record(results[-1:])
        return results

    def _run_preflight(self) -> str:
        """A preflight that raises is a failed preflight, never a pass."""
        try:
            return self._preflight() or ""
        except Exception as exc:  # noqa: BLE001 — any crash means the node is not proven
            return f"preflight raised {type(exc).__name__}"


# A runner idle longer than this has stopped polling: the Mac mini runner sat dead
# for days in October 2026 while its heartbeat kept the node "online".
RUNNER_STALE_S = float(os.environ.get("MESH_RUNNER_STALE_S", "900"))


def runner_down(breadcrumb_path: str, agents: list, now: Callable[[], float] = time.time) -> bool:
    """True when this node's runner breadcrumb stopped updating.

    The runner rewrites it on every poll but only once at the start of a build, so
    an old "working" breadcrumb with a live agent session is a long build, not a
    dead runner. No readable breadcrumb means no runner on this node: not down."""
    try:
        with open(breadcrumb_path) as f:
            data = json.loads(f.read())
        age = now() - float(data.get("ts") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return False
    if age <= RUNNER_STALE_S:
        return False
    return not (data.get("state") == "working" and agents)
