"""swarm/review_authority.py — who may decide a draft_review draft, and where.

Founder rulings 21/10/2026: CFO spend, CMO ad spend and CS refunds wait for
the founder, with zero auto-approval. They all resolve through
draft_review.mark_reaction, so this module binds that decision:

  * Only the Telegram user named by TAO_FOUNDER_TELEGRAM_USER_ID may decide.
    Unset or not a positive decimal user ID -> no reaction decides anything
    (fail closed, logged as an error). A reactor with no valid integer ID
    never matches.
  * A reaction counts only in the chat the draft was posted to. Telegram
    message ids are unique per chat, not globally. A draft with no recorded
    chat (saved before chats were recorded) is never decided; re-post it.
  * A review ask that never reached the founder (post failure, PII abort,
    or any non-"pending" result) is reported so money callers can block.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

log = logging.getLogger("swarm.review_authority")

FOUNDER_TELEGRAM_USER_ID_ENV = "TAO_FOUNDER_TELEGRAM_USER_ID"
REACTION_EMOJI = ("👍", "❌", "⏳")
_TELEGRAM_USER_ID = re.compile(r"[1-9][0-9]{0,19}")


def telegram_user_id(value: Any) -> str | None:
    """`value` as a positive decimal Telegram user ID, else None (null, bool, junk).

    Matched exactly, never trimmed: a padded value such as " 8000001" is malformed.
    """
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    text = str(value)
    return text if _TELEGRAM_USER_ID.fullmatch(text) else None


def founder_telegram_user_id() -> str:
    """The only Telegram user whose reaction may decide a draft. "" if unset or malformed."""
    raw = os.environ.get(FOUNDER_TELEGRAM_USER_ID_ENV) or ""
    founder = telegram_user_id(raw)
    if raw and founder is None:
        log.error("%s is not a positive decimal Telegram user ID; no reaction "
                  "can approve anything until it is fixed", FOUNDER_TELEGRAM_USER_ID_ENV)
    return founder or ""


def review_chat_id() -> str:
    """The chat review asks are posted to: REVIEW_CHAT_ID, else the alert chat."""
    from . import config
    return str(os.environ.get("REVIEW_CHAT_ID") or config.TELEGRAM_CHAT_ID or "")


def forward_reaction(reaction: dict[str, Any]) -> None:
    """Pass a Telegram message_reaction to draft_review with its chat and actor."""
    from . import draft_review
    msg_id = str(reaction.get("message_id", ""))
    chat_id = str((reaction.get("chat") or {}).get("id", ""))
    actor_id = telegram_user_id((reaction.get("user") or {}).get("id"))
    if not (msg_id and chat_id):
        return
    for r in reaction.get("new_reaction", []):
        emoji = r.get("emoji", "")
        if emoji in REACTION_EMOJI:
            draft_review.mark_reaction(review_message_id=msg_id, emoji=emoji,
                                       actor_user_id=actor_id, chat_id=chat_id)
            log.info("reaction %s on msg %s chat %s from user %s",
                     emoji, msg_id, chat_id, actor_id)


def find_reviewed_draft(
    snap: dict[str, dict[str, Any]], review_message_id: str, chat_id: str | None,
) -> tuple[str | None, dict[str, Any] | None]:
    """The draft posted as `review_message_id` in `chat_id`, else (None, None)."""
    if chat_id is None:
        return None, None
    for did, rec in snap.items():
        if str(rec.get("review_message_id")) != str(review_message_id):
            continue
        posted_chat = rec.get("review_chat_id")
        if not posted_chat:
            # Saved before the posting chat was recorded: the same message id
            # in another chat is a different message, so it cannot be bound.
            log.warning("draft %s: reaction REJECTED: no recorded review chat; "
                        "re-post it for review", did)
            _audit_rejection(did, rec, None, None,
                             "draft has no recorded review chat; re-post it for review")
        elif str(chat_id) == str(posted_chat):
            return did, rec
    return None, None


def authorise_reaction(
    draft_id: str, record: dict[str, Any], emoji: str, actor_user_id: str | None,
) -> bool:
    """True only if the founder made this reaction. Rejections are audited."""
    founder_id = founder_telegram_user_id()
    actor = telegram_user_id(actor_user_id)
    if founder_id and actor == founder_id:
        return True
    if not founder_id:
        reason = "founder Telegram user ID not configured"
        log.error("draft %s: %s reaction REJECTED: %s is unset or malformed, so no "
                  "reaction can approve anything until it is set",
                  draft_id, emoji, FOUNDER_TELEGRAM_USER_ID_ENV)
    else:
        reason = "reaction not from the founder"
        log.warning("draft %s: %s reaction from user %s REJECTED (%s)",
                    draft_id, emoji, actor or "?", reason)
    _audit_rejection(draft_id, record, emoji, actor, reason)
    return False


def _audit_rejection(draft_id: str, record: dict[str, Any], emoji: str | None,
                     actor: str | None, reason: str) -> None:
    from . import audit_emit, draft_review
    draft_review._append_jsonl(draft_review._drafts_jsonl(), {
        **record, "audit_event": "draft_reaction_rejected",
        "rejected_actor_user_id": actor or None, "rejected_reason": reason})
    audit_emit.row("draft_reaction_rejected", record.get("drafted_by_role", "Scribe"),
                   draft_id=draft_id, emoji=emoji, actor_user_id=actor or None,
                   reason=reason)


def send_halted(test_mode: bool) -> bool:
    """True when an approved draft must not send now: swarm off (outside test
    mode) or the kill switch engaged. Called right before the send, so a /panic
    earlier in the same update batch, or from the dashboard, still stops it."""
    from . import kill_switch
    swarm_off = os.environ.get("TAO_SWARM_ENABLED", "0") != "1" and not test_mode
    return swarm_off or kill_switch.is_active()


def review_undelivered(out: Any, what: str) -> str:
    """"" when a post_draft result is a review ask awaiting the founder; else why not.

    Money callers report "pending" only when this returns "". A failed post is
    saved "queued", a PII abort returns "aborted_pii", an auto-tier result
    returns "sent"/"deferred"; none of them reached the founder, and nothing
    re-posts them, so the caller must report "blocked". Logs the reason.
    """
    status = out.get("status") if isinstance(out, dict) else None
    if status == "aborted_pii":
        reason = "aborted (PII check failed; review ask never posted)"
    elif status != "pending" or not out.get("review_message_id"):
        reason = f"undelivered (status={status or 'unknown'})"
    else:
        return ""
    log.error("%s BLOCKED: founder review %s; nothing re-posts it", what, reason)
    return reason


__all__ = [
    "FOUNDER_TELEGRAM_USER_ID_ENV",
    "authorise_reaction",
    "find_reviewed_draft",
    "forward_reaction",
    "founder_telegram_user_id",
    "review_chat_id",
    "review_undelivered",
    "send_halted",
    "telegram_user_id",
]
