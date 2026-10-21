"""swarm/draft_decision.py — apply a founder reaction or an expiry to a draft_review draft.

Split out of draft_review.py (file-length ratchet); draft_review re-exports
mark_reaction and expire_overdue, so callers are unchanged.

The webhook (event-loop thread) and the orchestrator thread both write
telegram_drafts.json. Every load-modify-save holds snapshot_lock(), one
fcntl.flock on a sibling lock file, so neither can save a stale copy over the
other's change. A 👍 moves the draft to "sending" and saves that BEFORE the
send, so a second 👍 or a concurrent writer can never send it twice or put it
back to pending. A process that dies mid-send leaves the draft "sending",
which nothing re-sends or expires: a stuck draft, never a duplicate send.
"""
from __future__ import annotations

import fcntl
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from .review_authority import authorise_reaction, find_reviewed_draft, send_halted

log = logging.getLogger("swarm.draft_review")

_OPEN = ("pending", "deferred")


def _dr():
    from . import draft_review
    return draft_review


@contextmanager
def snapshot_lock() -> Iterator[None]:
    """Exclusive lock across one load-modify-save of the drafts snapshot. Not re-entrant."""
    path = _dr()._drafts_snapshot().with_suffix(".lock")
    with path.open("a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _transition(target: dict[str, Any], to: str, reason: str, actor: str | None,
                **extra: Any) -> None:
    target["status"] = to
    target["transitions"].append({"ts": _dr()._now_iso(), "to": to, "reason": reason,
                                  "actor_user_id": actor, **extra})
    target["decided_by_user_id"] = actor


def _record(snap: dict[str, Any], target_id: str, target: dict[str, Any], emoji: str) -> None:
    """Audit the decision and save the snapshot (caller holds snapshot_lock)."""
    from . import audit_emit
    dr = _dr()
    dr._append_jsonl(dr._drafts_jsonl(), {**target, "audit_event": "draft_reaction"})
    audit_emit.row("draft_reaction", target.get("drafted_by_role", "Scribe"), draft_id=target_id,
                   emoji=emoji, status=target["status"],
                   actor_user_id=target.get("decided_by_user_id"))
    snap[target_id] = target
    dr._save_snapshot(snap)


def _decide(target: dict[str, Any], emoji: str, actor: str | None) -> bool:
    """Apply the emoji to an open draft. True when a 👍 cleared it to send now."""
    if emoji == "👍":
        if send_halted(_dr().TEST_MODE):
            _transition(target, "deferred", "kill-switch active; send halted", actor)
            return False
        _transition(target, "sending", "approved; sending", actor)
        return True
    if emoji == "❌":
        _transition(target, "revise", "rejected", actor)
    else:  # ⏳
        new_expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        target["expires_at"] = new_expires
        _transition(target, "deferred", "delayed +24h", actor, new_expires_at=new_expires)
    return False


def mark_reaction(
    *,
    review_message_id: str,
    emoji: str,
    actor_user_id: str | None = None,
    chat_id: str | None = None,
) -> dict[str, Any] | None:
    """Apply the founder's 👍/❌/⏳ to the draft posted as review_message_id in chat_id.

    Anyone else, another chat, or no founder ID configured -> None, nothing changes."""
    dr = _dr()
    with snapshot_lock():
        snap = dr._load_snapshot()
        target_id, target = find_reviewed_draft(snap, review_message_id, chat_id)
        if not target:
            log.debug("reaction on unknown review_message_id=%s", review_message_id)
            return None
        if not authorise_reaction(target_id, target, emoji, actor_user_id):
            return None
        if target["status"] not in _OPEN:
            log.info("ignoring reaction on draft %s in state %s", target_id, target["status"])
            return target
        send_now = _decide(target, emoji, actor_user_id)
        _record(snap, target_id, target, emoji)
    if not send_now:
        return target
    sent_ok = dr._do_send(target) if not dr.TEST_MODE else True
    with snapshot_lock():
        snap = dr._load_snapshot()
        target = snap.get(target_id, target)
        _transition(target, "sent" if sent_ok else "revise",
                    "approved" if sent_ok else "send_failed", actor_user_id)
        _record(snap, target_id, target, emoji)
    return target


def _overdue(rec: dict[str, Any], now: datetime) -> bool:
    if rec["status"] not in _OPEN:
        return False
    try:
        return datetime.fromisoformat(rec["expires_at"]) < now
    except Exception:
        return False


def expire_overdue() -> int:
    """Sweep pending drafts past expires_at — mark expired. Returns count expired."""
    from . import audit_emit
    dr = _dr()
    now = datetime.now(timezone.utc)
    with snapshot_lock():
        snap = dr._load_snapshot()
        expired = [did for did, rec in snap.items() if _overdue(rec, now)]
        for did in expired:
            rec = snap[did]
            rec["status"] = "expired"
            rec["transitions"].append({"ts": dr._now_iso(), "to": "expired",
                                       "reason": "no reaction in window"})
            dr._append_jsonl(dr._drafts_jsonl(), {**rec, "audit_event": "draft_expired"})
            audit_emit.row("draft_expired", rec.get("drafted_by_role", "Scribe"), draft_id=did)
        if expired:
            dr._save_snapshot(snap)
    return len(expired)


__all__ = ["expire_overdue", "mark_reaction", "snapshot_lock"]
