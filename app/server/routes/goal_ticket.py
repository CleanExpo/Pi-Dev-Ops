"""Goal → Linear: analyze (no write), then file only after approval."""
from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_auth, require_rate_limit
from ..goal_analyze import analyze_goal
from ..goal_ticket import file_drafts
from ..models import GoalTicketFileRequest, GoalTicketRequest

router = APIRouter()


def _raise_goal_error(result: dict) -> None:
    err = result.get("error")
    if err == "validation":
        raise HTTPException(
            400,
            {
                "error": "validation",
                "fields": result.get("fields") or [],
                "hint": "goal, repo, and acceptance are required.",
            },
        )
    if err == "unknown_repo":
        raise HTTPException(
            400,
            {
                "error": "unknown_repo",
                "repo": result.get("repo"),
                "hint": "Repo must match an entry in config/harness/projects.json.",
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


@router.post(
    "/api/goal-ticket/analyze",
    dependencies=[Depends(require_auth), Depends(require_rate_limit)],
)
async def analyze_goal_ticket(body: GoalTicketRequest) -> dict:
    result = await analyze_goal(body.goal, body.repo, body.acceptance)
    if result.get("error"):
        _raise_goal_error(result)
    return result


@router.post(
    "/api/goal-ticket",
    dependencies=[Depends(require_auth), Depends(require_rate_limit)],
)
async def create_goal_ticket(body: GoalTicketFileRequest) -> dict:
    drafts = [t.model_dump() for t in body.tickets]
    result = file_drafts(
        body.repo,
        drafts,
        approved=body.approved,
        parent_goal=body.goal,
    )
    if result.get("error"):
        _raise_goal_error(result)
    return result
