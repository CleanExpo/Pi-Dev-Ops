"""telegram_webhook_ownership.py — RA-7434 setWebhook ownership guard.

``setWebhook`` silently converts a Telegram bot from polling to webhook mode.
If a token for a bot polled somewhere else (PiMargot_bot, via the Hermes
gateway) ever reaches this service, an unconditional ``setWebhook`` kills that
poller with no error anywhere. So the intake loop asks Telegram whose token it
holds and proceeds only for the allow-listed bot id.

Split out of ``telegram_intake.py`` rather than added to it: that file was 262
lines against the repo's 300-line convention, and this guard is a separate
concern with its own network call.
"""
from __future__ import annotations

import json
import os
import urllib.request

def _owned_bot_id() -> str:
    return os.environ.get("TELEGRAM_OWNED_BOT_ID", "").strip()


def _telegram_get_me_id(token: str) -> str:
    """The bot id Telegram reports for this token (``getMe``)."""
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/getMe", method="GET")
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if not body.get("ok"):
        raise RuntimeError(body.get("description") or str(body))
    return str((body.get("result") or {}).get("id") or "")


def _webhook_ownership_error(token: str) -> str:
    """Why setWebhook must NOT run for this token, or "" when the bot is ours.

    RA-7434: setWebhook silently converts a bot from polling to webhook mode. If
    a token for a bot polled elsewhere (PiMargot_bot via the Hermes gateway) ever
    lands here, an unconditional setWebhook kills that poller. So the intake loop
    asks Telegram whose token this is and only proceeds for the allow-listed id.
    Unset allow-list means refuse.
    """
    owned = _owned_bot_id()
    if not owned:
        return "TELEGRAM_OWNED_BOT_ID unset — refusing setWebhook (RA-7434)"
    try:
        bot_id = _telegram_get_me_id(token)
    except Exception as exc:  # noqa: BLE001
        return f"getMe failed — refusing setWebhook (RA-7434): {str(exc)[:120]}"
    if bot_id != owned:
        return (
            f"token belongs to bot {bot_id or '?'}, not the owned bot {owned} — "
            "refusing setWebhook (RA-7434)"
        )
    return ""
