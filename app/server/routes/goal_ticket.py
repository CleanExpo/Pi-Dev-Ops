"""Goal → Linear: projects, analyze (no write), file only after approval."""
from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_auth, require_rate_limit
from ..goal_analyze import analyze_goal
from ..goal_projects import create_project, get_project, load_projects, validate_brief
from ..goal_ticket import file_drafts
from ..models import GoalProjectCreate, GoalTicketFileRequest, GoalTicketRequest

router = APIRouter()

_LINEAR_DEST_REPO = "CleanExpo/Pi-Dev-Ops"


def _raise_goal_error(result: dict) -> None:
    err = result.get("error")
    if err == "validation":
        raise HTTPException(
            400,
            {
                "error": "validation",
                "fields": result.get("fields") or [],
                "hint": "goal, acceptance, and project_id are required.",
            },
        )
    if err == "unknown_project":
        raise HTTPException(
            400,
            {
                "error": "unknown_project",
                "project_id": result.get("project_id"),
                "hint": "Create a project first, then select it.",
            },
        )
    if err == "unknown_repo":
        raise HTTPException(
            400,
            {
                "error": "unknown_repo",
                "repo": result.get("repo"),
                "hint": "Linear destination could not be resolved.",
            },
        )
    if err == "not_approved":
        raise HTTPException(
            400,
            {
                "error": "not_approved",
                "hint": "Linear is not written until the proposed tickets are approved.",
            },
        )
    if err == "no_api_key":
        raise HTTPException(503, "LINEAR_API_KEY is not configured")
    if err == "backlog_state_missing":
        raise HTTPException(502, "Linear team has no Backlog workflow state")
    if err:
        raise HTTPException(502, result)


@router.get(
    "/api/goal-projects",
    dependencies=[Depends(require_auth), Depends(require_rate_limit)],
)
def list_goal_projects() -> dict:
    return {"projects": load_projects()}


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
    return {"project": create_project(body.model_dump())}


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
    brief = get_project(body.project_id)
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
