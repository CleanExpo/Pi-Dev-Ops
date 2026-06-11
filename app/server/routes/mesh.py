"""mesh.py — Nexus Mesh fleet endpoints.

Spec: docs/superpowers/specs/2026-06-11-nexus-mesh-design.md

POST /api/mesh/heartbeat   — a fleet node publishes its live state (machine + agents).
GET  /api/mesh/fleet       — the Mission Control Panel reads the whole fleet.

Machines authenticate with the X-Pi-CEO-Secret header (== TAO_WEBHOOK_SECRET), the
same scheme margot/cost-report use — so nodes never hold the Supabase service-role
key. This server is the only writer to the mesh_* tables (RLS-locked to service role).

Stdlib urllib only; no supabase-py. Writes are best-effort but the endpoint reports
failure so a node knows its heartbeat didn't land.
"""
from __future__ import annotations

import hmac as _hmac
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .. import config

log = logging.getLogger("pi-ceo.routes.mesh")
router = APIRouter(prefix="/api/mesh", tags=["mesh"])


def _check_secret(secret: Optional[str]) -> None:
    if not config.WEBHOOK_SECRET:
        raise HTTPException(503, "TAO_WEBHOOK_SECRET not configured on server")
    if not secret or not _hmac.compare_digest(secret, config.WEBHOOK_SECRET):
        raise HTTPException(401, "Invalid or missing X-Pi-CEO-Secret")


def _sb(method: str, path: str, body: Any = None, *, prefer: str = "") -> tuple[int, str]:
    url = config.SUPABASE_URL
    key = config.SUPABASE_SERVICE_ROLE_KEY
    if not url or not key:
        raise HTTPException(503, "Supabase not configured on server")
    headers = {
        "Content-Type": "application/json",
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }
    if prefer:
        headers["Prefer"] = prefer
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{url}/rest/v1/{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Supabase request failed: {e}") from e


class AgentState(BaseModel):
    runtime: str
    session_id: Optional[str] = None
    repo: Optional[str] = None
    branch: Optional[str] = None
    current_task: Optional[str] = None
    state: str = "working"


class Heartbeat(BaseModel):
    host: str
    os: Optional[str] = None
    tailnet_ip: Optional[str] = None
    status: str = "online"
    cpu_pct: Optional[float] = None
    mem_pct: Optional[float] = None
    load1: Optional[float] = None
    agent_runtimes: list[dict] = Field(default_factory=list)
    version: Optional[str] = None
    agents: list[AgentState] = Field(default_factory=list)


@router.post("/heartbeat")
async def heartbeat(
    hb: Heartbeat,
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
):
    _check_secret(x_pi_ceo_secret)
    machine_row = {
        "host": hb.host, "os": hb.os, "tailnet_ip": hb.tailnet_ip, "status": hb.status,
        "cpu_pct": hb.cpu_pct, "mem_pct": hb.mem_pct, "load1": hb.load1,
        "agent_runtimes": hb.agent_runtimes, "version": hb.version, "last_seen": "now()",
    }
    # PostgREST can't call now() inline; drop it and let the column default handle it.
    machine_row.pop("last_seen")
    status, _ = _sb("POST", "mesh_machines", machine_row,
                    prefer="resolution=merge-duplicates,return=minimal")
    if status >= 300:
        raise HTTPException(502, f"machine upsert failed ({status})")

    # Reconcile this machine's agent rows: mark all idle, then upsert the live ones.
    _sb("PATCH", f"mesh_agents?machine=eq.{urllib.parse.quote(hb.host)}",
        {"state": "idle"}, prefer="return=minimal")
    for a in hb.agents:
        row = {"machine": hb.host, "runtime": a.runtime, "session_id": a.session_id or a.runtime,
               "repo": a.repo, "branch": a.branch, "current_task": a.current_task, "state": a.state}
        _sb("POST", "mesh_agents", row,
            prefer="resolution=merge-duplicates,return=minimal")
    return {"ok": True, "host": hb.host, "agents": len(hb.agents)}


@router.get("/fleet")
async def fleet(
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
):
    """Whole-fleet snapshot for the Mission Control Panel."""
    _check_secret(x_pi_ceo_secret)
    _, machines = _sb("GET", "mesh_fleet?select=*&order=host")
    _, agents = _sb("GET", "mesh_agents?select=*&state=neq.idle&order=updated_at.desc")
    _, ships = _sb("GET", "mesh_ships?select=*&order=shipped_at.desc&limit=25")
    _, claims = _sb("GET", "mesh_work_claims?select=*&state=in.(claimed,working)&order=claimed_at.desc")
    def _j(s: str) -> Any:
        try:
            return json.loads(s)
        except (json.JSONDecodeError, TypeError):
            return []
    return {
        "machines": _j(machines),
        "agents": _j(agents),
        "ships": _j(ships),
        "claims": _j(claims),
    }
