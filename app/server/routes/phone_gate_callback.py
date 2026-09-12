"""Telegram callback_query -> phone-gate resolve (RA-7530).

phone.py's own docstring always said `/gate/{gid}/resolve` is "bot-internal,
called from callback" — nothing ever called it. An Approve/Deny tap on a
phone-gate card arrives as a `callback_query` update, never a `message`, and
the webhook only read `data["message"]`. Kept in its own module (not inlined
into webhooks.py) so webhooks.py's already-over-baseline line count doesn't
grow further.
"""
from __future__ import annotations

import json
import logging
import urllib.request

from fastapi import HTTPException

from .phone import ResolveBody, resolve_gate

log = logging.getLogger("pi-ceo.phone")


def answer_callback_query(token: str, callback_query_id: str) -> None:
    """Fire-and-forget — clears the loading spinner Telegram puts on a tapped button."""
    payload = json.dumps({"callback_query_id": callback_query_id}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/answerCallbackQuery",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8):
            pass
    except Exception as exc:  # noqa: BLE001
        log.warning("Telegram answerCallbackQuery failed: %s", exc)


async def handle_gate_callback(token: str, callback: dict) -> dict:
    """Resolve a phone-gate Approve/Deny tap. Always returns {"ok": True} to Telegram."""
    cb_id = callback.get("id", "")
    cb_data = callback.get("data", "") or ""
    user_id = (callback.get("from") or {}).get("id")
    action, _, gate_id = cb_data.partition(":")
    if action in ("approve", "deny") and gate_id:
        status = "approved" if action == "approve" else "denied"
        try:
            await resolve_gate(gate_id, ResolveBody(status=status, by_user_id=user_id))
        except HTTPException as exc:
            log.warning("gate resolve via callback failed gid=%s: %s", gate_id, exc.detail)
    if token and cb_id:
        answer_callback_query(token, cb_id)
    return {"ok": True}
