"""mesh_lane_events.py — per-lane events from the `mc-lane` Claude Code mod.

POST /api/mesh/lane-events   — a lane's batch of events (machines; shared secret)
GET  /api/mesh/lane-events   — newest events after a cursor (fleet read secret)

Spec: docs/specs/claude-mods-integration.md §3.1. The sender is
`mods/mc-lane/hooks/register.ts`.

WHY. The retired `claude_session_hud.py` could see only the host the backend runs on (its own
docstring says so: on Railway it is `available: False`), so the MacBook and
Windows lanes never reached Mission Control's HUD. The mod posts from every
machine instead; with all three machines reporting (RA-7902), the
context-ceiling file reader and its HUD were retired (spec §3, subtraction).

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

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .. import mesh_fleet_auth
from ..auth import require_auth
from . import mesh as _mesh

log = logging.getLogger("pi-ceo.routes.mesh_lane_events")
router = APIRouter(prefix="/api/mesh", tags=["mesh"])
# Session-gated read for the dashboard (through the /api/pi-ceo proxy): the
# browser never holds X-Pi-CEO-Secret, and no dashboard API route is added.
mc_router = APIRouter(prefix="/api/mission-control", tags=["mission-control"])

MAX_BATCH = 200          # mods/mc-lane/hooks/lane.ts MAX_BATCH — keep equal
MAX_READ = 500

# agent_start: a subagent or agent-team teammate started (mod's agent.spawn hook);
# `tool` carries the agent type's name, `model` what it runs on. Needs
# mesh/schema/0005_mesh_lane_events_agent_start.sql applied (kind CHECK).
KINDS = {"session_start", "tool", "agent_start", "usage", "session_end"}
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
    repo: str | None = None
    model: str | None = None
    tool: str | None = None
    ok: bool | None = None
    ms: float | None = Field(default=None, ge=0)
    ctx_pct: float | None = Field(default=None, ge=0, le=100)
    rate_pct: float | None = Field(default=None, ge=0, le=100)
    cost_usd: float | None = Field(default=None, ge=0)


class LaneBatch(BaseModel):
    host: str
    events: list[LaneEvent] = Field(default_factory=list)


def _match(pattern: re.Pattern, value: str | None) -> str | None:
    return value if value is not None and pattern.match(value) else None


def _row(host: str, ev: LaneEvent) -> dict | None:
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
    x_pi_ceo_secret: str | None = Header(default=None, alias="X-Pi-CEO-Secret"),
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


def _read(after_id: int, limit: int, newest: bool) -> dict:
    """Events after `after_id` (oldest first), or the newest `limit` (newest first).

    A failed read is a 502, never an empty list: "no lane reported" and "could
    not read" must not look the same (RA-7392's lesson in mesh_fleet.py).
    """
    order = "id.desc" if newest else "id.asc"
    status, body = _sb("GET", f"mesh_lane_events?id=gt.{after_id}&order={order}&limit={limit}")
    if status >= 300:
        raise HTTPException(502, f"lane-events read failed ({status})")
    try:
        rows = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(502, "lane-events read returned non-JSON") from exc
    if not isinstance(rows, list):
        raise HTTPException(502, "lane-events read returned an error object")
    cursor = max((r["id"] for r in rows if isinstance(r, dict) and isinstance(r.get("id"), int)), default=after_id)
    return {"events": rows, "cursor": cursor}


@router.get("/lane-events")
def get_lane_events(
    after_id: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=MAX_READ),
    newest: bool = Query(False),
    x_pi_ceo_secret: str | None = Header(default=None, alias="X-Pi-CEO-Secret"),
):
    """Machine read (fleet read secret): a cursor read, or newest=true for the latest."""
    mesh_fleet_auth.check(x_pi_ceo_secret)
    return _read(after_id, limit, newest)


@mc_router.get("/lane-events", dependencies=[Depends(require_auth)])
def mission_control_lane_events(limit: int = Query(MAX_READ, ge=1, le=MAX_READ)):
    """Dashboard read (session): the newest events, for the Claude lanes board module."""
    return _read(0, limit, newest=True)
