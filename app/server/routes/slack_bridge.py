"""Slack Events API ingress for the Margot Slack <-> Telegram bridge."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from swarm.margot_slack_bridge import handle_slack_message_event

log = logging.getLogger("app.server.routes.slack_bridge")

router = APIRouter(prefix="/webhooks/slack", tags=["slack-bridge"])

_MAX_SIGNATURE_AGE_S = 300
_MAX_SLACK_REQUEST_BODY = 1024 * 1024  # Slack event payloads are small; cap at 1 MiB.
_seen_event_ids: set[str] = set()
_seen_event_order: deque[str] = deque()
_seen_lock = threading.Lock()
_MAX_SEEN_EVENTS = 500


def _signing_secret() -> str:
    """Return the configured Slack signing secret without logging it."""
    return (os.environ.get("SLACK_SIGNING_SECRET") or "").strip()


def _bot_token() -> str:
    """Return the configured Slack bot token without logging it."""
    return (os.environ.get("SLACK_BOT_TOKEN") or "").strip()


def _bridge_enabled() -> bool:
    """Return whether production explicitly opted into the bridge."""
    return (os.environ.get("SLACK_TELEGRAM_BRIDGE_ENABLED") or "0").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _strengthening_channel() -> str:
    """Return the configured strengthening channel ID."""
    return (os.environ.get("SLACK_MARGOT_STRENGTHENING_CHANNEL") or "").strip()


def _verify_signature(*, raw_body: bytes, timestamp: str, signature: str,
                      now: float | None = None) -> bool:
    """Validate Slack's v0 HMAC signature and five-minute replay window."""
    secret = _signing_secret()
    if not secret or not timestamp or not signature:
        return False
    try:
        ts_int = int(timestamp)
    except ValueError:
        return False
    current = time.time() if now is None else now
    if abs(current - ts_int) > _MAX_SIGNATURE_AGE_S:
        return False
    base = b"v0:" + timestamp.encode("utf-8") + b":" + raw_body
    expected = "v0=" + hmac.new(
        secret.encode("utf-8"), base, hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _mark_event_once(event_id: str) -> bool:
    """Reserve an event ID once per process while it is processing/completed."""
    if not event_id:
        return True
    with _seen_lock:
        if event_id in _seen_event_ids:
            return False
        _seen_event_ids.add(event_id)
        _seen_event_order.append(event_id)
        while len(_seen_event_order) > _MAX_SEEN_EVENTS:
            oldest = _seen_event_order.popleft()
            _seen_event_ids.discard(oldest)
        return True


def _release_failed_event(event_id: str) -> None:
    """Release a failed reservation so a later Slack retry may run it again."""
    if not event_id:
        return
    with _seen_lock:
        _seen_event_ids.discard(event_id)
        try:
            _seen_event_order.remove(event_id)
        except ValueError:
            pass


async def _read_limited_body(request: Request) -> bytes:
    """Stream the request body and stop at one MiB, including chunked bodies."""
    declared = request.headers.get("content-length")
    if declared:
        try:
            if int(declared) > _MAX_SLACK_REQUEST_BODY:
                raise HTTPException(status_code=413, detail="Request too large")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid Content-Length")

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > _MAX_SLACK_REQUEST_BODY:
            raise HTTPException(status_code=413, detail="Request too large")
        body.extend(chunk)
    return bytes(body)


def _parse_signed_payload(request: Request, raw_body: bytes) -> dict[str, Any]:
    """Authenticate and decode a Slack request after the bounded body read."""
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    if not timestamp or not signature:
        raise HTTPException(status_code=401, detail="Invalid Slack signature")
    if not _signing_secret():
        raise HTTPException(status_code=503, detail="Slack bridge not configured")
    if not _verify_signature(raw_body=raw_body, timestamp=timestamp, signature=signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Invalid Slack payload")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid Slack payload")
    return payload


def _slack_json(method: str, payload: dict[str, str] | None = None) -> dict[str, Any]:
    """Run a bounded Slack Web API probe without ever returning credential material."""
    token = _bot_token()
    if not token:
        return {"ok": False, "error": "missing_bot_token"}
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return {"ok": False, "error": "network_or_invalid_response"}
    if not isinstance(body, dict):
        return {"ok": False, "error": "invalid_response"}
    return {
        "ok": bool(body.get("ok")),
        "error": str(body.get("error") or "")[:80],
    }


def _slack_health_snapshot() -> dict[str, Any]:
    """Return a non-secret readiness snapshot for the production Slack bridge."""
    token_present = bool(_bot_token())
    signing_present = bool(_signing_secret())
    channel = _strengthening_channel()
    enabled = _bridge_enabled()
    auth = _slack_json("auth.test") if token_present else {"ok": False, "error": "missing_bot_token"}
    channel_check = (
        _slack_json("conversations.info", {"channel": channel})
        if auth.get("ok") and channel
        else {"ok": False, "error": "auth_or_channel_missing"}
    )
    ready = bool(
        enabled and token_present and signing_present and channel
        and auth.get("ok") and channel_check.get("ok")
    )
    if ready:
        status = "ready"
    elif not enabled:
        status = "disabled"
    elif not token_present:
        status = "missing_bot_token"
    elif not signing_present:
        status = "missing_signing_secret"
    elif not auth.get("ok"):
        status = "bot_auth_failed"
    elif not channel:
        status = "missing_channel"
    else:
        status = "channel_inaccessible"
    return {
        "ready": ready,
        "status": status,
        "enabled": enabled,
        "bot_token_present": token_present,
        "signing_secret_present": signing_present,
        "channel_configured": bool(channel),
        "bot_auth_ok": bool(auth.get("ok")),
        "channel_access": bool(channel_check.get("ok")),
    }


async def _process_event(event: dict[str, Any], event_id: str) -> None:
    """Run one accepted Slack event and reopen its ID if processing fails."""
    try:
        result = await handle_slack_message_event(event)
        log.info("slack bridge event=%s result=%s", event_id or "?", result)
        if str(result).startswith("failed:"):
            _release_failed_event(event_id)
    except Exception as exc:  # noqa: BLE001
        _release_failed_event(event_id)
        log.exception("slack bridge background handler failed: %s", exc)


def _dispatch_callback(
    payload: dict[str, Any], background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Validate one event_callback and schedule exactly one message handler."""
    event_id = str(payload.get("event_id") or "").strip()
    if not _mark_event_once(event_id):
        return {"ok": True, "duplicate": True}
    event = payload.get("event") or {}
    if not isinstance(event, dict) or event.get("type") != "message":
        return {"ok": True, "ignored": "not_message"}
    background_tasks.add_task(_process_event, event, event_id)
    return {"ok": True}


@router.get("/health")
async def slack_bridge_health() -> dict[str, Any]:
    """Expose bridge readiness using booleans/status only, never secret values."""
    return await asyncio.to_thread(_slack_health_snapshot)


@router.post("/events")
async def slack_events(
    request: Request, background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Authenticate, acknowledge, and defer Slack Events API callbacks safely."""
    raw_body = await _read_limited_body(request)
    payload = _parse_signed_payload(request, raw_body)
    payload_type = payload.get("type")
    if payload_type == "url_verification":
        return {"challenge": payload.get("challenge", "")}
    if payload_type != "event_callback":
        return {"ok": True, "ignored": "unsupported_type"}
    return _dispatch_callback(payload, background_tasks)


__all__ = ["router"]
