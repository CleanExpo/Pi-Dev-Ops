"""RA-8100 delivery reconcile seam: flag, scheduler submit, status entry points.

Read-only: nothing here writes to an outside service. The tick lives in
delivery_reconcile_tick (a later unit); this module only submits it and reports on it.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import delivery_reconcile_status as _status

logger = logging.getLogger("pi-ceo.delivery_reconcile")

FLAG = "TAO_DELIVERY_RECONCILE"
STATE_FILE = Path(__file__).resolve().parents[2] / ".harness" / "delivery-reconcile-state.json"
LOCK_FILE = STATE_FILE.with_name("delivery-reconcile.lock")

_last_save_ok: bool | None = None
_last_tick_error: str | None = None
_inflight: Any = None


def enabled() -> bool:
    return os.environ.get(FLAG, "").strip() == "canary"


def record_save(persisted: bool) -> None:
    """The tick reports whether its last state save succeeded."""
    global _last_save_ok
    _last_save_ok = bool(persisted)


def record_tick(out: Any) -> None:
    """The last tick's error code (None after a tick with none), so the tile never shows an older good
    result after a tick failed. A skipped tick (lease held) neither sets nor clears it."""
    global _last_tick_error
    if not isinstance(out, dict) or "skipped" in out:
        return
    error = out.get("error")
    _last_tick_error = error if isinstance(error, str) else None


def run_reconcile_tick(now: datetime | None = None, path: str | None = None) -> dict:
    """One reconcile tick. Never raises; every failure is a returned state."""
    try:
        from .delivery_reconcile_tick import run_tick

        out = run_tick(now, path)
    except Exception as exc:  # noqa: BLE001 — recorded by type name only
        out = {"error": f"tick_failed_{type(exc).__name__}", "complete": False, "persisted": False}
    record_tick(out)
    return out


def _on_done(fut: Any, log: logging.Logger) -> None:
    """Log the tick outcome. An exception is reported by type name only, never its text."""
    try:
        if fut.cancelled():
            log.error("Delivery reconcile tick cancelled")
            return
        log.info("Delivery reconcile tick done: %s", fut.result())
    except Exception as exc:  # noqa: BLE001
        log.error("Delivery reconcile tick failed: %s", type(exc).__name__)


def submit_tick(loop: Any, log: logging.Logger) -> Any:
    """Submit the tick to the executor without awaiting it. Flag off: do nothing. Never raises."""
    global _inflight
    try:
        if not enabled():
            return None
        fut = loop.run_in_executor(None, run_reconcile_tick)
        _inflight = fut
        fut.add_done_callback(lambda f: _on_done(f, log))
        return fut
    except Exception as exc:  # noqa: BLE001
        try:
            log.error("Delivery reconcile submit failed: %s", type(exc).__name__)
        except Exception:  # noqa: BLE001
            pass
        return None


def status_snapshot(path: str | os.PathLike[str] | None = None,
                    now: datetime | None = None) -> dict:
    """Read-only tile for /api/mission-control/live. Never raises, never writes."""
    try:
        return _status.build(path or STATE_FILE, now or datetime.now(timezone.utc),
                             enabled(), _last_save_ok, _last_tick_error)
    except Exception as exc:  # noqa: BLE001
        snap = _status._snap("unreadable", [f"status_failed_{type(exc).__name__}"], enabled())
        return snap
