"""GET /api/mesh/claim/brief — the brief for a claim the dispatcher assigned.

`mesh_work_claims` has no text columns, so a dispatcher-assigned claim reaches its
runner without the ticket's title or description, and the runner used to stop every
such run (mesh/fleet_state.py). The runner now asks here. The server reads Linear with
its own key, so execution nodes stay credential-free (mesh/prompt.py says why).

Ticket text goes only to the node holding an OPEN claim on that exact ticket, by host
and claim row id; Linear is not read otherwise. That answers the warning recorded with
the gap, that enriching claims would hand ticket text to any holder of the mesh secret.
The same caps as `/claim/self` apply: the text is untrusted and reaches an unattended agent.

Kept out of routes/mesh.py so that file stays on its line-count ratchet.
"""
from __future__ import annotations

import urllib.parse
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from .. import mesh_fleet, mesh_lanes
from . import mesh as mesh_routes

router = APIRouter(prefix="/api/mesh", tags=["mesh"])


def _holds_open_claim(linear_id: str, host: str, claim_id: str) -> bool:
    """Whether `host` holds the open claim row `claim_id` on `linear_id`. 503 when unreadable."""
    q = urllib.parse.quote
    path = (f"mesh_work_claims?select=id&linear_id=eq.{q(linear_id)}&machine=eq.{q(host)}"
            f"&id=eq.{q(claim_id)}&state=in.(claimed,working)")
    rows, problem = mesh_fleet.read(mesh_routes._get, path)
    if problem:
        raise HTTPException(503, f"claim read failed ({problem}); cannot tell who holds the ticket")
    return bool(rows)


def _repo_for(issue: dict) -> Optional[str]:
    """The registered repo a build ticket must be built in; None when it needs none.

    409 when it needs one and none is registered: the runner would otherwise build it
    in its default repository, which is the wrong-repo failure W1b closed for self-claim.
    """
    if not mesh_lanes.needs_repo(issue):
        return None
    try:
        repos = mesh_lanes.registry_repos()
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "project registry could not be read; not guessing a repository") from exc
    repo = mesh_lanes.repo_of(issue, repos)
    if not repo:
        raise HTTPException(409, "ticket's project has no registered repository")
    return repo


@router.get("/claim/brief")
def claim_brief(
    linear_id: str = Query(min_length=1, max_length=64),
    host: str = Query(min_length=1, max_length=128),
    claim_id: str = Query(min_length=1, max_length=64),
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
):
    """Title, description, lane and repo of the ticket on `host`'s open claim."""
    mesh_routes._check_secret(x_pi_ceo_secret)
    if not _holds_open_claim(linear_id, host, claim_id):
        raise HTTPException(409, "no open claim on this ticket for this host and claim id")
    issue = mesh_lanes.read_issue(mesh_routes._linear_graphql, linear_id)
    if not issue:
        raise HTTPException(503, "Linear could not be read for this ticket")
    if reason := mesh_lanes.run_refusal(issue):
        raise HTTPException(409, f"ticket may no longer run: {reason}")
    return {
        "linear_id": linear_id,
        "title": (issue.get("title") or "")[:mesh_routes._TITLE_MAX_CHARS],
        "description": (issue.get("description") or "")[:mesh_routes._BRIEF_MAX_CHARS],
        "lane": mesh_lanes.lane_of(issue),
        "repo": _repo_for(issue),
    }


__all__ = ["router"]
