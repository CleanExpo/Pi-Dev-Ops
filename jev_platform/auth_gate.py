"""The auth gate: one bad Jev key must cost one request, however many workers share it.

Used by every dispatcher that can run requests in parallel (client.send, the constitution harness).
Sequential dispatchers (scripts/jev_triage.py, scripts/mission_control_jev_shadow.py main, evals/skill_routing/run.py)
never have two requests in flight and stop at their first 401/403; src/tao/skill_router.py and
app/server/skill_routing.py send one request per routing call and are not batch loops.

Outcome of a transmitted request -> gate transition (`outcome()` is the single place this is decided):

    real HTTP status 2xx / 3xx / non-auth 4xx / 429 / 5xx   key proven: the canary opens, workers run in parallel
    401, 403                                                 halt: published under the state lock BEFORE any ledger I/O
    no HTTP response (status 0, None, non-integer status,    gate stays closed: the next request is still the canary
      URLError, timeout, malformed body, any exception)

Admission is one critical section under the same lock as publication: no request is ADMITTED after a refusal is
published. Requests admitted before it may still finish (at most workers-1, and only after the canary has proven the
key once). A request that is not admitted is settled "not_sent" at 0.0: nothing left the machine.
"""
from __future__ import annotations

import contextlib
import threading

from jev_platform import spend

REFUSED = (401, 403)  # the key is refused: every later call would be refused too (billing for it is unproven)


def outcome(status) -> str:
    """'refused', 'proven' or 'none' for the status a transport reported."""
    if isinstance(status, bool) or not isinstance(status, int):
        return "none"
    if status in REFUSED:
        return "refused"
    return "proven" if 100 <= status <= 599 else "none"


class AuthGate:
    def __init__(self) -> None:
        self.halted: str | None = None  # the error every later call returns unsent
        self.canary_done = False
        self.admitted = 0  # requests admitted for transmission (instrumentation for the contract above)
        self._canary, self._state = threading.Lock(), threading.Lock()

    @contextlib.contextmanager
    def dispatch(self):
        """Until the key is proven, hold the canary lock across the request: exactly one request is sent."""
        held = False
        if not self.canary_done:
            self._canary.acquire()
            held = True
            if self.canary_done:  # another worker's canary finished while this one waited
                self._canary.release()
                held = False
        try:
            yield
        finally:
            if held:
                self._canary.release()

    def check(self) -> str | None:
        with self._state:
            return self.halted

    def refused(self, reason: str) -> None:
        with self._state:
            self.halted = self.halted or reason

    def answered(self) -> None:
        self.canary_done = True

    def admit(self) -> str | None:
        """None and the request is counted as admitted, or the published refusal."""
        with self._state:
            if self.halted:
                return self.halted
            self.admitted += 1
            return None

    def transmit(self, row: int, call, call_id: str | None = None):
        """Admit, send, publish. Returns (halted_reason, result): reason set means nothing was sent.

        `call()` returns a tuple whose first item is the HTTP status (0 when there was no HTTP response); an
        exception from it propagates (the request was admitted, the gate stays as it was). Pass the call id from
        spend.reserve_call so the unsent row is settled by it, never by a row id alone (RA-8116)."""
        reason = self.admit()
        if reason:
            spend.finish(row, "not_sent", 0.0, call_id=call_id)
            return reason, None
        result = call()
        kind = outcome(result[0])
        if kind == "refused":
            self.refused(f"signal_unavailable:http_{result[0]}")
        elif kind == "proven":
            self.answered()
        return None, result
