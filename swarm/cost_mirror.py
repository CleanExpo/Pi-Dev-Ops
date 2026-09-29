"""cost_mirror.py — keep the LLM cost mirror to Supabase off the event loop.

`budget_tracker.record_cost` mirrors each row to Supabase with a blocking
urllib request (8 s timeout). Called from async build code it froze every
request: the loop-lag monitor caught a 2.3 s stall in record_cost at 14:23 UTC
on 29 Sept 2026 (same class as RA-7845, which only covered the session
checkpoint).

On a running event loop the write goes to one worker thread; one worker keeps
rows in order. Off the loop it stays synchronous, exactly as before. The local
JSONL is the source of truth, so when Supabase is slow and writes pile up, the
extra mirrors are dropped rather than queued without limit.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

log = logging.getLogger("swarm.cost_mirror")

MAX_PENDING = 200
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cost-mirror")
_lock = threading.Lock()
_pending = 0


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


def _write_queued(row: dict[str, Any]) -> None:
    global _pending
    try:
        _write(row)
    finally:
        with _lock:
            _pending -= 1


def mirror(row: dict[str, Any]) -> None:
    """Mirror one cost row to Supabase without blocking a running event loop."""
    global _pending
    if not _on_event_loop():
        _write(row)
        return
    with _lock:
        if _pending >= MAX_PENDING:
            log.debug("cost_mirror: backlog full, row kept in JSONL only")
            return
        _pending += 1
    try:
        _pool.submit(_write_queued, row)
    except Exception as exc:  # noqa: BLE001
        with _lock:
            _pending -= 1
        log.debug("cost_mirror: not queued (non-fatal): %s", exc)


def wait_idle(timeout: float = 5.0) -> bool:
    """Block until queued writes have run; False if they outlast the timeout."""
    try:
        _pool.submit(lambda: None).result(timeout=timeout)
    except Exception:
        return False
    return True
