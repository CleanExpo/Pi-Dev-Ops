"""telegram_webhook_secret.py — the /webhook/telegram secret-token check.

Split out of ``webhooks.py`` (1264 lines against the 300-line convention)
when that route gained message_reaction handling for founder draft
approvals, so the route could take the new branch without growing.
"""
from __future__ import annotations

import hmac

from fastapi import HTTPException, Request

from .. import config


def require_telegram_secret(request: Request) -> None:
    """Raise unless X-Telegram-Bot-Api-Secret-Token matches the configured secret."""
    expected_secret = config.TELEGRAM_WEBHOOK_SECRET
    # RA-1004: Require the secret to be configured. If it is absent the endpoint
    # would otherwise be open to anyone — mirror the pattern used for GitHub
    # webhook secret (webhooks.py).
    if not expected_secret:
        raise HTTPException(500, "Telegram webhook secret not configured")
    # The bot id (the token's prefix) is what config falls back to when no
    # secret is set, and it is not secret: it authorises nothing here.
    bot_id = (config.TELEGRAM_BOT_TOKEN or "").split(":", 1)[0]
    if bot_id and hmac.compare_digest(expected_secret, bot_id):
        raise HTTPException(500, "set TELEGRAM_WEBHOOK_SECRET explicitly; the bot id is public")
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    # RA-1004 follow-up: use hmac.compare_digest to avoid a timing-side-channel
    # leak of the configured secret. Same pattern as the morning-intel handler.
    if not hmac.compare_digest(secret, expected_secret):
        raise HTTPException(401, "Invalid Telegram webhook secret")
