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
from typing import Any, Awaitable, Callable

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
    threading.Thread(target=target, daemon=True, name="goal-analysis-model").start()
    return fut
