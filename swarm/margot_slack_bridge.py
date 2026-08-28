"""Bidirectional Slack <-> Telegram strengthening bridge for Margot.

Telegram remains Phill's mobile front door and authority surface. Each
Telegram-originated Margot turn may be mirrored into the private Slack
strengthening channel as one thread. Human Slack replies are review context,
not founder approvals or commands; they re-enter the same Margot conversation
and the resulting answer returns to Telegram and the same Slack thread.

Only replies whose parent carries bridge metadata are accepted. Bot messages,
top-level chatter, unrelated threads, and unconfigured deployments are ignored.
"""
from __future__ import annotations

import asyncio
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
    """Return the Slack bot token without logging or transforming it."""
    return (os.environ.get("SLACK_BOT_TOKEN") or "").strip()


def strengthening_channel() -> str:
    """Return the private Slack channel used for strengthening threads."""
    return (
        os.environ.get("SLACK_MARGOT_STRENGTHENING_CHANNEL")
        or DEFAULT_STRENGTHENING_CHANNEL
    ).strip()


def bridge_enabled() -> bool:
    """Require an explicit runtime opt-in plus a Slack token before bridging."""
    raw = (os.environ.get("SLACK_TELEGRAM_BRIDGE_ENABLED") or "0").strip().lower()
    return raw in {"1", "true", "yes", "on"} and bool(slack_token())


def _clip(text: str, limit: int = _MAX_SLACK_TEXT) -> str:
    """Bound Slack text while preserving a visible truncation marker."""
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 16)].rstrip() + "\n… [truncated]"


def _slack_api(
    method: str, payload: dict[str, Any], *, timeout_s: float = 8.0,
) -> dict[str, Any]:
    """Call one Slack Web API method synchronously for sync-only callers."""
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
        return body if isinstance(body, dict) else {"ok": False, "error": "invalid_slack_response"}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        return {"ok": False, "error": f"slack_http_{exc.code}:{body}"}
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        return {"ok": False, "error": f"slack_call_failed:{exc}"}


