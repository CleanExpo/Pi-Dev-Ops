"""Production Telegram intake daemon and status route.

The standalone scripts remain the source of truth for Telegram polling and
idea promotion. This module only makes sure the same loop runs inside the
Railway FastAPI process so `/api/health/full` can observe the heartbeat on the
production host.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.parse
import urllib.request
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
_last_webhook_at: float | None = None
_last_webhook_ok: bool | None = None
_last_webhook_error: str = ""


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


def _webhook_autoconfigure_enabled() -> bool:
    return _env_flag("TELEGRAM_WEBHOOK_AUTOCONFIGURE", "1")


def _telegram_webhook_secret() -> str:
    return os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()


def _telegram_webhook_url() -> str:
    explicit = os.environ.get("TELEGRAM_WEBHOOK_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")

    for key in ("PI_CEO_PUBLIC_URL", "PI_CEO_URL", "RAILWAY_PUBLIC_DOMAIN"):
        value = os.environ.get(key, "").strip()
        if not value:
            continue
        if value.startswith(("http://", "https://")):
            return f"{value.rstrip('/')}/webhook/telegram"
        return f"https://{value.rstrip('/')}/webhook/telegram"

    return "https://pi-dev-ops-production.up.railway.app/webhook/telegram"


def _should_use_webhook_mode() -> bool:
    return bool(
        _webhook_autoconfigure_enabled()
        and os.environ.get("TELEGRAM_BOT_TOKEN")
        and _telegram_webhook_secret()
    )


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
        "webhook_autoconfigure": _webhook_autoconfigure_enabled(),
        "webhook_mode": _should_use_webhook_mode(),
        "webhook_url": _telegram_webhook_url() if _should_use_webhook_mode() else "",
        "last_webhook_ok": _last_webhook_ok,
        "last_webhook_error": _last_webhook_error,
        "last_webhook_age_s": int(now - _last_webhook_at) if _last_webhook_at else None,
    }


def _ensure_telegram_webhook() -> bool:
    """Register Telegram's webhook so Railway wins over competing getUpdates clients."""
    global _last_webhook_at, _last_webhook_ok, _last_webhook_error

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    secret = _telegram_webhook_secret()
    url = _telegram_webhook_url()
    if not token or not secret:
        _last_webhook_ok = False
        _last_webhook_error = "missing TELEGRAM_BOT_TOKEN or TELEGRAM_WEBHOOK_SECRET"
        return False

    payload = urllib.parse.urlencode(
        {
            "url": url,
            "secret_token": secret,
            "drop_pending_updates": "false",
            "allowed_updates": json.dumps(["message"]),
        }
    ).encode("utf-8")

    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/setWebhook",
            data=payload,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        if not body.get("ok"):
            raise RuntimeError(body.get("description") or str(body))
        _last_webhook_ok = True
        _last_webhook_error = ""
        log.info("Telegram webhook ensured: %s", url)
        return True
    except Exception as exc:  # noqa: BLE001 - loop must keep trying
        _last_webhook_ok = False
        _last_webhook_error = str(exc)[:200]
        log.warning("Telegram webhook ensure failed: %s", exc)
        return False
    finally:
        _last_webhook_at = time.time()


async def _run_iteration() -> None:
    global _last_poll_at, _last_drain_at, _last_poll_exit, _last_processed, _last_error, _iteration_count

    if _should_use_webhook_mode():
        _last_poll_exit = 0 if await asyncio.to_thread(_ensure_telegram_webhook) else 2
        _last_poll_at = time.time()
        _last_drain_at = _last_poll_at
        _iteration_count += 1
        _last_error = _last_webhook_error
        return

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
