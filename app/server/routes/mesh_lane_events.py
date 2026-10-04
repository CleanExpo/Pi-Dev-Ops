"""mesh_lane_events.py — per-lane events from the `mc-lane` Claude Code mod.

POST /api/mesh/lane-events   — a lane's batch of events (machines; shared secret)
GET  /api/mesh/lane-events   — newest events after a cursor (fleet read secret)

Spec: docs/specs/claude-mods-integration.md §3.1. The sender is
`mods/mc-lane/hooks/register.ts`.

WHY. `claude_session_hud.py` can see only the host the backend runs on (its own
docstring says so: on Railway it is `available: False`), so the MacBook and
Windows lanes never reach Mission Control's HUD. The mod posts from every
machine instead. Once the mod is live on the fleet, the context-ceiling file
reader is retired (spec §3, subtraction) — not in this change, because nothing
is flowing yet.

WHAT IS STORED. Names, numbers and booleans only. The mod sends no tool input
or output, and this route re-validates every field, so a mod that drifted (or
a caller that is not the mod) still cannot write free text: `tool` must look
like a tool name, `repo` like `owner/name`, `model` like a model id; anything
else is dropped field by field, never stored.

IDEMPOTENT. Rows are unique on (session_id, seq) and inserted with
`resolution=ignore-duplicates`, so a lane that re-sends after a timeout writes
nothing twice. The response acks the highest seq per session it accepted; the
mod drops those from its queue.

COST. `cost_usd` absent is stored as NULL and must be shown as "unknown" —
never 0 (UNI-2412: "unknown rather than invented values").
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .. import mesh_fleet_auth
from . import mesh as _mesh

log = logging.getLogger("pi-ceo.routes.mesh_lane_events")
router = APIRouter(prefix="/api/mesh", tags=["mesh"])

MAX_BATCH = 200          # mods/mc-lane/hooks/lane.ts MAX_BATCH — keep equal
MAX_READ = 500

KINDS = {"session_start", "tool", "usage", "session_end"}
_TOOL = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_REPO = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_MODEL = re.compile(r"^[A-Za-z0-9_.:\[\]-]{1,80}$")
_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_HOST = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


def _sb(method: str, path: str, body=None, *, prefer: str = "") -> tuple[int, str]:
    """Supabase via the mesh router's client; a seam for tests."""
    return _mesh._sb(method, path, body, prefer=prefer)


class LaneEvent(BaseModel):
    session_id: str
    seq: int = Field(ge=0)
    kind: str
    at: str
    repo: Optional[str] = None
    model: Optional[str] = None
    tool: Optional[str] = None
    ok: Optional[bool] = None
    ms: Optional[float] = Field(default=None, ge=0)
    ctx_pct: Optional[float] = Field(default=None, ge=0, le=100)
    rate_pct: Optional[float] = Field(default=None, ge=0, le=100)
    cost_usd: Optional[float] = Field(default=None, ge=0)


class LaneBatch(BaseModel):
    host: str
    events: list[LaneEvent] = Field(default_factory=list)


def _match(pattern: re.Pattern, value: Optional[str]) -> Optional[str]:
    return value if value is not None and pattern.match(value) else None


def _row(host: str, ev: LaneEvent) -> Optional[dict]:
    """The row to store, or None when the event itself is unusable."""
    if ev.kind not in KINDS or not _ID.match(ev.session_id):
        return None
    return {
        "host": host,
        "session_id": ev.session_id,
        "seq": ev.seq,
        "kind": ev.kind,
        "at": ev.at[:40],
        "repo": _match(_REPO, ev.repo),
        "model": _match(_MODEL, ev.model),
        "tool": _match(_TOOL, ev.tool),
        "ok": ev.ok,
        "ms": ev.ms,
        "ctx_pct": ev.ctx_pct,
        "rate_pct": ev.rate_pct,
        "cost_usd": ev.cost_usd,
    }


@router.post("/lane-events")
def post_lane_events(
    batch: LaneBatch,
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
):
    _mesh._check_secret(x_pi_ceo_secret)
    if len(batch.events) > MAX_BATCH:
        raise HTTPException(413, f"at most {MAX_BATCH} events per batch")
    host = batch.host if _HOST.match(batch.host) else "unknown"

    rows = [r for r in (_row(host, ev) for ev in batch.events) if r is not None]
    rejected = len(batch.events) - len(rows)
    if rows:
        status, body = _sb("POST", "mesh_lane_events?on_conflict=session_id,seq", rows,
                           prefer="resolution=ignore-duplicates,return=minimal")
        if status >= 300:
            log.warning("lane-events insert failed: %s %s", status, body[:200])
            # 502 so the mod keeps the batch and retries; nothing is acked.
            raise HTTPException(502, f"lane-events insert failed ({status})")
    # Ack every event with a usable session id, stored or rejected: a rejected
    # one would otherwise be re-sent forever.
    acked: dict[str, int] = {}
    for ev in batch.events:
        if _ID.match(ev.session_id):
            acked[ev.session_id] = max(acked.get(ev.session_id, 0), ev.seq)
    return {"ok": True, "stored": len(rows), "rejected": rejected, "acked": acked}


@router.get("/lane-events")
def get_lane_events(
    after_id: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=MAX_READ),
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
):
    """Events with id > after_id, oldest first. `cursor` is the id to pass next.

    A failed read is a 502, never an empty list: "no lane reported" and "could
    not read" must not look the same (RA-7392's lesson in mesh_fleet.py).
    """
    mesh_fleet_auth.check(x_pi_ceo_secret)
    status, body = _sb("GET", f"mesh_lane_events?id=gt.{after_id}&order=id.asc&limit={limit}")
    if status >= 300:
        raise HTTPException(502, f"lane-events read failed ({status})")
    try:
        rows = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(502, "lane-events read returned non-JSON") from exc
    if not isinstance(rows, list):
        raise HTTPException(502, "lane-events read returned an error object")
    cursor = rows[-1]["id"] if rows else after_id
    return {"events": rows, "cursor": cursor}
