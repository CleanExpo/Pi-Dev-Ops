"""
Telegram proxy routes — second-brain backend endpoints.

Every endpoint is auth-gated (`require_auth`) so the bot's backend cookie is the
only caller in practice. Each endpoint bridges a Telegram slash command to
either Linear GraphQL or Pi-CEO internals:

  POST /api/telegram/linear/create       body: {title, project_id?}
  GET  /api/telegram/linear/status/{iid} Linear issue + latest comment
  GET  /api/telegram/pipeline/{iid}      Phase snapshot for a ticket
  POST /api/telegram/ship                {issue_id} -> triggers ship_build
  POST /api/telegram/plan                {brief, project_id?} -> plan_build
  GET  /api/telegram/digest              portfolio snapshot (live)

Failures return HTTP 502 with a concise error string (never silent 200 success).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import require_auth
from .. import config

log = logging.getLogger("pi-ceo.telegram_proxy")
router = APIRouter(prefix="/api/telegram", tags=["telegram"])

_LINEAR_ENDPOINT = "https://api.linear.app/graphql"


# ── Helpers ─────────────────────────────────────────────────────────────────
def _linear_key() -> str:
    key = os.environ.get("LINEAR_API_KEY", "").strip()
    if not key:
        raise HTTPException(502, "LINEAR_API_KEY not configured")
    return key


def _linear_graphql(query: str, variables: dict | None = None) -> dict:
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        _LINEAR_ENDPOINT,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": _linear_key(),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise HTTPException(502, f"Linear HTTP {exc.code}: {exc.read()[:200].decode(errors='ignore')}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise HTTPException(502, f"Linear transport error: {exc}") from exc
    if "errors" in data:
        raise HTTPException(502, f"Linear GraphQL errors: {data['errors']}")
    return data.get("data", {}) or {}


def _projects_json_path() -> Path:
    """Walk up from this file to find .harness/projects.json."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / ".harness" / "projects.json"
        if candidate.is_file():
            return candidate
    return Path("/app/.harness/projects.json")


def _project_routing(project_id: str | None) -> dict:
    """Resolve project_id -> Linear team + project IDs from .harness/projects.json."""
    path = _projects_json_path()
    default = {
        "teamId": config.LINEAR_TEAM_ID,
        "projectId": config.LINEAR_PROJECT_ID,
    }
    if not project_id:
        return default
    try:
        data = json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        log.warning("projects.json unreadable at %s: %s", path, exc)
        return default
    for p in data.get("projects", []):
        if p.get("id") == project_id:
            team_id = p.get("linear_team_id") or default["teamId"]
            proj_id = p.get("linear_project_id") or default["projectId"]
            return {"teamId": team_id, "projectId": proj_id}
    return default


# ── /linear/create ──────────────────────────────────────────────────────────
class LinearCreateBody(BaseModel):
    title: str
    project_id: str | None = None
    description: str | None = None
    priority: int = 2  # Linear: 0=none, 1=urgent, 2=high, 3=medium, 4=low


@router.post("/linear/create", dependencies=[Depends(require_auth)])
async def linear_create(body: LinearCreateBody) -> dict:
    routing = _project_routing(body.project_id)
    mutation = """
    mutation Create($input: IssueCreateInput!) {
      issueCreate(input: $input) {
        success
        issue { id identifier url title }
      }
    }
    """
    inp = {
        "teamId": routing["teamId"],
        "title": body.title,
        "priority": body.priority,
    }
    if routing.get("projectId"):
        inp["projectId"] = routing["projectId"]
    if body.description:
        inp["description"] = body.description

    data = _linear_graphql(mutation, {"input": inp})
    result = data.get("issueCreate", {}) or {}
    if not result.get("success"):
        raise HTTPException(502, "Linear issueCreate returned success=false")
    issue = result.get("issue", {}) or {}
    return {
        "id": issue.get("id"),
        "identifier": issue.get("identifier"),
        "url": issue.get("url"),
        "title": issue.get("title"),
    }


# ── /linear/status/{issue_id} ───────────────────────────────────────────────
@router.get("/linear/status/{issue_id}", dependencies=[Depends(require_auth)])
async def linear_status(issue_id: str) -> dict:
    query = """
    query($id: String!) {
      issue(id: $id) {
        identifier
        title
        url
        state { name type }
        assignee { name }
        comments(first: 1, orderBy: updatedAt) {
          nodes { body createdAt user { name } }
        }
      }
    }
    """
    data = _linear_graphql(query, {"id": issue_id})
    issue = data.get("issue")
    if not issue:
        raise HTTPException(404, f"Issue {issue_id} not found")
    latest = ""
    nodes = (issue.get("comments") or {}).get("nodes") or []
    if nodes:
        c = nodes[0]
        who = (c.get("user") or {}).get("name", "?")
        latest = f"{who}: {c.get('body', '')}"
    return {
        "identifier": issue.get("identifier"),
        "title": issue.get("title"),
        "url": issue.get("url"),
        "state": (issue.get("state") or {}).get("name", "?"),
        "assignee": (issue.get("assignee") or {}).get("name", "unassigned"),
        "latest_comment": latest,
    }


