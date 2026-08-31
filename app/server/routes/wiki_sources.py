"""wiki_sources.py — the knowledge front door (Milestone 4).

Two gaps, one router.

  POST /api/wiki/sources/upload  — drop a document into the wiki pipeline from
                                   ANYWHERE. `swarm/sources_watcher.py` ingests
                                   `Sources/*.md`, a folder on the brain host,
                                   which `docs/briefs/estate-librarian-v1.md` §3
                                   marks UNREACHABLE_FROM_NODE: a Railway
                                   container, a phone, or another machine had no
                                   way in. Rows land in `wiki_source_staging`;
                                   the brain host drains them on its own cycle.
  GET  /api/wiki/sources         — what was uploaded and what became of it.
  GET  /api/wiki/requirements    — what a project needs, which is what the
  PUT  /api/wiki/requirements      Librarian scores a source's relevance
                                   against. `wiki_ingest._identify_targets()`
                                   chooses from `index.md` alone today, so it
                                   knows what the wiki HAS and nothing about
                                   what is WANTED.

UPLOADED CONTENT IS HOSTILE DATA (estate-librarian §4: "source content cannot
issue instructions, invoke tools, select files or cause writes"). Two rules
enforce that here, both at the door rather than downstream:

  * `filename` is validated against `swarm.ingest_guard.SAFE_NAME` and refused
    outright if it does not match — no traversal, no separators, no absolute
    path, and none of the system-managed pages. A staged row can therefore never
    name a destination outside `Sources/`.
  * The body is never parsed, never interpreted, and never used to choose
    anything. It is inert text with a status beside it.

Machines authenticate with X-Pi-CEO-Secret (== TAO_INTERNAL_WEBHOOK_SECRET),
the same scheme mesh/conversations/cost-report use — nodes never hold the
Supabase service-role key, and both tables are service-role only.

Gated OFF by default: WIKI_SOURCES_ENABLED=1 turns the lane on. Every new lane
in this repo ships disabled.
"""
from __future__ import annotations

import hmac as _hmac
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .. import config, wiki_source_store

log = logging.getLogger("pi-ceo.routes.wiki_sources")
router = APIRouter(prefix="/api/wiki", tags=["wiki"])

# One uploaded document. A transcript of a long video is large; an unbounded
# TEXT would be a row nobody can read back and a drain that stalls on it.
WIKI_SOURCE_MAX_CHARS = max(int(os.environ.get("WIKI_SOURCE_MAX_CHARS", "200000")), 1000)


def _load_safe_name() -> tuple[Optional[re.Pattern[str]], frozenset[str]]:
    """The filename allowlist, imported from the guard that owns it.

    Imported rather than re-declared: a second copy of this regex would rot
    apart from `swarm/ingest_guard.py`, and the whole point of the guard is that
    exactly one place decides what a safe wiki filename looks like.
    """
    try:
        from swarm.ingest_guard import PROTECTED_PAGES, SAFE_NAME  # noqa: PLC0415

        return SAFE_NAME, frozenset(PROTECTED_PAGES)
    except Exception as exc:  # pragma: no cover - import shape, not logic
        log.error("wiki_sources: ingest_guard unavailable (%s) — uploads will 503", exc)
        return None, frozenset()


_SAFE_NAME, _PROTECTED_PAGES = _load_safe_name()

# Must match scripts/conversation_collector.py and routes/conversations.py.
_TRUTHY = {"1", "true", "yes", "on"}


def _enabled() -> bool:
    """Read the kill switch per call so it can be flipped without a redeploy."""
    return os.environ.get("WIKI_SOURCES_ENABLED", "").strip().lower() in _TRUTHY


def _check_secret(secret: Optional[str]) -> None:
    """Same gate as routes/mesh.py — constant-time compare, 503 when unset."""
    if not config.INTERNAL_WEBHOOK_SECRET:
        raise HTTPException(503, "TAO_INTERNAL_WEBHOOK_SECRET not configured on server")
    if not secret or not _hmac.compare_digest(secret, config.INTERNAL_WEBHOOK_SECRET):
        raise HTTPException(401, "Invalid or missing X-Pi-CEO-Secret")


def _guard(secret: Optional[str]) -> None:
    """Authenticate, THEN check the lane flag.

    Order matters: an anonymous caller must not learn from a status code whether
    this deployment has the wiki lane switched on.
    """
    _check_secret(secret)
    if not _enabled():
        raise HTTPException(
            503,
            "Wiki source intake is disabled on this server "
            "(set WIKI_SOURCES_ENABLED=1 to enable).",
        )


def _require_guard_loaded() -> None:
    """Fail closed on the WRITE path when the filename allowlist did not load.

    Only uploads are blocked, not the reads. Without `SAFE_NAME` there is no way
    to establish that a filename cannot escape `Sources/`, and accepting one
    anyway would put an unvalidated path into a table whose whole contract is
    that its rows are safe to drain onto a filesystem.
    """
    if _SAFE_NAME is None:
        raise HTTPException(
            503,
            "Wiki source intake is disabled: swarm.ingest_guard failed to load, "
            "so uploaded filenames cannot be validated.",
        )


