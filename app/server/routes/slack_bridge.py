"""Slack Events API ingress for the Margot Slack <-> Telegram bridge."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
from collections import deque
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from swarm.margot_slack_bridge import handle_slack_message_event

log = logging.getLogger("app.server.routes.slack_bridge")

router = APIRouter(prefix="/webhooks/slack", tags=["slack-bridge"])

_MAX_SIGNATURE_AGE_S = 300
_seen_event_ids: set[str] = set()
_seen_event_order: deque[str] = deque()
_seen_lock = threading.Lock()
_MAX_SEEN_EVENTS = 500


def _signing_secret() -> str:
    return (os.environ.get("SLACK_SIGNING_SECRET") or "").strip()


def _verify_signature(*, raw_body: bytes, timestamp: str, signature: str,
                      now: float | None = None) -> bool:
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
    """Return True once per process for a Slack event_id."""
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


async def _process_event(event: dict[str, Any], event_id: str) -> None:
    try:
        result = await handle_slack_message_event(event)
        log.info("slack bridge event=%s result=%s", event_id or "?", result)
    except Exception as exc:  # noqa: BLE001
        log.exception("slack bridge background handler failed: %s", exc)


@router.post("/events")
async def slack_events(request: Request, background_tasks: BackgroundTasks
                       ) -> dict[str, Any]:
    """Verify and acknowledge Slack Events API callbacks.

    Slack expects a response in roughly three seconds, so accepted message
    events are processed after the HTTP acknowledgement via BackgroundTasks.
    """
    if not _signing_secret():
        raise HTTPException(status_code=503, detail="Slack bridge not configured")

    raw_body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    if not _verify_signature(
        raw_body=raw_body, timestamp=timestamp, signature=signature,
    ):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Invalid Slack payload")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid Slack payload")

    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}

    if payload.get("type") != "event_callback":
        return {"ok": True, "ignored": "unsupported_type"}

    # Our handler acknowledges immediately. Slack retry callbacks are therefore
    # duplicates, not a reason to execute Margot a second time.
    if request.headers.get("X-Slack-Retry-Num"):
        return {"ok": True, "duplicate": True}

    event_id = str(payload.get("event_id") or "").strip()
    if not _mark_event_once(event_id):
        return {"ok": True, "duplicate": True}

    event = payload.get("event") or {}
    if not isinstance(event, dict) or event.get("type") != "message":
        return {"ok": True, "ignored": "not_message"}

    background_tasks.add_task(_process_event, event, event_id)
    return {"ok": True}


__all__ = ["router"]
