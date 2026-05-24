"""Callback dispatch — 5 handlers (Agree/Dismiss/Discuss/PAUSE 24h/STOP).

Per ADR 003:
- Every tap edits the card's reply_markup to a greyed processed state.
- Callback data shape: '<action>|<fingerprint>'.
- STOP sets paused-hard (halts interactive stream; L4 digest continues).
- PAUSE 24h sets paused-until-{ISO-8601-ts} (24h soft pause).
- Discuss prompts a voice reply — transcription pipeline deferred to Phase 4.
≤80 lines per [[feedback-tight-code]].
"""
import os
from datetime import datetime, timezone, timedelta

import requests


def _bot_token() -> str:
    return os.environ["PILOT_BOT_TOKEN"]


def _tenant_slug() -> str:
    return os.environ.get("PILOT_TENANT_SLUG", "phill")


def _edit_reply_markup(chat_id: int, message_id: int, marker: str) -> None:
    url = f"https://api.telegram.org/bot{_bot_token()}/editMessageReplyMarkup"
    kb = {"inline_keyboard": [[{"text": marker, "callback_data": "noop"}]]}
    try:
        requests.post(url, json={
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": kb,
        }, timeout=10)
    except requests.RequestException:
        pass  # non-fatal — state already recorded server-side


def _prompt_voice_reply(chat_id: int, suggestion_id: int) -> None:
    url = f"https://api.telegram.org/bot{_bot_token()}/sendMessage"
    try:
        requests.post(url, json={
            "chat_id": chat_id,
            "text": f"🎙 Reply with a voice message to discuss suggestion #{suggestion_id}.",
        }, timeout=10)
    except requests.RequestException:
        pass


def handle_callback(callback_data: str, suggestion_id: int, memory) -> None:
    """Dispatch a Telegram callback_data string to the matching handler.

    Args:
        callback_data: '<action>|<fingerprint>' from Telegram callback query.
        suggestion_id: DB id of the suggestion (resolved by caller).
        memory: Memory instance (injected).
    """
    action, _, _ = callback_data.partition("|")
    msg = memory.get_message_for_suggestion(suggestion_id)
    chat_id = msg["chat_id"] if msg else None
    message_id = msg["message_id"] if msg else None

    if action == "agree":
        memory.mark_response(suggestion_id, "agree", "accepted")
        if chat_id:
            _edit_reply_markup(chat_id, message_id, "✓ accepted")

    elif action == "dismiss":
        memory.mark_response(suggestion_id, "dismiss", "rejected")
        if chat_id:
            _edit_reply_markup(chat_id, message_id, "✗ dismissed")

    elif action == "discuss":
        memory.mark_response(suggestion_id, "discuss", "in_discussion")
        if chat_id:
            _edit_reply_markup(chat_id, message_id, "🎙 awaiting voice reply")
            _prompt_voice_reply(chat_id=chat_id, suggestion_id=suggestion_id)

    elif action == "pause_24h":
        until = (
            datetime.now(timezone.utc) + timedelta(hours=24)
        ).isoformat(timespec="seconds")
        memory.set_pause_state(_tenant_slug(), f"paused-until-{until}")
        if chat_id:
            _edit_reply_markup(chat_id, message_id, "⏸ paused 24h")

    elif action == "stop":
        # Halts interactive live stream only — L4 daily digest continues.
        memory.set_pause_state(_tenant_slug(), "paused-hard")
        if chat_id:
            _edit_reply_markup(chat_id, message_id, "⏹ stopped (RESUME to re-enable)")
    # unknown action: silently ignore (noop — no state mutation)
