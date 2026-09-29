"""loop_lag.py — name the code that freezes the event loop (RA-7845).

uvicorn runs this app on one event loop (--workers 1). Any blocking call made
inside an async handler stalls every request at once: production /health has
taken 5-25 s with the CPU idle. The 08:15 freeze on 29 Sept 2026 stalled
everything for 10 s and no log line named the cause.

A coroutine on the loop stamps a heartbeat every second. A plain thread, which
keeps running while the loop is stuck, checks that heartbeat. When it is older
than the threshold, the thread logs the loop thread's current stack: the frame
at the top is the blocking call itself. A tick that only measures its own late
wake-up could say how long a freeze lasted but never what caused it, because
by then the blocker has returned.

One warning per stall, with the stack, then one info line with the total
duration when the loop answers again. Env: TAO_LOOP_LAG_ENABLED (default 1),
TAO_LOOP_LAG_THRESHOLD_S (default 2.0).
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import time
import traceback

log = logging.getLogger("pi-ceo.loop_lag")

_STACK_FRAMES = 25


class LoopLagMonitor:
    """Heartbeat on the loop, watcher on a thread; logs stalls with the loop's stack."""

    def __init__(self, threshold_s: float = 2.0, interval_s: float = 1.0) -> None:
        self.threshold_s = threshold_s
        self.interval_s = interval_s
        self._beat = time.monotonic()
        self._loop_thread_id: int | None = None
        self._stalled_since: float | None = None
        self._stop = threading.Event()

    async def heartbeat(self) -> None:
        """Runs on the event loop; stamps the time each interval."""
        self._loop_thread_id = threading.get_ident()
        while not self._stop.is_set():
            self._beat = time.monotonic()
            await asyncio.sleep(self.interval_s)

    def loop_stack(self) -> str:
        """The loop thread's current stack, innermost frame last."""
        frame = sys._current_frames().get(self._loop_thread_id or -1)
        if frame is None:
            return "(loop thread stack unavailable)"
        return "".join(traceback.format_stack(frame, limit=_STACK_FRAMES))

    def check(self, now: float) -> None:
        """One watcher step: report a stall once, and its end once."""
        age = now - self._beat
        if age > self.threshold_s and self._stalled_since is None:
            self._stalled_since = self._beat
            log.warning(
                "event loop stalled: no heartbeat for %.1fs (threshold %.1fs); loop is running:\n%s",
                age, self.threshold_s, self.loop_stack(),
            )
        elif age <= self.threshold_s and self._stalled_since is not None:
            log.info("event loop recovered after a %.1fs stall", self._beat - self._stalled_since)
            self._stalled_since = None

    def watch(self) -> None:
        """Runs on a daemon thread until stop()."""
        while not self._stop.wait(self.interval_s / 2):
            self.check(time.monotonic())

    def stop(self) -> None:
        self._stop.set()


def _threshold_from_env() -> float | None:
    """The stall threshold in seconds, or None when disabled or misconfigured."""
    if os.environ.get("TAO_LOOP_LAG_ENABLED", "1") == "0":
        return None
    raw = os.environ.get("TAO_LOOP_LAG_THRESHOLD_S", "2.0")
    try:
        value = float(raw)
    except ValueError:
        log.warning("TAO_LOOP_LAG_THRESHOLD_S=%r is not a number; loop-lag monitor off", raw)
        return None
    return value if value > 0 else None


def start_loop_lag_monitor() -> LoopLagMonitor | None:
    """Start the heartbeat task and watcher thread. Call from inside the running loop."""
    threshold = _threshold_from_env()
    if threshold is None:
        log.info("loop-lag monitor not started")
        return None
    monitor = LoopLagMonitor(threshold_s=threshold)
    asyncio.get_running_loop().create_task(monitor.heartbeat(), name="loop_lag_heartbeat")
    threading.Thread(target=monitor.watch, name="loop-lag-watch", daemon=True).start()
    log.info("loop-lag monitor started (threshold %.1fs)", threshold)
    return monitor
