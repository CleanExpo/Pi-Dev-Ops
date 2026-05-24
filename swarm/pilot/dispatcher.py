"""Dispatcher — Telegram sendMessage + pilot_suggestion_messages persistence.

Per ADR 003: stores chat_id+message_id for every sent card so feedback
handlers can call editMessageReplyMarkup when the user taps a button.
"""
import os

import requests

from swarm.pilot.types import RawCandidate


def send(message: dict, candidate: RawCandidate, memory) -> int:
    """Send a suggestion card and persist the message link.

    Args:
        message: Telegram sendMessage payload from composer.format().
        candidate: the RawCandidate being sent.
        memory: Memory instance (injected — never imported here).

    Returns:
        suggestion_id as stored in pilot_suggestions.
    """
    token = os.environ["PILOT_BOT_TOKEN"]
    chat_id = int(os.environ["PILOT_BOT_CHAT_ID"])
    tenant_slug = os.environ.get("PILOT_TENANT_SLUG", "phill")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": message["text"],
            "reply_markup": message.get("reply_markup", {}),
        },
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")

    message_id = data["result"]["message_id"]
    suggestion_id = memory.record_suggestion(
        fingerprint=candidate.fingerprint,
        headline=candidate.headline,
        pillar=candidate.pillar,
        effort=candidate.effort,
        source=candidate.source,
        confidence=candidate.confidence,
        body_json={"body": candidate.body},
    )
    memory.record_message(
        suggestion_id=suggestion_id,
        chat_id=chat_id,
        message_id=message_id,
        tenant_slug=tenant_slug,
    )
    return suggestion_id
