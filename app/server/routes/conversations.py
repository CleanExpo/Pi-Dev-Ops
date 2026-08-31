"""conversations.py — the shared conversation brain (Milestone 3).

Three machines run Claude Code and each one's transcripts stay on the machine
that produced them, so no machine can search what the others did. This router
is the shared side:

  POST /api/conversations/ingest  — a machine publishes its redacted digests.
  GET  /api/conversations/search  — full-text across every machine's digests.
  GET  /api/conversations/recent  — the newest digests, optionally per machine.

RAW JSONL NEVER TRAVELS. A client sends only the digest it already redacted;
this route redacts a SECOND time before anything is written, using the existing
secret banks (`app.server.scanner` plus the transcript-specific extensions in
`scripts.sync_claude_sessions`) rather than a private regex list that could rot
apart from them. A second pass is not paranoia: the client half runs on three
machines that update independently, so "the client redacted it" is a claim this
server cannot verify, and the row is durable.

Machines authenticate with X-Pi-CEO-Secret (== TAO_INTERNAL_WEBHOOK_SECRET),
the same scheme mesh/margot/cost-report use — nodes never hold the Supabase
service-role key, and `conversation_digests` is service-role only.

Gated OFF by default: CONVERSATION_SYNC_ENABLED=1 turns the lane on. Every new
lane in this repo ships disabled.
"""
from __future__ import annotations

import hmac as _hmac
import logging
import os
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .. import config, conversation_store

log = logging.getLogger("pi-ceo.routes.conversations")
router = APIRouter(prefix="/api/conversations", tags=["conversations"])

# Per-digest body cap. A Claude Code session can run for hours; an uncapped
# digest_md would put an unbounded TEXT into a row that is rewritten on every
# re-sync, and the tsvector is generated over it.
CONVERSATION_DIGEST_MAX_CHARS = max(
    int(os.environ.get("CONVERSATION_DIGEST_MAX_CHARS", "20000")), 500
)
# Batch cap. Bounds one request independently of the 10 MB middleware limit.
CONVERSATION_INGEST_MAX_ROWS = max(
    int(os.environ.get("CONVERSATION_INGEST_MAX_ROWS", "200")), 1
)


from ..conversation_redaction import (  # noqa: E402
    _build_redaction_bank,
    _redact,
)

# Re-bound as module globals so `_require_complete_bank` reads THIS module's
# copy and the tests that monkeypatch it keep working.
_REDACTION_BANK, _REDACTION_BANK_COMPLETE = _build_redaction_bank()


def _check_secret(secret: Optional[str]) -> None:
    """Same gate as routes/mesh.py — constant-time compare, 503 when unset."""
    if not config.INTERNAL_WEBHOOK_SECRET:
        raise HTTPException(503, "TAO_INTERNAL_WEBHOOK_SECRET not configured on server")
    if not secret or not _hmac.compare_digest(secret, config.INTERNAL_WEBHOOK_SECRET):
        raise HTTPException(401, "Invalid or missing X-Pi-CEO-Secret")


# Must match scripts/conversation_collector.py's TRUTHY. They are the two halves
# of one switch: the collectors decide whether to POST, this route decides
# whether to accept. When the server took only the literal "1" and the collector
# took the whole set, CONVERSATION_SYNC_ENABLED=true meant every machine shipped
# into a 503 forever, and the runbook told operators that value would work.
_TRUTHY = {"1", "true", "yes", "on"}


def _sync_enabled() -> bool:
    """Read the kill switch per call so it can be flipped without a redeploy.

    Default OFF: unset, "", "0" and "false" all disable, so a missing variable
    can never fail open.
    """
    return os.environ.get("CONVERSATION_SYNC_ENABLED", "").strip().lower() in _TRUTHY


def _guard(secret: Optional[str]) -> None:
    """Authenticate, THEN check the lane flag.

    Order matters: an anonymous caller must not be able to learn whether this
    deployment has the conversation lane switched on, and the smoke surfaces
    declare 401 for an unauthenticated probe regardless of config.
    """
    _check_secret(secret)
    if not _sync_enabled():
        raise HTTPException(
            503,
            "Conversation sync is disabled on this server "
            "(set CONVERSATION_SYNC_ENABLED=1 to enable).",
        )


def _require_complete_bank() -> None:
    """Fail closed on the WRITE path when the second pass is degraded.

    Only ingest is blocked, not the reads: rows already in the table were
    redacted by whatever bank was in force when they were written, and refusing
    to read them would hide data rather than protect it. What must not happen is
    a NEW row landing under a bank that cannot match the shapes transcripts
    actually carry — a durable leak with no signal that it occurred.
    """
    if not _REDACTION_BANK_COMPLETE:
        raise HTTPException(
            503,
            "Conversation ingest is disabled: the transcript redaction bank "
            "(scripts.sync_claude_sessions) failed to load, so the second pass "
            "cannot cover transcript token shapes.",
        )


class Digest(BaseModel):
    """One conversation's redacted digest, as sent by a machine."""

    session_id: str
    project_dir: Optional[str] = None
    title: Optional[str] = None
    digest_md: Optional[str] = None
    turn_count: Optional[int] = None
    started_at: Optional[str] = None
    last_activity_at: Optional[str] = None


class IngestRequest(BaseModel):
    machine: str
    digests: list[Digest] = Field(default_factory=list)