# ── /pipeline/{issue_id} ────────────────────────────────────────────────────
@router.get("/pipeline/{issue_id}", dependencies=[Depends(require_auth)])
async def pipeline_snapshot(issue_id: str) -> dict:
    """Return {phases: [{name, status}]} for the most recent pipeline for this issue."""
    try:
        from ..pipeline import list_pipelines, load_pipeline_state
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"pipeline module unavailable: {exc}") from exc

    summaries = list_pipelines() or []
    # Find pipeline linked to this Linear issue (pipelines store linear_issue_id)
    match = None
    for s in summaries:
        if (s.get("linear_issue_id") or "").upper() == issue_id.upper():
            match = s
            break
    if not match:
        return {"phases": []}

    state = load_pipeline_state(match.get("pipeline_id", ""))
    if not state:
        return {"phases": []}

    # Convert PipelineState dataclass to phase list
    phase_order = ["spec", "plan", "build", "test", "ship"]
    phases = []
    for name in phase_order:
        phase = getattr(state, f"{name}_phase", None) or getattr(state, name, None)
        status = "pending"
        if phase:
            st = getattr(phase, "status", None) or (phase.get("status") if isinstance(phase, dict) else None)
            if st:
                status = str(st).lower()
        phases.append({"name": name, "status": status})
    return {"phases": phases}


# ── /ship ───────────────────────────────────────────────────────────────────
class ShipBody(BaseModel):
    issue_id: str


@router.post("/ship", dependencies=[Depends(require_auth)])
async def ship(body: ShipBody) -> dict:
    """Trigger the ship phase for the most recent pipeline tied to this Linear issue."""
    try:
        from ..pipeline import list_pipelines, run_ship_phase
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"pipeline module unavailable: {exc}") from exc

    for s in list_pipelines() or []:
        if (s.get("linear_issue_id") or "").upper() == body.issue_id.upper():
            pid = s.get("pipeline_id")
            try:
                state = run_ship_phase(pid)
                ship_log = getattr(state, "ship_log", None) or {}
                return {
                    "session_id": pid,
                    "status": "shipped" if ship_log.get("shipped") else "failed",
                }
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(502, f"ship failed: {exc}") from exc
    raise HTTPException(404, f"No pipeline found for {body.issue_id}")


# ── /plan ───────────────────────────────────────────────────────────────────
class PlanBody(BaseModel):
    brief: str
    project_id: str | None = None


@router.post("/plan", dependencies=[Depends(require_auth)])
async def plan(body: PlanBody) -> dict:
    """Run plan phase synchronously and return the outline text."""
    try:
        from ..pipeline import run_plan_phase, run_spec_phase
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"pipeline module unavailable: {exc}") from exc

    import uuid as _uuid

    pipeline_id = _uuid.uuid4().hex[:8]
    repo_url = ""
    if body.project_id:
        try:
            data = json.loads(_projects_json_path().read_text())
            for p in data.get("projects", []):
                if p.get("id") == body.project_id:
                    repo_url = p.get("repo", "") or p.get("repo_url", "")
                    break
        except Exception:  # noqa: BLE001
            pass

    try:
        run_spec_phase(body.brief, repo_url, pipeline_id=pipeline_id)
        state = run_plan_phase(pipeline_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"plan failed: {exc}") from exc

    outline = ""
    plan_phase = getattr(state, "plan_phase", None) or getattr(state, "plan", None)
    if plan_phase:
        outline = getattr(plan_phase, "output", "") or (
            plan_phase.get("output", "") if isinstance(plan_phase, dict) else ""
        )
    return {"pipeline_id": pipeline_id, "outline": outline}


# ── /digest ─────────────────────────────────────────────────────────────────
@router.get("/digest", dependencies=[Depends(require_auth)])
async def digest_on_demand() -> dict:
    """On-demand portfolio digest — same aggregator used by scheduled 08:00/20:00 pushes."""
    try:
        from ..digest import render_digest_text
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"digest module unavailable: {exc}") from exc

    try:
        return {"text": render_digest_text()}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"digest assembly failed: {exc}") from exc
