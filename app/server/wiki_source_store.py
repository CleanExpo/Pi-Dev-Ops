"""wiki_source_store.py — Supabase read/write path for the knowledge front door.

Two tables, one module: `project_requirements` (what the projects need, which
is what the Librarian scores a source's relevance against) and
`wiki_source_staging` (documents uploaded from anywhere, waiting for the brain
host to drain them into `Sources/`).

Every call goes through `supabase_log._request()` — the single server-side
Supabase HTTP path — so there is one request builder, one timeout, and one
place that knows how to be unconfigured. These live here rather than in
`supabase_log.py` for the same reason `conversation_store.py` and
`session_lease.py` do: that module is already baselined over the 300-line
ceiling in `.github/file-length.baseline.txt` and may not grow.

Reads degrade to `[]`; a caller cannot tell "no rows" from "Supabase down", and
for a relevance hint that is the right failure — the Librarian falls back to
its old index-only behaviour rather than blocking.

The WRITE path is the exception, and reports. A machine told "queued" for a row
that never landed keeps a document nobody will ever ingest, with no signal it
is missing — the same rule `conversation_store.save_conversation_digests()`
follows.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from . import supabase_log

log = logging.getLogger("pi-ceo.wiki_source_store")

_REQUIREMENTS = "project_requirements"
_STAGING = "wiki_source_staging"

_REQ_COLUMNS = "id,project_key,title,detail,keywords,active,created_at,updated_at"
# body_md is deliberately excluded from the LIST columns: it is the whole
# document and a listing of 50 rows would be megabytes. The drain fetches it.
_STAGING_LIST_COLUMNS = "id,filename,origin,status,status_reason,created_at,updated_at"
_STAGING_FULL_COLUMNS = _STAGING_LIST_COLUMNS + ",body_md"

_MAX_LIMIT = 100

# The staging lifecycle. Enforced HERE rather than by a CHECK constraint: the
# `sessions` table carried `sessions_status_check` accepting only
# running/done/error, the build lifecycle grew to nine states, and RA-1407 had
# to drop the constraint in a migration against a live table
# (supabase/migration.sql:66). Widening this set is a one-line code change.
STAGING_STATUSES = frozenset({"queued", "ingested", "quarantined", "error"})


def _clamp(limit: int) -> int:
    """A caller-supplied limit, bounded. `limit=100000` is not a page."""
    try:
        return max(1, min(int(limit), _MAX_LIMIT))
    except (TypeError, ValueError):
        return 20


def body_id(body_md: str) -> str:
    """The staging primary key: sha256 of the body.

    Content-addressed so re-uploading the same document upserts onto its own row
    rather than queueing it twice. The drain is not idempotent by itself, so the
    dedupe has to happen at the door.
    """
    return hashlib.sha256((body_md or "").encode("utf-8")).hexdigest()


def _rows(path: str, what: str) -> list[dict[str, Any]]:
    """GET one page. `[]` on any failure — reads never raise into a caller."""
    status, body = supabase_log._request("GET", path, None, "")
    if not supabase_log._ok(status):
        log.warning("%s read failed: HTTP %s", what, status)
        return []
    return [r for r in body if isinstance(r, dict)] if isinstance(body, list) else []


def _upsert_one(table: str, row: dict[str, Any], what: str) -> bool:
    """Upsert one row on its primary key. True only when Supabase confirmed it.

    `return=representation` is what makes the answer real: with the module
    default `return=minimal` a 2xx proves only that the request was accepted, so
    a caller reporting success would be reporting its own input back to itself.
    `resolution=merge-duplicates` turns the PK conflict that a re-upload always
    produces into an update rather than a 409.
    """
    status, body = supabase_log._request(
        "POST", table, [row], "return=representation,resolution=merge-duplicates",
    )
    if not supabase_log._ok(status):
        log.warning("%s upsert failed: HTTP %s", what, status)
        return False
    written = len(body) if isinstance(body, list) else 0
    if written != 1:
        log.warning("%s upsert confirmed %d rows, expected 1", what, written)
    return written == 1


# ── project_requirements ─────────────────────────────────────────────────────


def active_requirements(project_key: str, limit: int = 50) -> list[dict[str, Any]]:
    """Active requirements for one project, newest first.

    Routes on `project_key` (a config/harness/projects.json `id`), never on a
    repo: `id` is unique across all 12 entries and `repo` is not.
    """
    if not project_key:
        return []
    params = (
        f"select={_REQ_COLUMNS}"
        f"&project_key=eq.{supabase_log._q(project_key)}"
        f"&active=is.true"
        f"&order=updated_at.desc"
        f"&limit={_clamp(limit)}"
    )
    return _rows(f"{_REQUIREMENTS}?{params}", "project_requirements")


def save_requirement(row: dict[str, Any]) -> bool:
    """Upsert one requirement. True only when Supabase confirmed the row."""
    return _upsert_one(_REQUIREMENTS, row, "project_requirements")


# ── wiki_source_staging ──────────────────────────────────────────────────────


def stage_source(row: dict[str, Any]) -> bool:
    """Upsert one staged document. True only when Supabase confirmed it."""
    return _upsert_one(_STAGING, row, "wiki_source_staging")


def queued_sources(limit: int = 20) -> list[dict[str, Any]]:
    """Oldest queued documents, WITH their bodies — this is what the drain reads."""
    params = (
        f"select={_STAGING_FULL_COLUMNS}"
        f"&status=eq.queued"
        f"&order=created_at.asc"
        f"&limit={_clamp(limit)}"
    )
    return _rows(f"{_STAGING}?{params}", "wiki_source_staging")


def list_sources(status: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Staged documents for an operator, WITHOUT bodies.

    A listing exists to answer "did my upload arrive and what happened to it",
    which needs the status and not the megabyte of text.
    """
    params = (
        f"select={_STAGING_LIST_COLUMNS}"
        f"&order=created_at.desc"
        f"&limit={_clamp(limit)}"
    )
    if status:
        params += f"&status=eq.{supabase_log._q(status)}"
    return _rows(f"{_STAGING}?{params}", "wiki_source_staging")


def mark_source(source_id: str, status: str, reason: str | None = None) -> bool:
    """Move one staged row to a terminal state. Rejects an unknown status.

    Returns False rather than raising: the drain must not die because one row
    could not be marked, and a False here means the row stays `queued` and is
    retried, which is the safe direction.
    """
    if status not in STAGING_STATUSES:
        log.warning("wiki_source_staging: refusing unknown status %r", status)
        return False
    patch = {
        "status": status,
        "status_reason": reason,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path = f"{_STAGING}?id=eq.{supabase_log._q(source_id)}"
    code, _ = supabase_log._request("PATCH", path, patch, "return=representation")
    if not supabase_log._ok(code):
        log.warning("wiki_source_staging: mark %s -> %s failed: HTTP %s", source_id, status, code)
        return False
    return True
