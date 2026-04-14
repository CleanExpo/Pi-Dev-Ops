"""Trigger CRUD routes: GET/POST/DELETE /api/triggers (RA-937)."""
from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_auth, require_rate_limit
from ..cron import list_triggers, create_trigger, delete_trigger
from ..models import TriggerRequest

router = APIRouter()


@router.get("/api/triggers", dependencies=[Depends(require_auth)])
async def get_triggers():
    return list_triggers()


@router.post("/api/triggers", dependencies=[Depends(require_auth), Depends(require_rate_limit)])
async def add_trigger(body: TriggerRequest):
    trigger = create_trigger(
        repo_url=body.repo_url,
        brief=body.brief,
        minute=body.minute,
        hour=body.hour,
        model=body.model,
    )
    return trigger


@router.delete("/api/triggers/{tid}", dependencies=[Depends(require_auth)])
async def remove_trigger(tid: str):
    if not delete_trigger(tid):
        raise HTTPException(404, "Trigger not found")
    return {"ok": True}