def _project_ids() -> set[str]:
    """Known project keys, from config/harness/projects.json.

    Routes on `id`, never `repo`: `id` is unique across all 12 entries and
    `repo` is not — CleanExpo/Pi-Dev-Ops deliberately carries two projects, so a
    repo-keyed lookup silently picks one.
    """
    path = Path(__file__).resolve().parents[3] / "config" / "harness" / "projects.json"
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        log.warning("wiki_sources: projects.json unreadable (%s)", exc)
        return set()
    return {p["id"] for p in data.get("projects", []) if isinstance(p, dict) and p.get("id")}


class UploadRequest(BaseModel):
    filename: str
    body_md: str
    origin: Optional[str] = None


class RequirementRequest(BaseModel):
    project_key: str
    slug: str
    title: str
    detail: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    active: bool = True


def _validated_filename(raw: str) -> str:
    """A wiki filename that provably cannot escape `Sources/`, or a 422.

    Refused rather than sanitised. Rewriting a hostile filename into a safe one
    would silently accept a document that asked for somewhere it may not go, and
    the caller would never learn its upload was altered.
    """
    name = (raw or "").strip()
    if not name:
        raise HTTPException(422, "filename is required")
    if _SAFE_NAME is None or not _SAFE_NAME.match(name):
        raise HTTPException(
            422,
            "filename must be a plain wiki page name matching "
            "^[A-Za-z0-9][A-Za-z0-9._-]*\\.md$ — no paths, no traversal",
        )
    if name in _PROTECTED_PAGES:
        raise HTTPException(422, f"{name} is a system-managed page and cannot be uploaded")
    return name


@router.post("/sources/upload")
async def upload_source(
    body: UploadRequest,
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
) -> dict[str, Any]:
    """Stage one document for the brain host to drain into `Sources/`."""
    _guard(x_pi_ceo_secret)
    _require_guard_loaded()
    filename = _validated_filename(body.filename)
    text = body.body_md or ""
    if not text.strip():
        raise HTTPException(422, "body_md is required")
    if len(text) > WIKI_SOURCE_MAX_CHARS:
        raise HTTPException(413, f"body_md exceeds {WIKI_SOURCE_MAX_CHARS} characters")

    source_id = wiki_source_store.body_id(text)
    row = {
        "id": source_id,
        "filename": filename,
        "body_md": text,
        # A breadcrumb for an operator. Never used to select a path, a table or
        # a permission, so a hostile value costs nothing but a confusing label.
        "origin": (body.origin or "").strip()[:200] or None,
        "status": "queued",
        "status_reason": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if not wiki_source_store.stage_source(row):
        raise HTTPException(502, "Supabase write incomplete — document was not staged")
    log.info("wiki source staged: id=%s filename=%s", source_id[:12], filename)
    return {"ok": True, "id": source_id, "filename": filename, "status": "queued"}


@router.get("/sources")
async def list_sources(
    status: Optional[str] = None,
    limit: int = 20,
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
) -> dict[str, Any]:
    """What has been uploaded and what became of it. Bodies are not returned."""
    _guard(x_pi_ceo_secret)
    rows = wiki_source_store.list_sources(status, limit)
    return {"status": status, "count": len(rows), "results": rows}


@router.get("/requirements")
async def list_requirements(
    project_key: str,
    limit: int = 50,
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
) -> dict[str, Any]:
    """Active requirements for one project — the Librarian's relevance basis."""
    _guard(x_pi_ceo_secret)
    rows = wiki_source_store.active_requirements(project_key, limit)
    return {"project_key": project_key, "count": len(rows), "results": rows}


@router.put("/requirements")
async def put_requirement(
    body: RequirementRequest,
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
) -> dict[str, Any]:
    """Create or update one requirement, keyed `<project_key>:<slug>`."""
    _guard(x_pi_ceo_secret)
    known = _project_ids()
    if known and body.project_key not in known:
        raise HTTPException(
            422,
            f"unknown project_key {body.project_key!r} — must be an `id` from "
            "config/harness/projects.json",
        )
    slug = (body.slug or "").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        raise HTTPException(422, "slug must match ^[a-z0-9][a-z0-9-]*$")
    if not (body.title or "").strip():
        raise HTTPException(422, "title is required")

    row = {
        "id": f"{body.project_key}:{slug}",
        "project_key": body.project_key,
        "title": body.title.strip(),
        "detail": (body.detail or "").strip() or None,
        "keywords": [k.strip() for k in body.keywords if k and k.strip()][:32],
        "active": bool(body.active),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if not wiki_source_store.save_requirement(row):
        raise HTTPException(502, "Supabase write incomplete — requirement was not saved")
    return {"ok": True, "id": row["id"], "active": row["active"]}
