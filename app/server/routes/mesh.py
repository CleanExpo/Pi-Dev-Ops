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
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .. import config

log = logging.getLogger("pi-ceo.routes.mesh")
router = APIRouter(prefix="/api/mesh", tags=["mesh"])

# Stale-claim reaper (UNI-2301): a runner that dies mid-claim leaves the row
# stuck in claimed/working forever, since mesh_work_claims_one_open keeps the
# ticket locked and nothing else stamps released_at. Threshold is measured
# against claimed_at — the only timestamp the row carries — which already
# banks headroom past the runner's 3600s agent-run cap.
# Floor: 65 = the runner's 3600s (60min) agent-run cap + 5min margin — the TTL
# must never undercut that cap, or the reaper could release a claim while the
# runner is still legitimately working. Unlike MESH_MAX_CLAIMS, an explicit
# "0" here is NOT a special case: every configured value is clamped.
MESH_CLAIM_TTL_MINUTES = max(int(os.environ.get("MESH_CLAIM_TTL_MINUTES", "90")), 65)


def _check_secret(secret: Optional[str]) -> None:
    if not config.INTERNAL_WEBHOOK_SECRET:
        raise HTTPException(503, "TAO_INTERNAL_WEBHOOK_SECRET not configured on server")
    if not secret or not _hmac.compare_digest(secret, config.INTERNAL_WEBHOOK_SECRET):
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
    # PostgREST can't call now() inline, and the column default only fires on INSERT —
    # stamp last_seen from the server so it refreshes on every upsert (else rows read stale).
    machine_row["last_seen"] = datetime.now(timezone.utc).isoformat()
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


# ── Dispatcher: assign mesh:auto tickets to free nodes ───────────────────────
# The nervous-system brain (RA-6494): the always-on server hands work to whichever
# online node has spare capacity. The unique partial index on mesh_work_claims
# guarantees a ticket is claimed by exactly one machine even if dispatch races.
_LINEAR_ENDPOINT = "https://api.linear.app/graphql"
_MESH_AUTO_QUERY = (
    'query{issues(first:50,filter:{labels:{name:{eq:"mesh:auto"}},'
    'state:{type:{in:["backlog","unstarted"]}}}){nodes{id identifier title priority team{id}}}}'
)


def _priority_rank(priority: Any) -> int:
    """Linear priority → sort key (lower = claimed first). 1=Urgent .. 4=Low;
    0/None ("No priority") sorts last so real priorities win."""
    try:
        p = int(priority)
    except (TypeError, ValueError):
        return 99
    return p if p > 0 else 99


def _linear_graphql(query: str) -> dict:
    key = config.LINEAR_API_KEY
    if not key:
        return {}
    req = urllib.request.Request(
        _LINEAR_ENDPOINT, data=json.dumps({"query": query}).encode(), method="POST",
        headers={"Content-Type": "application/json", "Authorization": key})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return (json.loads(r.read()) or {}).get("data", {}) or {}
    except Exception as e:  # noqa: BLE001
        log.warning("linear query failed: %s", e)
        return {}


def _team_started_state_id(team_id: str) -> str:
    """Resolve the team's first 'started'-type workflow state (e.g. In Progress),
    dynamically — no hardcoded state UUIDs."""
    q = f'query{{team(id:"{team_id}"){{states{{nodes{{id type position}}}}}}}}'
    nodes = (((_linear_graphql(q).get("team") or {}).get("states") or {}).get("nodes")) or []
    started = sorted((n for n in nodes if n.get("type") == "started"),
                     key=lambda n: n.get("position") or 0)
    return started[0]["id"] if started else ""


def _mark_issue_in_progress(issue: dict) -> bool:
    """Transition a just-claimed issue out of backlog/unstarted so _MESH_AUTO_QUERY
    stops returning it. Without this, a completed ticket re-enters the pool and is
    re-claimed forever (the infinite re-claim loop). Best-effort: only possible for
    tickets that came from the auto query (explicit dispatch ids carry no node id)."""
    issue_id = issue.get("id")
    team_id = (issue.get("team") or {}).get("id")
    if not issue_id or not team_id:
        return False
    state_id = _team_started_state_id(team_id)
    if not state_id:
        log.warning("no started-type state found for team %s", team_id)
        return False
    m = f'mutation{{issueUpdate(id:"{issue_id}",input:{{stateId:"{state_id}"}}){{success}}}}'
    ok = bool((_linear_graphql(m).get("issueUpdate") or {}).get("success"))
    if not ok:
        log.warning("issueUpdate → started failed for %s", issue.get("identifier") or issue_id)
    return ok


def _team_unstarted_state_id(team_id: str) -> str:
    """Resolve the team's first 'unstarted'-type workflow state (e.g. Todo),
    dynamically — the mirror of _team_started_state_id, used to put a reaped
    issue back into the claimable mesh:auto pool."""
    q = f'query{{team(id:"{team_id}"){{states{{nodes{{id type position}}}}}}}}'
    nodes = (((_linear_graphql(q).get("team") or {}).get("states") or {}).get("nodes")) or []
    todo = sorted((n for n in nodes if n.get("type") == "unstarted"),
                 key=lambda n: n.get("position") or 0)
    return todo[0]["id"] if todo else ""


