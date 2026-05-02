"""
swarm/draft_review.py — RA-1839: HITL gate state machine for outbound Telegram.

Implements telegram-draft-for-review SKILL.md:
  pending → sent (👍) | revise (❌) | deferred (⏳) | expired (no-reaction-24h)

State persisted to .harness/swarm/telegram_drafts.jsonl (append-only).
Active drafts kept in .harness/swarm/telegram_drafts.json (latest snapshot).

Design rules:
  * No silent send. No silent drop. Every transition writes an audit row.
  * Kill-switch aware: TAO_SWARM_ENABLED=0 halts the SEND, not the post-to-review.
  * REVIEW_CHAT_ID env var distinguishes review chat from destination chat.
  * Test mode (TAO_DRAFT_REVIEW_TEST=1): does NOT post to real Telegram;
    accepts synthetic reactions via mark_reaction() for unit testing.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

log = logging.getLogger("swarm.draft_review")

DraftStatus = Literal["pending", "sent", "revise", "deferred", "expired", "queued", "aborted_pii"]
ReactionEmoji = Literal["👍", "❌", "⏳"]

DEFAULT_TIMEOUT_HOURS = 24
TEST_MODE = os.environ.get("TAO_DRAFT_REVIEW_TEST", "0") == "1"


def _config():
    """Lazy import to avoid pulling config at module import time."""
    from . import config as _cfg
    return _cfg


def _state_dir() -> Path:
    cfg = _config()
    d = cfg.SWARM_LOG_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _drafts_jsonl() -> Path:
    return _state_dir() / "telegram_drafts.jsonl"


def _drafts_snapshot() -> Path:
    return _state_dir() / "telegram_drafts.json"


def _audit_swarm_jsonl() -> Path:
    return _state_dir() / "swarm.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(p: Path, row: dict[str, Any]) -> None:
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _load_snapshot() -> dict[str, dict[str, Any]]:
    p = _drafts_snapshot()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        log.warning("draft snapshot unreadable — starting fresh")
        return {}


def _save_snapshot(state: dict[str, dict[str, Any]]) -> None:
    p = _drafts_snapshot()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(p)


def _post_review_message(text: str) -> str | None:
    """Post a review-ask message to REVIEW_CHAT_ID. Returns message_id or None."""
    if TEST_MODE:
        return f"test-msg-{uuid.uuid4().hex[:8]}"
    cfg = _config()
    review_chat = os.environ.get("REVIEW_CHAT_ID") or cfg.TELEGRAM_CHAT_ID
    token = cfg.TELEGRAM_BOT_TOKEN
    if not (review_chat and token):
        log.warning("REVIEW_CHAT_ID + TELEGRAM_BOT_TOKEN required for draft review")
        return None
    import urllib.request
    payload = json.dumps({
        "chat_id": review_chat,
        "text": text,
        "parse_mode": "HTML",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return str(data.get("result", {}).get("message_id", ""))
    except Exception as exc:
        log.warning("review-post failed: %s", exc)
        return None


def post_draft(
    *,
    draft_text: str,
    destination_chat_id: str,
    drafted_by_role: str,
    originating_intent_id: str | None = None,
    destination_thread_id: str | None = None,
    timeout_hours: int = DEFAULT_TIMEOUT_HOURS,
) -> dict[str, Any]:
    """Queue a draft for review. Posts to REVIEW_CHAT_ID; returns draft_id + status.

    Caller does NOT block; the reaction listener resolves the final state on a
    subsequent orchestrator cycle.

    PII redaction (RA-1839 gap-1 close): every outbound draft is run through
    pii-redactor at strictness=standard before storage and review-post. If
    precision drops below 0.95, the draft is aborted with audit row and never
    reaches the review chat. The destination chat receives a re-redaction at
    strictness=high in _do_send when REVIEW_CHAT_ID differs.
    """
    from . import pii_redactor
    pii_pre = pii_redactor.redact(
        draft_text,
        context="telegram_send",
        strictness="standard",
    )
    if not pii_pre.passed:
        from . import audit_emit
        audit_emit.row(
            "draft_pii_aborted",
            drafted_by_role,
            precision=pii_pre.precision_score,
            redaction_count=pii_pre.redaction_count,
            destination_chat_id=destination_chat_id,
            originating_intent_id=originating_intent_id,
        )
        log.error(
            "Draft aborted: PII precision %.2f < 0.95 (count=%d)",
            pii_pre.precision_score, pii_pre.redaction_count,
        )
        return {
            "draft_id": None,
            "review_message_id": None,
            "status": "aborted_pii",
            "redaction_count": pii_pre.redaction_count,
            "precision_score": pii_pre.precision_score,
        }
    draft_text = pii_pre.redacted_payload  # use redacted text from here on

    draft_id = uuid.uuid4().hex[:12]
    now = _now_iso()
    expires = (datetime.now(timezone.utc) + timedelta(hours=timeout_hours)).isoformat()

    review_text = (
        f"✏️ <b>DRAFT</b> ({drafted_by_role}) — for chat <code>{destination_chat_id}</code>\n"
        f"─────────────────────────────────\n"
        f"{draft_text}\n"
        f"─────────────────────────────────\n"
        f"React 👍 to send · ❌ to revise · ⏳ to delay 24h"
    )
    review_message_id = _post_review_message(review_text)

    record = {
        "draft_id": draft_id,
        "review_message_id": review_message_id,
        "destination_chat_id": destination_chat_id,
        "destination_thread_id": destination_thread_id,
        "drafted_by_role": drafted_by_role,
        "originating_intent_id": originating_intent_id,
        "draft_text": draft_text,
        "status": "pending" if review_message_id else "queued",
        "drafted_at": now,
        "expires_at": expires,
        "transitions": [],
    }

    _append_jsonl(_drafts_jsonl(), {**record, "audit_event": "draft_posted"})
    from . import audit_emit
    audit_emit.row("draft_posted", drafted_by_role,
                   draft_id=draft_id,
                   destination_chat_id=destination_chat_id)

    snap = _load_snapshot()
    snap[draft_id] = record
    _save_snapshot(snap)

    log.info("Draft %s queued for review (msg=%s)", draft_id, review_message_id)
    return {
        "draft_id": draft_id,
        "review_message_id": review_message_id,
        "status": record["status"],
    }


def mark_reaction(
    *,
    review_message_id: str,
    emoji: ReactionEmoji,
) -> dict[str, Any] | None:
    """Apply a 👍/❌/⏳ reaction to a draft. Returns the updated draft record."""
    snap = _load_snapshot()
    target = None
    target_id = None
    for did, rec in snap.items():
        if str(rec.get("review_message_id")) == str(review_message_id):
            target = rec
            target_id = did
            break
    if not target:
        log.debug("reaction on unknown review_message_id=%s", review_message_id)
        return None

    if target["status"] not in ("pending", "deferred"):
        log.info("ignoring reaction on draft %s in state %s", target_id, target["status"])
        return target

    cfg = _config()
    swarm_enabled = os.environ.get("TAO_SWARM_ENABLED", "0") == "1"

    if emoji == "👍":
        if not swarm_enabled and not TEST_MODE:
            target["status"] = "deferred"
            target["transitions"].append({"ts": _now_iso(), "to": "deferred",
                                          "reason": "kill-switch active; send halted"})
        else:
            sent_ok = _do_send(target) if not TEST_MODE else True
            target["status"] = "sent" if sent_ok else "revise"
            target["transitions"].append({"ts": _now_iso(),
                                          "to": target["status"],
                                          "reason": "approved" if sent_ok else "send_failed"})
    elif emoji == "❌":
        target["status"] = "revise"
        target["transitions"].append({"ts": _now_iso(), "to": "revise",
                                      "reason": "rejected"})
    elif emoji == "⏳":
        new_expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        target["expires_at"] = new_expires
        target["status"] = "deferred"
        target["transitions"].append({"ts": _now_iso(), "to": "deferred",
                                      "reason": "delayed +24h",
                                      "new_expires_at": new_expires})

    _append_jsonl(_drafts_jsonl(), {**target, "audit_event": "draft_reaction"})
    from . import audit_emit
    audit_emit.row("draft_reaction", target.get("drafted_by_role", "Scribe"),
                   draft_id=target_id, emoji=emoji, status=target["status"])
    snap[target_id] = target
    _save_snapshot(snap)
    return target


def _do_send(record: dict[str, Any]) -> bool:
    """Send the approved draft via Telegram Bot API. Returns True on 200."""
    if TEST_MODE:
        return True
    cfg = _config()
    token = cfg.TELEGRAM_BOT_TOKEN
    if not token:
        return False

    # ── PII re-redact at strictness=high if destination differs from review chat ──
    # post_draft already standard-redacted draft_text; this catches the case
    # where the operator approved while reading review-context, but the
    # destination chat (e.g. external-team Telegram group) needs stricter
    # name/attendee redaction. SKILL.md §"Where the redactor sits" item 2.
    review_chat = os.environ.get("REVIEW_CHAT_ID")
    send_text = record["draft_text"]
    if review_chat and str(record["destination_chat_id"]) != str(review_chat):
        from . import pii_redactor
        pii_send = pii_redactor.redact(
            send_text,
            context="telegram_send",
            strictness="high",
        )
        if not pii_send.passed:
            from . import audit_emit
            audit_emit.row(
                "draft_send_pii_aborted",
                record.get("drafted_by_role", "Scribe"),
                draft_id=record.get("draft_id"),
                precision=pii_send.precision_score,
                redaction_count=pii_send.redaction_count,
            )
            log.error(
                "Send aborted: PII precision %.2f < 0.95 (draft=%s)",
                pii_send.precision_score, record.get("draft_id"),
            )
            return False
        send_text = pii_send.redacted_payload

    import urllib.request
    payload = {
        "chat_id": record["destination_chat_id"],
        "text": send_text,
    }
    if record.get("destination_thread_id"):
        payload["message_thread_id"] = int(record["destination_thread_id"])
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except Exception as exc:
        log.warning("approved-draft send failed: %s", exc)
        return False


def expire_overdue() -> int:
    """Sweep pending drafts past expires_at — mark expired. Returns count expired."""
    now = datetime.now(timezone.utc)
    snap = _load_snapshot()
    expired = 0
    for did, rec in snap.items():
        if rec["status"] not in ("pending", "deferred"):
            continue
        try:
            exp = datetime.fromisoformat(rec["expires_at"])
        except Exception:
            continue
        if exp < now:
            rec["status"] = "expired"
            rec["transitions"].append({"ts": _now_iso(), "to": "expired",
                                       "reason": "no reaction in window"})
            _append_jsonl(_drafts_jsonl(), {**rec, "audit_event": "draft_expired"})
            from . import audit_emit
            audit_emit.row("draft_expired", rec.get("drafted_by_role", "Scribe"),
                           draft_id=did)
            expired += 1
    if expired:
        _save_snapshot(snap)
    return expired


def list_pending() -> list[dict[str, Any]]:
    """Return all pending or deferred drafts."""
    snap = _load_snapshot()
    return [r for r in snap.values() if r["status"] in ("pending", "deferred")]


__all__ = ["post_draft", "mark_reaction", "expire_overdue", "list_pending"]
