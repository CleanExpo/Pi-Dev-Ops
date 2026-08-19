"""POST /api/goal-ticket — Goal → Linear Backlog (first hop)."""
from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_auth, require_rate_limit
from ..goal_ticket import file_goal
from ..models import GoalTicketRequest

router = APIRouter()


@router.post(
    "/api/goal-ticket",
    dependencies=[Depends(require_auth), Depends(require_rate_limit)],
)
async def create_goal_ticket(body: GoalTicketRequest) -> dict:
    result = file_goal(body.goal, body.repo, body.acceptance)
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
    if err == "no_api_key":
        raise HTTPException(503, "LINEAR_API_KEY is not configured")
    if err == "backlog_state_missing":
        raise HTTPException(502, "Linear team has no Backlog workflow state")
    if err:
        raise HTTPException(502, result)
    return result
