"""Production Telegram intake daemon and status route.

The standalone scripts remain the source of truth for Telegram polling and
idea promotion. This module only makes sure the same loop runs inside the
Railway FastAPI process so `/api/health/full` can observe the heartbeat on the
production host.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..app_factory import app, _resilient


log = logging.getLogger("pi-ceo.telegram_intake")
router = APIRouter()

_started_at: float | None = None
_last_poll_at: float | None = None
_last_drain_at: float | None = None
_last_poll_exit: int | None = None
_last_processed: int = 0
_last_error: str = ""
_iteration_count: int = 0


def _env_flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _has_chat_allowlist() -> bool:
    return bool(
        os.environ.get("ALLOWED_USERS")
        or os.environ.get("TELEGRAM_CHAT_ID")
        or os.environ.get("PHONE_COMPANION_CHAT_ID")
    )


def _configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and _has_chat_allowlist())


def _interval_seconds() -> int:
    raw = os.environ.get("TELEGRAM_INTAKE_POLL_SECONDS", "60")
    try:
        return max(15, int(raw))
    except ValueError:
        return 60


def _startup_delay_seconds() -> int:
    raw = os.environ.get("TELEGRAM_INTAKE_STARTUP_DELAY_SECONDS", "5")
    try:
        return max(0, int(raw))
    except ValueError:
        return 5


def _status() -> dict[str, Any]:
    now = time.time()
    return {
        "enabled": _env_flag("TELEGRAM_INTAKE_ENABLED", "1"),
        "configured": _configured(),
        "started": _started_at is not None,
        "poll_interval_s": _interval_seconds(),
        "iteration_count": _iteration_count,
        "last_poll_exit": _last_poll_exit,
        "last_processed": _last_processed,
        "last_error": _last_error,
        "last_poll_age_s": int(now - _last_poll_at) if _last_poll_at else None,
        "last_drain_age_s": int(now - _last_drain_at) if _last_drain_at else None,
        "has_bot_token": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        "has_chat_allowlist": _has_chat_allowlist(),
        "has_linear_api_key": bool(os.environ.get("LINEAR_API_KEY")),
    }


async def _run_iteration() -> None:
    global _last_poll_at, _last_drain_at, _last_poll_exit, _last_processed, _last_error, _iteration_count

    from scripts import marathon_telegram_inbox, marathon_watchdog  # noqa: PLC0415

    poll_exit = await asyncio.to_thread(marathon_telegram_inbox.main)
    _last_poll_exit = int(poll_exit)
    _last_poll_at = time.time()

    if poll_exit == 0:
        processed, replies = await asyncio.to_thread(marathon_watchdog._drain_inbox)
        _last_processed = int(processed)
        _last_drain_at = time.time()
        if processed:
            log.info("Telegram intake drained %d message(s): %s", processed, " | ".join(replies[:3]))
    else:
        log.warning("Telegram intake poll returned non-zero exit code: %s", poll_exit)

    _iteration_count += 1
    _last_error = ""


async def telegram_intake_loop() -> None:
    """Poll Telegram and drain queued phone ideas until the process exits."""
    global _started_at, _last_error

    _started_at = time.time()
    delay = _startup_delay_seconds()
    interval = _interval_seconds()
    if delay:
        await asyncio.sleep(delay)

    log.info("Telegram intake loop started (interval=%ss)", interval)
    while True:
        try:
            await _run_iteration()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - loop must keep breathing
            _last_error = str(exc)[:200]
            log.warning("Telegram intake iteration failed: %s", exc, exc_info=True)
        await asyncio.sleep(interval)


@app.on_event("startup")
async def _start_telegram_intake() -> None:
    if not _env_flag("TELEGRAM_INTAKE_ENABLED", "1"):
        log.info("Telegram intake loop disabled (TELEGRAM_INTAKE_ENABLED=0)")
        return
    if not _configured():
        log.info(
            "Telegram intake loop not started (missing TELEGRAM_BOT_TOKEN or chat allowlist)"
        )
        return
    asyncio.create_task(_resilient(telegram_intake_loop, "telegram_intake_loop"))


@router.get("/api/telegram/intake/status")
async def telegram_intake_status() -> JSONResponse:
    return JSONResponse(_status())
