"""conversation_store.py — Supabase read/write path for `conversation_digests`.

The shared half of the conversation brain (Milestone 3). Raw
`~/.claude/projects/**/*.jsonl` never leaves its origin machine; a client sends
already-redacted digests to `POST /api/conversations/ingest`, that route
redacts a second time, and these three functions are what actually touch
Supabase.

Every call goes through `supabase_log._request()` — the single server-side
Supabase HTTP path — so there is exactly one request builder, one timeout and
one place that knows how to be unconfigured. These helpers live HERE rather
than in `supabase_log.py` for the same reason `session_lease.py` does: that
module is already baselined over the 300-line ceiling in
`.github/file-length.baseline.txt` and may not grow.

Fire-and-forget in spirit — nothing here raises into a caller. The two read
paths degrade to `[]`, which is indistinguishable from "no matches" and is the
right answer for a search box. The write path is the exception the ingest route
needs: it returns the number of rows Supabase actually confirmed, so a caller
can tell a real write from a silent no-op instead of reporting success it never
observed.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from . import supabase_log

log = logging.getLogger("pi-ceo.conversation_store")

_TABLE = "conversation_digests"

# search_tsv is deliberately excluded: it is a stored tsvector, useless to a
# reader and the largest column on the row.
_COLUMNS = (
    "id,machine,project_dir,title,digest_md,turn_count,"
    "started_at,last_activity_at,updated_at"
)

_MAX_LIMIT = 100
_MAX_TERMS = 12

# to_tsquery rejects free text: `fts` on "deploy failed" or "auth/session" is a
# syntax error, not zero results, and PostgREST surfaces that as a 400 the
# caller sees as an outage. Reducing the query to its word tokens and joining
# them with & keeps the `fts` operator (the generated column is an english
# tsvector) while making any input a valid tsquery.
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tsquery(query: str) -> str:
    """Free text → a safe `&`-joined to_tsquery expression. `''` when empty."""
    return "&".join(_TOKEN_RE.findall(query or "")[:_MAX_TERMS])


def _clamp(limit: int) -> int:
    """Bound a caller-supplied row limit to 1..100."""
    try:
        return max(1, min(int(limit), _MAX_LIMIT))
    except (TypeError, ValueError):
        return 20


def save_conversation_digests(rows: list[dict[str, Any]]) -> int:
    """Bulk-upsert digest rows on the `id` primary key. Returns rows written.

    One POST for the whole batch — PostgREST accepts an array body, and
    `resolution=merge-duplicates` turns the PK conflict a re-sync always
    produces into an update instead of a 409.

    `return=representation` is what makes the count real: with the module's
    default `return=minimal` a 2xx proves only that the request was accepted,
    so a caller reporting "wrote 40" would be reporting the length of its own
    input. Returns 0 when Supabase is unconfigured or the write failed —
    never raises, and never claims a row it did not see come back.
    """
    if not rows:
        return 0
    status, body = supabase_log._request(
        "POST", _TABLE, rows, "return=representation,resolution=merge-duplicates",
    )
    if not supabase_log._ok(status):
        log.warning("conversation digest upsert failed: HTTP %s (%d rows)", status, len(rows))
        return 0
    written = len(body) if isinstance(body, list) else 0
    if written != len(rows):
        log.warning("conversation digest upsert wrote %d of %d rows", written, len(rows))
    return written


def search_conversation_digests(
    query: str,
    *,
    machine: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Full-text search across every machine's digests, newest first.

    An empty or punctuation-only query returns `[]` rather than falling through
    to an unfiltered select — a search box that silently returns "everything"
    when the tsquery came out empty looks identical to a working search and is
    how a reader ends up trusting an unfiltered list.
    """
    tsq = _tsquery(query)
    if not tsq:
        return []
    params = (
        f"select={_COLUMNS}"
        f"&search_tsv=fts(english).{supabase_log._q(tsq)}"
        f"&order=last_activity_at.desc.nullslast"
        f"&limit={_clamp(limit)}"
    )
    if machine:
        params += f"&machine=eq.{supabase_log._q(machine)}"
    return _rows(params)


def recent_conversation_digests(
    machine: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Most-recently-active digests, optionally for one machine."""
    params = (
        f"select={_COLUMNS}"
        f"&order=last_activity_at.desc.nullslast"
        f"&limit={_clamp(limit)}"
    )
    if machine:
        params += f"&machine=eq.{supabase_log._q(machine)}"
    return _rows(params)


def _rows(params: str) -> list[dict[str, Any]]:
    """GET one page of digests. `[]` on any failure — reads never raise."""
    status, body = supabase_log._request("GET", f"{_TABLE}?{params}", None, "")
    if not supabase_log._ok(status):
        log.warning("conversation digest read failed: HTTP %s", status)
        return []
    return [r for r in body if isinstance(r, dict)] if isinstance(body, list) else []
