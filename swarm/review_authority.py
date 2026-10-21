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
  * A Telegram /resume or /resume-confirm counts only when the founder sent it
    in person (sent_by_founder): not another member, not an anonymous admin or
    a channel (sender_chat), not a bot, never with the founder ID unset.
    /panic stays open to anyone in the alert chat: it fails safe.
"""
from __future__ import annotations

import json
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


def sent_by_founder(msg: dict[str, Any]) -> bool:
    """True only for a message the founder sent in person: a `from` user that is
    not a bot, whose ID equals TAO_FOUNDER_TELEGRAM_USER_ID, with no sender_chat
    (a message sent on behalf of a chat: an anonymous admin or a channel).
    False when the founder ID is unset or malformed (fail closed)."""
    founder = founder_telegram_user_id()
    sender = msg.get("from")
    if not founder or msg.get("sender_chat") is not None or not isinstance(sender, dict):
        return False
    if sender.get("is_bot") is not False:
        return False
    return telegram_user_id(sender.get("id")) == founder


def command_context(msg: dict[str, Any]) -> dict[str, Any]:
    """kill_switch.handle_command keywords for a Telegram message: its own date
    (Telegram's clock) and whether the founder sent it in person."""
    date = msg.get("date")
    sent_at = float(date) if isinstance(date, (int, float)) and not isinstance(date, bool) else None
    return {"sent_at": sent_at, "from_founder": sent_by_founder(msg)}


def review_chat_id() -> str:
    """The chat review asks are posted to: REVIEW_CHAT_ID, else the alert chat."""
    from . import config
    return str(os.environ.get("REVIEW_CHAT_ID") or config.TELEGRAM_CHAT_ID or "")


def added_emoji(reaction: dict[str, Any]) -> list[str]:
    """Review emoji in new_reaction that were not in old_reaction, in order.

    A 👍 still on the card (say, from before a kill-switch deferral) is in both
    lists, so adding or removing another emoji never re-fires it."""
    def emoji(key: str) -> list[str]:
        return [r.get("emoji", "") for r in reaction.get(key) or [] if isinstance(r, dict)]
    old = set(emoji("old_reaction"))
    return [e for e in dict.fromkeys(emoji("new_reaction")) if e in REACTION_EMOJI and e not in old]


def forward_reaction(reaction: dict[str, Any]) -> None:
    """Pass each emoji the reactor just added to draft_review, with chat and actor.

    Never raises: a failure is logged and audited, so the poller still writes
    its offset (and reaches /panic later in the batch) and the webhook answers."""
    from . import draft_review
    msg_id = str(reaction.get("message_id", ""))
    chat_id = str((reaction.get("chat") or {}).get("id", ""))
    actor_id = telegram_user_id((reaction.get("user") or {}).get("id"))
    if not (msg_id and chat_id):
        return
    for emoji in added_emoji(reaction):
        try:
            draft_review.mark_reaction(review_message_id=msg_id, emoji=emoji,
                                       actor_user_id=actor_id, chat_id=chat_id)
            log.info("reaction %s on msg %s chat %s from user %s",
                     emoji, msg_id, chat_id, actor_id)
        except Exception as exc:
            log.exception("reaction %s on msg %s chat %s from user %s FAILED; the draft "
                          "may be unchanged or part-way", emoji, msg_id, chat_id, actor_id)
            try:
                from . import audit_emit
                audit_emit.row("draft_reaction_failed", "Scribe", emoji=emoji,
                               actor_user_id=actor_id, review_message_id=msg_id,
                               chat_id=chat_id, error=f"{type(exc).__name__}: {exc}")
            except Exception:
                log.exception("could not audit the failed reaction")


def webhook_reaction(update: dict[str, Any]) -> dict[str, Any]:
    """Webhook entry for a message_reaction update; drops replays.

    Telegram redelivers updates, and a captured one can be replayed. The last
    processed update_id is persisted; an update at or below it, or with no
    integer update_id, is dropped, so a replayed founder 👍 cannot re-approve."""
    uid = update.get("update_id")
    if isinstance(uid, bool) or not isinstance(uid, int) or not _claim_update_id(uid):
        log.warning("webhook reaction update_id=%r dropped: replayed, stale or missing", uid)
        return {"ok": True, "ignored": "stale or missing update_id"}
    forward_reaction(update["message_reaction"])
    return {"ok": True}


def webhook_kill_switch(update: dict[str, Any]) -> dict[str, Any] | None:
    """/panic, /resume, /resume-confirm sent to the webhook from the alert chat.

    In webhook mode getUpdates receives nothing, so the poller's handler never
    runs; this applies the same kill_switch.handle_command. /panic is always
    honoured, even late or redelivered. A /resume must carry an update_id newer
    than the last processed one, so a stale /resume cannot undo a later panic.
    None when the update is not one of these commands from the alert chat.
    """
    from . import config, kill_switch
    observed = kill_switch.panic_id()  # before any check: a later panic wins
    msg = update.get("message") or {}
    text = (msg.get("text") or "").strip()
    alert_chat = str(config.TELEGRAM_CHAT_ID or "")
    if not (alert_chat and str((msg.get("chat") or {}).get("id", "")) == alert_chat):
        return None
    if not text.lower().startswith(("/panic", "/resume")):
        return None
    uid = update.get("update_id")
    fresh = not isinstance(uid, bool) and isinstance(uid, int) and _claim_update_id(uid)
    if text.lower().startswith("/resume") and not fresh:
        log.warning("webhook %s update_id=%r dropped: stale or missing", text.split()[0], uid)
        return {"ok": True, "ignored": "stale or missing update_id"}
    return {"ok": True, "kill_switch": kill_switch.handle_command(
        text, observed_id=observed, **command_context(msg))}


def _claim_update_id(uid: int) -> bool:
    """Record uid as processed. False if it is not newer than the last one (or unreadable)."""
    from . import draft_decision, draft_review
    path = draft_review._state_dir() / "telegram_webhook_update_id.json"
    with draft_decision.snapshot_lock():
        try:
            last = int(json.loads(path.read_text())["last_update_id"]) if path.exists() else -1
        except Exception:
            log.error("%s unreadable; dropping webhook reactions until it is fixed", path)
            return False
        if uid <= last:
            return False
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"last_update_id": uid}))
        tmp.replace(path)
    return True


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
    "added_emoji",
    "authorise_reaction",
    "find_reviewed_draft",
    "forward_reaction",
    "founder_telegram_user_id",
    "review_chat_id",
    "review_undelivered",
    "send_halted",
    "telegram_user_id",
    "webhook_kill_switch",
    "webhook_reaction",
]
