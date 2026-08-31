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
import re
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .. import config, conversation_store
from ..scanner import _SECRET_PATTERNS as _SCANNER_SECRET_PATTERNS

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


def _build_redaction_bank() -> list[tuple[re.Pattern[str], str]]:
    """Compile the existing secret banks into (pattern, tag) pairs.

    Union, not a choice between them: `scanner._SECRET_PATTERNS` is the
    server-side bank (`scripts/secrets_check.py` documents itself as mirroring
    it), while `scripts/sync_claude_sessions.py` extends it with the shapes that
    bank misses but transcripts actually contain — sk-ant-oat OAuth tokens,
    AIza, xox*, gho_/github_pat_. Neither alone covers a conversation digest.

    The scripts/ import is best-effort so a refactor over there degrades the
    second pass instead of 500-ing the route, and says so loudly — a silent
    downgrade of a redaction bank is exactly the failure this endpoint exists
    to prevent.
    """
    bank = [(re.compile(p), title) for p, title, _sev in _SCANNER_SECRET_PATTERNS]
    try:
        from scripts.sync_claude_sessions import _SECRET_PATTERNS as _extra  # noqa: PLC0415
        bank += [(re.compile(p), tag) for p, tag in _extra]
    except Exception:  # noqa: BLE001 — never let an import failure open the lane
        log.warning(
            "conversation redaction: scripts.sync_claude_sessions bank unavailable — "
            "second pass covers the scanner shapes only", exc_info=True,
        )
    return bank


_REDACTION_BANK = _build_redaction_bank()


def _redact(text: Optional[str]) -> Optional[str]:
    """Replace every known secret shape with a typed placeholder. Idempotent."""
    if not text:
        return text
    for rx, tag in _REDACTION_BANK:
        text = rx.sub(f"[REDACTED:{tag}]", text)
    return text


def _check_secret(secret: Optional[str]) -> None:
    """Same gate as routes/mesh.py — constant-time compare, 503 when unset."""
    if not config.INTERNAL_WEBHOOK_SECRET:
        raise HTTPException(503, "TAO_INTERNAL_WEBHOOK_SECRET not configured on server")
    if not secret or not _hmac.compare_digest(secret, config.INTERNAL_WEBHOOK_SECRET):
        raise HTTPException(401, "Invalid or missing X-Pi-CEO-Secret")


def _sync_enabled() -> bool:
    """Read the kill switch per call so it can be flipped without a redeploy."""
    return os.environ.get("CONVERSATION_SYNC_ENABLED", "0") == "1"


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


def _row(machine: str, d: Digest) -> dict[str, Any]:
    """One `conversation_digests` row: redacted, capped, and identity-keyed.

    Redaction happens HERE, on the way in, so there is no path from a request
    body to the table that skips it. The cap is applied after redaction — a
    placeholder is shorter than the secret it replaced, so truncating first
    could slice a secret in half and leave a fragment no pattern matches.
    """
    return {
        "id": f"{machine}:{d.session_id}",
        "machine": machine,
        "project_dir": d.project_dir,
        "title": _redact(d.title),
        "digest_md": (_redact(d.digest_md) or "")[:CONVERSATION_DIGEST_MAX_CHARS] or None,
        "turn_count": d.turn_count,
        "started_at": d.started_at,
        "last_activity_at": d.last_activity_at,
    }


@router.post("/ingest")
async def ingest(
    body: IngestRequest,
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
) -> dict[str, Any]:
    """Publish one machine's redacted digests into the shared store."""
    _guard(x_pi_ceo_secret)
    if not body.machine.strip():
        raise HTTPException(422, "machine is required")
    if len(body.digests) > CONVERSATION_INGEST_MAX_ROWS:
        raise HTTPException(
            413, f"at most {CONVERSATION_INGEST_MAX_ROWS} digests per request",
        )
    rows = [_row(body.machine, d) for d in body.digests if d.session_id]
    written = conversation_store.save_conversation_digests(rows)
    # Unlike the observability writers in supabase_log.py, this one reports.
    # A machine that syncs nightly and is told "ok" for a write that never
    # landed keeps a lake nobody can search and no signal that it is missing.
    if written != len(rows):
        raise HTTPException(
            502, f"stored {written} of {len(rows)} digests — Supabase write incomplete",
        )
    log.info("conversation digests stored: machine=%s rows=%d", body.machine, written)
    return {"ok": True, "machine": body.machine, "stored": written}


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
