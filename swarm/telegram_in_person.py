"""telegram_in_person.py — is a Telegram message the sender's own act, made now?

Split out of review_authority.py (300-line convention). Used by
review_authority.sent_by_founder: a founder /resume must be the founder's own
command, dated when he sent it, so it can be ordered against a panic.
"""
from __future__ import annotations

from typing import Any

# A forward keeps the original sender in these fields but gets a fresh date and
# `from` = whoever forwarded it, so it is never the founder's own command.
_FORWARD_KEYS = ("forward_origin", "forward_from", "forward_from_chat",
                 "forward_sender_name", "forward_date", "is_automatic_forward")
# Sent by something acting for the founder, not by the founder at that moment:
# a business bot, an inline bot. Their `date` says when it arrived, not when he
# decided, so it cannot be ordered against a panic.
_AUTOMATED_KEYS = ("sender_business_bot", "via_bot")


def not_in_person(msg: dict[str, Any]) -> bool:
    """A forward, an automated sender, or a scheduled / away / greeting message
    (is_from_offline: Telegram stamps the delivery date, so a /resume scheduled
    before a panic would read as sent after it)."""
    if "is_from_offline" in msg and msg["is_from_offline"] is not False:
        return True
    return any(k in msg for k in _FORWARD_KEYS + _AUTOMATED_KEYS)