def _identifiable(d: Digest) -> bool:
    """True when this digest's session_id survives redaction unchanged.

    The row id is "<machine>:<session_id>" and BOTH halves are redacted, so two
    different secret-bearing session ids collapse to the same placeholder text
    and therefore the same primary key — one conversation silently overwriting
    another. Redacting an identity does not sanitise it, it destroys it.

    A real collector cannot trigger this: session_id is a JSONL filename stem, a
    UUID. But this route's whole premise is that the client's claim cannot be
    verified, so the pathological case has to be handled rather than assumed
    away. The digest is skipped and counted rather than rejecting the request,
    because one unidentifiable digest must not cost the batch it arrived in —
    the same rule the duplicate-id and bad-timestamp paths follow.
    """
    return _redact(d.session_id) == d.session_id


def _timestamp_or_none(value: Optional[str]) -> Optional[str]:
    """An ISO-8601 timestamp, or None when the value is not one.

    Guards the two TIMESTAMPTZ columns. A caller can send anything in these
    fields, and redaction can itself turn a secret-bearing value into text that
    is still not a timestamp. Either way Postgres rejects the row — and because
    the upsert is a single statement for the entire batch, that one value fails
    every digest sent with it. Returning None costs one field on one row.
    """
    if not value:
        return None
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        log.warning("conversation ingest: dropping unparseable timestamp")
        return None
    return value


def _row(machine: str, d: Digest) -> dict[str, Any]:
    """One `conversation_digests` row: redacted, capped, and identity-keyed.

    EVERY text field is redacted, not just the obvious two. `project_dir` is a
    cwd, so it carries a username at minimum — the client redacts it for exactly
    that reason (`scripts/conversation_collector.py`), and this server exists
    because the client's claim cannot be verified. `machine` and `session_id`
    are caller-supplied strings that end up concatenated into the primary key,
    so they are redacted before that concatenation rather than after.

    `machine` arrives already redacted from `ingest`, which needs the clean
    value for its log line and response body too.

    The cap is applied after redaction — a placeholder is shorter than the
    secret it replaced, so truncating first could slice a secret in half and
    leave a fragment no pattern matches.
    """
    session_id = _redact(d.session_id) or ""
    return {
        "id": f"{machine}:{session_id}",
        "machine": machine,
        "project_dir": _redact(d.project_dir),
        "title": _redact(d.title),
        "digest_md": (_redact(d.digest_md) or "")[:CONVERSATION_DIGEST_MAX_CHARS] or None,
        "turn_count": d.turn_count,
        # Redacted like every other caller string, THEN validated. Redaction
        # alone was not enough and reasoning it was is what this fixes: a
        # secret-bearing timestamp is not a timestamp either before or after
        # redaction, so TIMESTAMPTZ rejects it — and the upsert is ONE statement
        # for the whole batch, so a single bad value takes up to
        # CONVERSATION_INGEST_MAX_ROWS good digests down with it. Dropping the
        # field keeps the row, and both columns are nullable by design.
        "started_at": _timestamp_or_none(_redact(d.started_at)),
        "last_activity_at": _timestamp_or_none(_redact(d.last_activity_at)),
    }


@router.post("/ingest")
async def ingest(
    body: IngestRequest,
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
) -> dict[str, Any]:
    """Publish one machine's redacted digests into the shared store."""
    _guard(x_pi_ceo_secret)
    _require_complete_bank()
    # Redacted once, here, because this value reaches three durable places: the
    # row, this route's log line, and the response body. Logging the raw value
    # put a caller-supplied secret into the server log even when the row itself
    # was clean.
    machine = (_redact(body.machine) or "").strip()
    if not machine:
        raise HTTPException(422, "machine is required")
    if machine != body.machine.strip():
        # Identity must be clean, not merely redacted. A machine name that
        # changed under redaction is a broken client, and it applies to every
        # digest in the request, so there is no partial recovery to attempt.
        raise HTTPException(422, "machine must not contain a secret")
    if len(body.digests) > CONVERSATION_INGEST_MAX_ROWS:
        raise HTTPException(
            413, f"at most {CONVERSATION_INGEST_MAX_ROWS} digests per request",
        )
    usable = [d for d in body.digests if d.session_id and _identifiable(d)]
    skipped = len([d for d in body.digests if d.session_id]) - len(usable)
    rows = [_row(machine, d) for d in usable]
    written = conversation_store.save_conversation_digests(rows)
    # Unlike the observability writers in supabase_log.py, this one reports.
    # A machine that syncs nightly and is told "ok" for a write that never
    # landed keeps a lake nobody can search and no signal that it is missing.
    if written != len(rows):
        raise HTTPException(
            502, f"stored {written} of {len(rows)} digests — Supabase write incomplete",
        )
    log.info(
        "conversation digests stored: machine=%s rows=%d skipped=%d",
        machine, written, skipped,
    )
    return {"ok": True, "machine": machine, "stored": written, "skipped": skipped}


@router.get("/search")
async def search(
    q: str,
    machine: Optional[str] = None,
    limit: int = 20,
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
) -> dict[str, Any]:
    """Full-text search across every machine's digests."""
    _guard(x_pi_ceo_secret)
    hits = conversation_store.search_conversation_digests(q, machine=machine, limit=limit)
    return {"query": q, "machine": machine, "count": len(hits), "results": hits}


@router.get("/recent")
async def recent(
    machine: Optional[str] = None,
    limit: int = 20,
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
) -> dict[str, Any]:
    """The newest digests, optionally narrowed to one machine."""
    _guard(x_pi_ceo_secret)
    rows = conversation_store.recent_conversation_digests(machine, limit)
    return {"machine": machine, "count": len(rows), "results": rows}
