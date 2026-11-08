"""Who owns a goal analysis job's model call (UNI-3306 PR 2, review r1 P1-1 and r2 P1).

Design: ownership of the concurrency slot and of the job belongs to the MODEL THREAD, not
the coroutine. A coroutine can be cancelled or time out; a blocking provider thread cannot
be killed. So:
- The model call runs in a thread this module starts (run_in_thread), never a bare
  asyncio.to_thread that nothing can track.
- The per-process slot and the live-job registry entry are released ONLY in that thread's
  own finally, once the model call has actually returned. A cancelled or timed-out
  coroutine never releases them, so recovery cannot start attempt 2 of a job whose
  attempt 1 still runs a model call, and the limit counts real model calls.
- take() refuses a job id already in the registry and refuses when every slot is in use;
  the refused job stays queued (or interrupted) for a later recovery pass.
A slot is taken BEFORE the claim and handed to the model thread when it starts. If the
attempt never reaches the model call, the launching task releases the slot itself.
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
from typing import Any, Awaitable, Callable

# ---- the self-fencing lease (review r3) -------------------------------------------------
# The end of an attempt is decided remotely (the database claim expires) but the local stop
# used to fire only when a heartbeat RETURNED False, so a stalled loop or a hung heartbeat
# never learned the claim was gone and another server's attempt overlapped it. Now every
# attempt has a watchdog THREAD (independent of the event loop) that fences the attempt, by
# setting stop, at  fence_at = (monotonic time the last SUCCESSFUL heartbeat or the claim was
# SENT) + CLAIM_S - FENCE_SAFETY_S.  Sent, not returned: the database stamps the new expiry
# after it receives the request, so sent + CLAIM_S can only be earlier than the real expiry.
#   CLAIM_S           = the claim length in the SQL functions (pinned to the migration by a test)
#   STOP_BOUND_S      = 5 s: a stopped model call ends within 5 s (#1002)
#   WATCH_POLL_S      = 0.5 s: the watchdog's wake-up interval
#   FENCE_SLACK_S     = 4 s: scheduling and clock slack
#   FENCE_SAFETY_S    = 9.5 s, so stop is complete by sent + 60 - 9.5 + 0.5 + 5 = sent + 56 s,
#                       before the claim can expire, and recovery adds a further 5 s margin.
#   HEARTBEAT_S = 20 s, so fence_at - sent = 50.5 s tolerates two lost beats and never fences
#                       a healthy attempt; the test asserts 2 * HEARTBEAT_S < 50.5 s.
CLAIM_S = 60.0
STOP_BOUND_S = 5.0
WATCH_POLL_S = 0.5
FENCE_SLACK_S = 4.0
FENCE_SAFETY_S = STOP_BOUND_S + WATCH_POLL_S + FENCE_SLACK_S
_now = time.monotonic

_lock = threading.Lock()
_live: set[str] = set()  # job ids holding a slot: launched, or with a live model thread
_running = 0  # slots in use


def max_concurrent() -> int:
    """Model runs at once in this process, read live like the switch. Default 2."""
    try:
        return max(1, int(os.environ.get("GOAL_ANALYZE_MAX_CONCURRENT", "2")))
    except ValueError:
        return 2


def is_live(job_id: str) -> bool:
    with _lock:
        return job_id in _live


class Slot:
    def __init__(self, job_id: str) -> None:
        self.job_id, self._held, self.handed_off = job_id, True, False

    def release(self) -> None:
        """Idempotent. Called by the model thread's finally, or by the launching task when
        the attempt never reached a model thread (see release_if_not_handed_off)."""
        global _running
        with _lock:
            if self._held:
                self._held = False
                _live.discard(self.job_id)
                _running -= 1

    def release_if_not_handed_off(self) -> None:
        if not self.handed_off:
            self.release()


def take(job_id: str) -> Slot | None:
    global _running
    with _lock:
        if job_id in _live or _running >= max_concurrent():
            return None
        _live.add(job_id)
        _running += 1
    return Slot(job_id)


def _deliver(fut: asyncio.Future[Any], outcome: tuple[str, Any]) -> None:
    if fut.done():
        return
    kind, value = outcome
    fut.set_result(value) if kind == "ok" else fut.set_exception(value)


def run_in_thread(call: Callable[[], Awaitable[Any]], slot: Slot | None,
                  loop: asyncio.AbstractEventLoop) -> asyncio.Future[Any]:
    """Run call() on its own event loop in a thread we own. The future resolves when the
    call returns; cancelling the future does NOT end the thread. The slot is released in
    the thread's own finally."""
    fut: asyncio.Future[Any] = loop.create_future()

    def target() -> None:
        try:
            outcome: tuple[str, Any] = ("ok", asyncio.run(call()))
        except BaseException as exc:  # reported to the waiter; a thread must never die silently
            outcome = ("err", exc)
        finally:
            if slot is not None:
                slot.release()
        try:
            loop.call_soon_threadsafe(_deliver, fut, outcome)
        except RuntimeError:
            pass  # the loop is closed: nobody is waiting

    if slot is not None:
        slot.handed_off = True
    try:
        threading.Thread(target=target, daemon=True, name="goal-analysis-model").start()
    except BaseException:
        # No thread exists, so nothing will release the slot: ownership never moved.
        if slot is not None:
            slot.handed_off = False
            slot.release()
        raise
    return fut


class Fence:
    """Watchdog for one attempt. advance() is called only after a heartbeat SUCCEEDED, with
    the time it was SENT; a failed or slow heartbeat never extends the lease."""

    def __init__(self, sent_at: float, on_expire: Callable[[], None]) -> None:
        self._at, self._on_expire = sent_at, on_expire
        self._guard, self._done = threading.Lock(), threading.Event()

    def fence_at(self) -> float:
        with self._guard:
            return self._at + CLAIM_S - FENCE_SAFETY_S

    def advance(self, sent_at: float) -> None:
        with self._guard:
            self._at = max(self._at, sent_at)

    def start(self) -> None:
        threading.Thread(target=self._watch, daemon=True, name="goal-analysis-fence").start()

    def close(self) -> None:
        self._done.set()

    def _watch(self) -> None:
        while not self._done.wait(WATCH_POLL_S):
            if _now() >= self.fence_at():
                self._on_expire()
                return
