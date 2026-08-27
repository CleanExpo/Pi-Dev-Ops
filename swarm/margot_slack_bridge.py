"""Bidirectional Slack <-> Telegram bridge for Margot.

Telegram remains Phill's mobile front door. Each Telegram-originated Margot
turn is mirrored into the private Slack strengthening channel as one thread.
A human reply inside that thread is routed back through the same Margot engine,
sent to Telegram, and appended to the same Slack thread.

The module intentionally does not consume arbitrary top-level Slack messages.
Only replies whose parent carries bridge metadata are accepted. This prevents
Slack chatter, bot messages, and unrelated threads from becoming Telegram
commands.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any

log = logging.getLogger("swarm.margot_slack_bridge")

SLACK_API_BASE = "https://slack.com/api/{method}"
DEFAULT_STRENGTHENING_CHANNEL = "C0BTX0LRZQ8"
BRIDGE_EVENT_TYPE = "margot_telegram_bridge"
_MAX_SLACK_TEXT = 3800
_MENTION_RE = re.compile(r"^(?:\s*<@[A-Z0-9]+>\s*)+", re.I)


def slack_token() -> str:
    return (os.environ.get("SLACK_BOT_TOKEN") or "").strip()


def strengthening_channel() -> str:
    return (
        os.environ.get("SLACK_MARGOT_STRENGTHENING_CHANNEL")
        or DEFAULT_STRENGTHENING_CHANNEL
    ).strip()


def bridge_enabled() -> bool:
    raw = (os.environ.get("SLACK_TELEGRAM_BRIDGE_ENABLED") or "1").strip().lower()
    return raw in {"1", "true", "yes", "on"} and bool(slack_token())


def _clip(text: str, limit: int = _MAX_SLACK_TEXT) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 16)].rstrip() + "\n… [truncated]"


def _slack_api(method: str, payload: dict[str, Any], *, timeout_s: float = 8.0
               ) -> dict[str, Any]:
    token = slack_token()
    if not token:
        return {"ok": False, "error": "missing_slack_bot_token"}
    req = urllib.request.Request(
        SLACK_API_BASE.format(method=method),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as response:
            body = json.loads(response.read().decode("utf-8"))
        if not isinstance(body, dict):
            return {"ok": False, "error": "invalid_slack_response"}
        return body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        return {"ok": False, "error": f"slack_http_{exc.code}:{body}"}
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        return {"ok": False, "error": f"slack_call_failed:{exc}"}


def _post_message(*, channel: str, text: str, thread_ts: str | None = None,
                  metadata: dict[str, Any] | None = None) -> str | None:
    payload: dict[str, Any] = {
        "channel": channel,
        "text": _clip(text),
        "unfurl_links": False,
        "unfurl_media": False,
    }
    if thread_ts:
        payload["thread_ts"] = thread_ts
    if metadata:
        payload["metadata"] = metadata
    result = _slack_api("chat.postMessage", payload)
    if not result.get("ok"):
        log.warning("margot bridge: Slack post failed (%s)", result.get("error"))
        return None
    ts = str(result.get("ts") or "").strip()
    return ts or None


def _thread_parent(*, channel: str, thread_ts: str) -> dict[str, Any] | None:
    result = _slack_api(
        "conversations.replies",
        {"channel": channel, "ts": thread_ts, "limit": 1, "inclusive": True},
    )
    if not result.get("ok"):
        log.warning("margot bridge: Slack thread lookup failed (%s)",
                    result.get("error"))
        return None
    messages = result.get("messages") or []
    if not isinstance(messages, list) or not messages:
        return None
    parent = messages[0]
    return parent if isinstance(parent, dict) else None


def _parent_bridge_context(parent: dict[str, Any] | None) -> dict[str, str] | None:
    if not parent:
        return None
    metadata = parent.get("metadata") or {}
    if not isinstance(metadata, dict):
        return None
    if metadata.get("event_type") != BRIDGE_EVENT_TYPE:
        return None
    event_payload = metadata.get("event_payload") or {}
    if not isinstance(event_payload, dict):
        return None
    chat_id = str(event_payload.get("chat_id") or "").strip()
    turn_id = str(event_payload.get("turn_id") or "").strip()
    if not chat_id:
        return None
    return {"chat_id": chat_id, "turn_id": turn_id}


def mirror_telegram_turn(turn: Any) -> str | None:
    """Mirror one Telegram-originated Margot turn into a new Slack thread."""
    if not bridge_enabled():
        return None
    channel = strengthening_channel()
    chat_id = str(getattr(turn, "chat_id", "") or "").strip()
    turn_id = str(getattr(turn, "turn_id", "") or "").strip()
    user_text = str(getattr(turn, "user_text", "") or "").strip()
    margot_text = str(getattr(turn, "margot_text", "") or "").strip()
    if not channel or not chat_id or not user_text:
        return None

    parent_text = (
        "*Telegram → Margot*\n"
        f"`{turn_id or 'turn'}`\n"
        f"{_clip(user_text)}"
    )
    metadata = {
        "event_type": BRIDGE_EVENT_TYPE,
        "event_payload": {
            "chat_id": chat_id,
            "turn_id": turn_id,
        },
    }
    parent_ts = _post_message(
        channel=channel,
        text=parent_text,
        metadata=metadata,
    )
    if not parent_ts:
        return None

    if margot_text:
        _post_message(
            channel=channel,
            thread_ts=parent_ts,
            text=f"*Margot → Telegram*\n{_clip(margot_text)}",
        )
    return parent_ts


def _clean_human_text(text: str) -> str:
    return _MENTION_RE.sub("", (text or "").strip()).strip()


async def handle_slack_message_event(event: dict[str, Any]) -> str:
    """Process one verified Slack message event.

    Only human replies inside a Telegram-created bridge thread are accepted.
    The reply is fed through Margot, which sends the resulting answer to the
    original Telegram chat. The same answer is then appended to the Slack
    thread so both surfaces stay aligned.
    """
    if not bridge_enabled():
        return "ignored:bridge_disabled"

    channel = str(event.get("channel") or "").strip()
    if channel != strengthening_channel():
        return "ignored:wrong_channel"
    if event.get("bot_id") or event.get("subtype"):
        return "ignored:bot_or_subtype"

    thread_ts = str(event.get("thread_ts") or "").strip()
    if not thread_ts:
        return "ignored:not_thread_reply"

    text = _clean_human_text(str(event.get("text") or ""))
    if not text:
        return "ignored:empty"

    parent = _thread_parent(channel=channel, thread_ts=thread_ts)
    context = _parent_bridge_context(parent)
    if not context:
        return "ignored:not_bridge_thread"

    event_ts = str(event.get("event_ts") or event.get("ts") or "").strip()
    try:
        from . import margot_bot  # noqa: PLC0415

        turn = await margot_bot.handle_turn(
            chat_id=context["chat_id"],
            user_text=text,
            message_id=f"slack:{event_ts}" if event_ts else "slack",
            _send=True,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("margot bridge: Slack -> Margot failed")
        _post_message(
            channel=channel,
            thread_ts=thread_ts,
            text=f"*Bridge error*\n{_clip(str(exc), 1200)}",
        )
        return f"failed:{exc}"

    reply = str(getattr(turn, "margot_text", "") or "").strip()
    if reply:
        _post_message(
            channel=channel,
            thread_ts=thread_ts,
            text=f"*Margot → Telegram*\n{_clip(reply)}",
        )
    return "ok"


__all__ = [
    "BRIDGE_EVENT_TYPE",
    "bridge_enabled",
    "handle_slack_message_event",
    "mirror_telegram_turn",
    "slack_token",
    "strengthening_channel",
]
