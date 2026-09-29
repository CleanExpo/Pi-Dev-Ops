"""cost_mirror.py — keep the LLM cost mirror to Supabase off the event loop.

`budget_tracker.record_cost` mirrors each row to Supabase with a blocking
urllib request (8 s timeout). Called from async build code it froze every
request: the loop-lag monitor caught a 2.3 s stall in record_cost at 14:23 UTC
on 29 Sept 2026 (same class as RA-7845, which only covered the session
checkpoint).

On a running event loop the write goes to one daemon worker thread; one worker
keeps rows in order. Off the loop it stays synchronous, exactly as before. The
local JSONL is the source of truth, so the mirror is allowed to lose rows: when
Supabase is slow the bounded queue drops the extras, and because the worker is
a daemon a normal shutdown does not wait for the queue (a ThreadPoolExecutor
would join and drain it, up to 200 x 8 s).
"""
from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from typing import Any

log = logging.getLogger("swarm.cost_mirror")

MAX_PENDING = 200
_queue: queue.Queue[Any] = queue.Queue(maxsize=MAX_PENDING)
_start_lock = threading.Lock()
_worker: threading.Thread | None = None


def _on_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _write(row: dict[str, Any]) -> None:
    try:
        from app.server.supabase_log import _insert  # noqa: PLC0415
        _insert("llm_costs", row)
    except Exception as exc:  # noqa: BLE001
        log.debug("cost_mirror: supabase mirror failed (non-fatal): %s", exc)


def _run() -> None:
    while True:
        item = _queue.get()
        try:
            if isinstance(item, threading.Event):
                item.set()
            else:
                _write(item)
        finally:
            _queue.task_done()


def _ensure_worker() -> None:
    global _worker
    with _start_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_run, name="cost-mirror", daemon=True)
            _worker.start()


def mirror(row: dict[str, Any]) -> None:
    """Mirror one cost row to Supabase without blocking a running event loop."""
    if not _on_event_loop():
        _write(row)
        return
    try:
        _queue.put_nowait(row)
    except queue.Full:
        log.debug("cost_mirror: backlog full, row kept in JSONL only")
        return
    _ensure_worker()


def wait_idle(timeout: float = 5.0) -> bool:
    """Block until queued writes have run; False if they outlast the timeout."""
    deadline = time.monotonic() + timeout
    done = threading.Event()
    try:
        _queue.put(done, timeout=timeout)
    except queue.Full:
        return False
    _ensure_worker()
    return done.wait(max(0.0, deadline - time.monotonic()))


async def flush(timeout: float) -> None:
    """Await queued writes at shutdown, for at most `timeout` seconds.

    Queued rows that outlast the wait are lost from Supabase only; the local
    JSONL has them. Nothing here can block an exit for longer than `timeout`.
    """
    if not await asyncio.to_thread(wait_idle, timeout):
        log.warning("queued cost mirrors did not finish within %.0fs", timeout)