def _mark_issue_reaped(linear_id: str) -> bool:
    """A reaped claim's Linear issue moves back to the team's first
    unstarted-type state, so it re-enters _MESH_AUTO_QUERY and can be claimed
    again — without this, a dead runner's ticket would sit claimable-never in
    Linear even though the mesh_work_claims row was freed. Best-effort: looked
    up by identifier since claim rows don't carry the Linear issue/team uuid."""
    q = f'query{{issue(id:"{linear_id}"){{id team{{id}}}}}}'
    issue = _linear_graphql(q).get("issue") or {}
    issue_id = issue.get("id")
    team_id = (issue.get("team") or {}).get("id")
    if not issue_id or not team_id:
        log.warning("reap: could not resolve issue/team for %s", linear_id)
        return False
    state_id = _team_unstarted_state_id(team_id)
    if not state_id:
        log.warning("reap: no unstarted-type state found for team %s", team_id)
        return False
    m = f'mutation{{issueUpdate(id:"{issue_id}",input:{{stateId:"{state_id}"}}){{success}}}}'
    ok = bool((_linear_graphql(m).get("issueUpdate") or {}).get("success"))
    if not ok:
        log.warning("reap: issueUpdate → unstarted failed for %s", linear_id)
    return ok


def _reap_stale_claims() -> list[dict]:
    """Release claims stuck in claimed/working past MESH_CLAIM_TTL_MINUTES,
    freeing the mesh_work_claims_one_open unique index so the ticket becomes
    claimable again. Guarded by machine liveness: a claim past TTL is only
    reaped when the claiming machine's heartbeat is itself stale or absent
    (mesh_fleet.is_stale) — a live heartbeat means the runner may legitimately
    still be inside its up-to-3600s agent run, so leave it alone."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=MESH_CLAIM_TTL_MINUTES)).isoformat()
    _, body = _sb(
        "GET",
        "mesh_work_claims?select=id,linear_id,machine,claimed_at&state=in.(claimed,working)"
        f"&claimed_at=lt.{urllib.parse.quote(cutoff)}",
    )
    candidates = _rows(body)
    if not candidates:
        return []
    _, fleet_body = _sb("GET", "mesh_fleet?select=host,is_stale")
    stale_by_host = {m["host"]: m.get("is_stale") for m in _rows(fleet_body)}
    now_iso = datetime.now(timezone.utc).isoformat()
    reaped: list[dict] = []
    for c in candidates:
        machine = c.get("machine")
        if machine is not None and stale_by_host.get(machine) is False:
            continue  # fresh heartbeat — runner may still be legitimately working
        status, body = _sb(
            "PATCH",
            f"mesh_work_claims?id=eq.{c['id']}&state=in.(claimed,working)",
            {"state": "released", "released_at": now_iso},
            prefer="return=representation",
        )
        # return=representation: a 0-row response means a racing reap (or the
        # runner itself) already flipped this claim's state — don't record a
        # reap or fire a redundant Linear transition for a row we didn't touch.
        if status < 300 and _rows(body):
            reaped.append({"linear_id": c["linear_id"], "machine": machine})
            _mark_issue_reaped(c["linear_id"])
    return reaped


def _reap_sweep_best_effort() -> None:
    """Run the stale-claim sweep without letting a Supabase hiccup 502 the
    caller's hot path (claim_self / dispatch). The explicit POST
    /api/mesh/claims/reap endpoint still propagates errors so ops can see
    them there."""
    try:
        _reap_stale_claims()
    except HTTPException as e:
        log.warning("inline reap sweep failed (%s), continuing without it", e.detail)


def _rows(body: str) -> list:
    """Parse a PostgREST body to a list of row dicts; [] on error or error-object."""
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return []
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def _online_machines() -> list[dict]:
    """Online, non-stale nodes, least-loaded first."""
    _, body = _sb("GET", "mesh_fleet?select=host,is_stale,active_agents,load1&order=load1.asc.nullslast")
    return [m for m in _rows(body) if not m.get("is_stale")]


def _open_claim_ids() -> set:
    _, body = _sb("GET", "mesh_work_claims?select=linear_id&state=in.(claimed,working)")
    return {r["linear_id"] for r in _rows(body) if r.get("linear_id")}


class DispatchRequest(BaseModel):
    linear_ids: list[str] = Field(default_factory=list)  # explicit tickets; empty → query Linear mesh:auto


class ClaimUpdate(BaseModel):
    linear_id: str
    state: str  # working | done | released | failed
    branch: Optional[str] = None


class SelfClaimRequest(BaseModel):
    host: str  # the node claiming for itself


@router.get("/claims")
async def claims(
    machine: Optional[str] = None,
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
):
    """Open claims, optionally for one machine — a runner asks 'what's mine?'."""
    _check_secret(x_pi_ceo_secret)
    q = "mesh_work_claims?select=*&state=in.(claimed,working)&order=claimed_at.desc"
    if machine:
        q += f"&machine=eq.{urllib.parse.quote(machine)}"
    _, body = _sb("GET", q)
    return {"claims": _rows(body)}