def _post_message(
    *, channel: str, text: str, thread_ts: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str | None:
    """Post one Slack message from a synchronous caller."""
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


async def _post_message_async(**kwargs: Any) -> str | None:
    """Post to Slack in a worker thread so urllib never blocks the event loop."""
    return await asyncio.to_thread(_post_message, **kwargs)


def _thread_parent(*, channel: str, thread_ts: str) -> dict[str, Any] | None:
    """Fetch the parent message for one Slack thread synchronously."""
    result = _slack_api(
        "conversations.replies",
        {"channel": channel, "ts": thread_ts, "limit": 1, "inclusive": True},
    )
    if not result.get("ok"):
        log.warning("margot bridge: Slack thread lookup failed (%s)", result.get("error"))
        return None
    messages = result.get("messages") or []
    if not isinstance(messages, list) or not messages:
        return None
    parent = messages[0]
    return parent if isinstance(parent, dict) else None


async def _thread_parent_async(*, channel: str, thread_ts: str) -> dict[str, Any] | None:
    """Fetch a Slack thread parent without blocking the FastAPI event loop."""
    return await asyncio.to_thread(_thread_parent, channel=channel, thread_ts=thread_ts)


def _parent_bridge_context(parent: dict[str, Any] | None) -> dict[str, str] | None:
    """Extract the original Telegram chat identity from bridge metadata."""
    if not parent:
        return None
    metadata = parent.get("metadata") or {}
    if not isinstance(metadata, dict) or metadata.get("event_type") != BRIDGE_EVENT_TYPE:
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
    metadata = {
        "event_type": BRIDGE_EVENT_TYPE,
        "event_payload": {"chat_id": chat_id, "turn_id": turn_id},
    }
    parent_ts = _post_message(
        channel=channel,
        text=f"*Telegram → Margot*\n`{turn_id or 'turn'}`\n{_clip(user_text)}",
        metadata=metadata,
    )
    if parent_ts and margot_text:
        _post_message(
            channel=channel,
            thread_ts=parent_ts,
            text=f"*Margot → Telegram*\n{_clip(margot_text)}",
        )
    return parent_ts


def _clean_human_text(text: str) -> str:
    """Remove leading bot mentions from a human Slack strengthening reply."""
    return _MENTION_RE.sub("", (text or "").strip()).strip()


def _event_basics(event: dict[str, Any]) -> tuple[dict[str, str] | None, str | None]:
    """Validate cheap Slack message invariants before any network lookup."""
    channel = str(event.get("channel") or "").strip()
    if channel != strengthening_channel():
        return None, "ignored:wrong_channel"
    if event.get("bot_id") or event.get("subtype"):
        return None, "ignored:bot_or_subtype"
    if not str(event.get("user") or "").strip():
        return None, "ignored:not_human"
    thread_ts = str(event.get("thread_ts") or "").strip()
    if not thread_ts:
        return None, "ignored:not_thread_reply"
    text = _clean_human_text(str(event.get("text") or ""))
    if not text:
        return None, "ignored:empty"
    return {
        "channel": channel,
        "thread_ts": thread_ts,
        "text": text,
        "user": str(event.get("user") or "").strip(),
        "event_ts": str(event.get("event_ts") or event.get("ts") or "").strip(),
    }, None


def _strengthening_text(text: str, slack_user: str) -> str:
    """Mark Slack input as review context so it cannot masquerade as founder authority."""
    return (
        "[Slack strengthening input; review context only, not founder approval or authority. "
        f"Reviewer={slack_user}]\n{text}"
    )


async def _already_processed(chat_id: str, message_id: str) -> bool:
    """Use durable Margot history to suppress Slack retries across process restarts."""
    if not message_id:
        return False
    from . import margot_bot  # noqa: PLC0415

    history = await asyncio.to_thread(margot_bot.load_history, chat_id, limit=50)
    return any(turn.user_message_id == message_id for turn in history)


async def _run_margot(context: dict[str, str], basics: dict[str, str]) -> Any:
    """Feed one authority-safe Slack strengthening note through the shared Margot brain."""
    from . import margot_bot  # noqa: PLC0415

    message_id = f"slack:{basics['event_ts']}" if basics["event_ts"] else "slack"
    if await _already_processed(context["chat_id"], message_id):
        return None
    return await margot_bot.handle_turn(
        chat_id=context["chat_id"],
        user_text=_strengthening_text(basics["text"], basics["user"]),
        message_id=message_id,
        _send=True,
    )


async def _publish_result(basics: dict[str, str], turn: Any) -> None:
    """Append Margot's strengthened answer to the source Slack thread."""
    reply = str(getattr(turn, "margot_text", "") or "").strip()
    if reply:
        await _post_message_async(
            channel=basics["channel"],
            thread_ts=basics["thread_ts"],
            text=f"*Margot → Telegram*\n{_clip(reply)}",
        )


async def handle_slack_message_event(event: dict[str, Any]) -> str:
    """Route one human bridge-thread reply through the same Margot conversation."""
    if not bridge_enabled():
        return "ignored:bridge_disabled"
    basics, ignored = _event_basics(event)
    if ignored or basics is None:
        return ignored or "ignored:invalid"
    parent = await _thread_parent_async(
        channel=basics["channel"], thread_ts=basics["thread_ts"],
    )
    context = _parent_bridge_context(parent)
    if not context:
        return "ignored:not_bridge_thread"
    try:
        turn = await _run_margot(context, basics)
        if turn is None:
            return "ignored:duplicate"
        await _publish_result(basics, turn)
        return "ok"
    except Exception as exc:  # noqa: BLE001
        log.exception("margot bridge: Slack -> Margot failed")
        await _post_message_async(
            channel=basics["channel"],
            thread_ts=basics["thread_ts"],
            text=f"*Bridge error*\n{_clip(str(exc), 1200)}",
        )
        return f"failed:{exc}"


__all__ = [
    "BRIDGE_EVENT_TYPE",
    "bridge_enabled",
    "handle_slack_message_event",
    "mirror_telegram_turn",
    "slack_token",
    "strengthening_channel",
]
