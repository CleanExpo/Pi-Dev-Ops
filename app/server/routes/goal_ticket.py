"""Goal → Linear: projects, analyze (no write), file only after approval."""
from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_auth, require_rate_limit
from ..goal_analyze import analyze_goal
from ..goal_projects import (
    GoalProjectStoreError,
    create_project,
    get_project,
    load_projects,
    validate_brief,
)
from ..goal_ticket import file_drafts
from ..models import GoalProjectCreate, GoalTicketFileRequest, GoalTicketRequest

router = APIRouter()

_LINEAR_DEST_REPO = "CleanExpo/Pi-Dev-Ops"


def _error_detail(result: dict, extra: dict) -> dict:
    """Keep already-filed tickets on every Goal HTTP error."""
    body = dict(extra)
    if result.get("filed"):
        body["filed"] = result["filed"]
    if result.get("failed_title"):
        body["failed_title"] = result["failed_title"]
    return body


def _fail(status: int, result: dict, extra: dict) -> None:
    raise HTTPException(status, _error_detail(result, extra))


def _raise_goal_error(result: dict) -> None:
    err = result.get("error")
    if err == "validation":
        _fail(400, result, {
            "error": "validation",
            "fields": result.get("fields") or [],
            "hint": "Goal, acceptance, and a brief are required.",
        })
    if err == "unknown_project":
        _fail(400, result, {
            "error": "unknown_project",
            "project_id": result.get("project_id"),
            "hint": "Create a brief first, then select it.",
        })
    if err == "unknown_repo":
        _fail(400, result, {
            "error": "unknown_repo",
            "repo": result.get("repo"),
            "hint": "Linear destination could not be resolved.",
        })
    if err == "not_approved":
        _fail(400, result, {
            "error": "not_approved",
            "hint": "Linear is not written until you confirm Write.",
        })
    if err in {
        "supabase_not_configured",
        "supabase_read_failed",
        "supabase_write_failed",
        "file_store_disabled",
    }:
        _fail(503, result, {"error": err, "hint": result.get("hint") or "Database store failed."})
    if err == "no_api_key":
        _fail(503, result, {"error": err, "hint": "LINEAR_API_KEY is not configured"})
    if err == "backlog_state_missing":
        _fail(502, result, {"error": err, "hint": "Linear team has no Backlog workflow state"})
    if err:
        raise HTTPException(502, _error_detail(result, result))


@router.get(
    "/api/goal-projects",
    dependencies=[Depends(require_auth), Depends(require_rate_limit)],
)
def list_goal_projects() -> dict:
    try:
        return {"projects": load_projects()}
    except GoalProjectStoreError as exc:
        raise HTTPException(503, {"error": exc.code, "hint": exc.hint}) from exc


@router.post(
    "/api/goal-projects",
    dependencies=[Depends(require_auth), Depends(require_rate_limit)],
)
def create_goal_project(body: GoalProjectCreate) -> dict:
    missing = validate_brief(body.model_dump())
    if missing:
        raise HTTPException(
            400,
            {
                "error": "validation",
                "fields": missing,
                "hint": "title, description, and audience are required.",
            },
        )
    try:
        return {"project": create_project(body.model_dump())}
    except GoalProjectStoreError as exc:
        raise HTTPException(503, {"error": exc.code, "hint": exc.hint}) from exc


@router.post(
    "/api/goal-ticket/analyze",
    dependencies=[Depends(require_auth), Depends(require_rate_limit)],
)
async def analyze_goal_ticket(body: GoalTicketRequest) -> dict:
    result = await analyze_goal(body.goal, body.acceptance, body.project_id)
    if result.get("error"):
        _raise_goal_error(result)
    return result


@router.post(
    "/api/goal-ticket",
    dependencies=[Depends(require_auth), Depends(require_rate_limit)],
)
async def create_goal_ticket(body: GoalTicketFileRequest) -> dict:
    try:
        brief = get_project(body.project_id)
    except GoalProjectStoreError as exc:
        _raise_goal_error({"error": exc.code, "hint": exc.hint})
    if not brief:
        _raise_goal_error({"error": "unknown_project", "project_id": body.project_id})
    drafts = [t.model_dump() for t in body.tickets]
    result = file_drafts(
        _LINEAR_DEST_REPO,
        drafts,
        approved=body.approved,
        parent_goal=body.goal,
        project_title=brief["title"],
    )
    if result.get("error"):
        _raise_goal_error(result)
    return result
