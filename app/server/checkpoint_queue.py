"""checkpoint_queue.py — keep the Supabase session checkpoint off the event loop (RA-7845).

`persistence.save_session` is called from async build phases. Its Supabase
dual-write is a blocking `urllib` request with an 8 s timeout, so each save
froze every request on the server while Supabase answered: the loop-lag
monitor caught a 2.4 s stall inside `_phase_sandbox -> save_session` at
11:19 UTC on 29 Sept 2026.

On the loop thread the row is built immediately — the session keeps mutating,
so the write must carry the state at the moment of the save — and the network
write goes to one worker thread. One worker keeps writes in order. Saves that
pile up for the same session while Supabase is slow collapse to the newest
row, which is the only one that matters for resume. Off the loop the write
stays synchronous, exactly as before.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

log = logging.getLogger("pi-ceo.checkpoint_queue")

_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="supabase-checkpoint")
_lock = threading.Lock()
_pending: dict[str, dict[str, Any]] = {}


def _on_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _write(row: dict[str, Any]) -> bool:
    from . import supabase_log
    try:
        return supabase_log._upsert("sessions", row)
    except Exception as exc:
        log.warning("RA-1407 queued checkpoint failed (non-fatal): %s", exc)
        return False


def _drain(sid: str) -> None:
    with _lock:
        row = _pending.pop(sid, None)
    if row is not None:
        _write(row)


def _enqueue(sid: str, row: dict[str, Any]) -> None:
    with _lock:
        already_queued = sid in _pending
        _pending[sid] = row
    if not already_queued:
        _pool.submit(_drain, sid)


def save_checkpoint(session: Any) -> None:
    """Persist the session checkpoint to Supabase without blocking the event loop."""
    from . import supabase_log
    if not _on_event_loop():
        supabase_log.save_session_checkpoint(session)
        return
    sid = getattr(session, "id", "") if session is not None else ""
    if not sid:
        return
    try:
        # A JSON round trip detaches the row from the live session: nested
        # lists and dicts the build keeps mutating are copied, not shared.
        row = json.loads(json.dumps(supabase_log._checkpoint_payload(session)))
    except Exception as exc:
        log.warning("RA-1407 checkpoint not serialisable (non-fatal): %s", exc)
        return
    _enqueue(sid, row)


def wait_idle(timeout: float = 5.0) -> bool:
    """Block until queued writes have run; False if they outlast the timeout."""
    try:
        _pool.submit(lambda: None).result(timeout=timeout)
    except Exception:
        return False
    return True


async def flush(timeout: float) -> None:
    """Await queued writes at shutdown: the "interrupted" rows are what the
    next container resumes from, so they must land before the process exits."""
    if not await asyncio.to_thread(wait_idle, timeout):
        log.warning("queued Supabase checkpoints did not finish within %.0fs", timeout)