@router.post("/claim/update")
async def claim_update(
    u: ClaimUpdate,
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
):
    """A runner reports a claim transition: claimed → working → done/failed/released."""
    _check_secret(x_pi_ceo_secret)
    patch: dict[str, Any] = {"state": u.state}
    if u.branch:
        patch["branch"] = u.branch
    if u.state in ("done", "released", "failed"):
        patch["released_at"] = datetime.now(timezone.utc).isoformat()
    status, body = _sb("PATCH",
        f"mesh_work_claims?linear_id=eq.{urllib.parse.quote(u.linear_id)}&state=in.(claimed,working)",
        patch, prefer="return=representation")
    # return=representation: a 0-row match (claim already done/absent — e.g. the
    # reaper released it and another runner re-claimed) still 2xxs, so gate the
    # reversal on rows actually returned or a stale runner's `released` would
    # yank a freshly re-claimed ticket back to Todo.
    if u.state == "released" and status < 300 and _rows(body):
        # A HARD_STOP-released claim must return its Linear issue to the
        # unstarted pool, same as a reaped claim — otherwise it strands
        # In Progress forever even though the mesh_work_claims row is freed.
        # Best-effort: a Linear failure here must never fail the claim update.
        try:
            _mark_issue_reaped(u.linear_id)
        except Exception:  # noqa: BLE001
            log.warning("claim_update: Linear reversal failed for %s", u.linear_id, exc_info=True)
    return {"ok": True, "linear_id": u.linear_id, "state": u.state}


@router.post("/claims/reap")
async def reap_claims(
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
):
    """Manual/ops trigger for the stale-claim sweep (UNI-2301) — the same sweep
    also runs inline at the top of claim_self and dispatch, so this endpoint is
    only needed to force a reap on demand."""
    _check_secret(x_pi_ceo_secret)
    return {"reaped": _reap_stale_claims()}


@router.post("/dispatch")
async def dispatch(
    body: DispatchRequest,
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
):
    """Assign unclaimed work to free nodes. One tick. Idempotent — already-claimed
    tickets are skipped, and the unique index rejects any racing double-claim."""
    _check_secret(x_pi_ceo_secret)
    _reap_sweep_best_effort()  # piggyback: free any dead-runner claims before assigning
    if body.linear_ids:
        tickets = [{"identifier": t} for t in body.linear_ids]
    else:
        nodes = _linear_graphql(_MESH_AUTO_QUERY).get("issues", {}).get("nodes", [])
        tickets = nodes or []
    machines = _online_machines()
    if not machines:
        return {"assigned": [], "online_machines": [], "reason": "no online machines"}
    open_ids = _open_claim_ids()
    assigned: list[dict] = []
    idx = 0
    for tk in tickets:
        ident = tk.get("identifier") or tk.get("id")
        if not ident or ident in open_ids:
            continue
        host = machines[idx % len(machines)]["host"]   # least-loaded first, then round-robin
        status, _ = _sb("POST", "mesh_work_claims",
                        {"linear_id": ident, "machine": host, "state": "claimed"},
                        prefer="return=minimal")
        if status < 300:
            assigned.append({"linear_id": ident, "machine": host})
            open_ids.add(ident)
            idx += 1
            _mark_issue_in_progress(tk)  # leave the mesh:auto pool — no re-claim loop
        # status 409 = already claimed by a racing dispatch → skip silently
    return {"assigned": assigned, "online_machines": [m["host"] for m in machines]}


@router.post("/claim/self")
async def claim_self(
    body: SelfClaimRequest,
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
):
    """An idle runner self-claims the top-priority unclaimed `mesh:auto` ticket
    for itself, so capacity never idles waiting on the dispatcher.

    Atomic: each attempt POSTs a claim row; the `mesh_work_claims_one_open`
    partial unique index rejects a racing double-claim with 409, and we fall
    through to the next candidate — so two idle nodes can never take the same
    ticket. Returns the ticket claimed, or null when the queue is empty/drained."""
    _check_secret(x_pi_ceo_secret)
    _reap_sweep_best_effort()  # piggyback: free any dead-runner claims before self-claiming
    nodes = _linear_graphql(_MESH_AUTO_QUERY).get("issues", {}).get("nodes", [])
    open_ids = _open_claim_ids()
    candidates = sorted(
        (n for n in nodes if n.get("identifier") and n["identifier"] not in open_ids),
        key=lambda n: (_priority_rank(n.get("priority")), n["identifier"]),
    )
    for tk in candidates:
        ident = tk["identifier"]
        status, _ = _sb("POST", "mesh_work_claims",
                        {"linear_id": ident, "machine": body.host, "state": "claimed"},
                        prefer="return=minimal")
        if status < 300:
            _mark_issue_in_progress(tk)  # leave the mesh:auto pool — no re-claim loop
            return {"claimed": {"linear_id": ident, "machine": body.host}}
        # status 409 = raced by another node → try the next candidate
    return {"claimed": None, "reason": "queue empty or fully claimed"}
