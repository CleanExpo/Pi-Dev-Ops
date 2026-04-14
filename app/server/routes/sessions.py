"""Session routes: build, list, kill, SSE logs, resume (RA-937)."""
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..auth import require_auth, require_rate_limit
from ..sessions import create_session, get_session, list_sessions, kill_session, _sessions, run_build
from ..orchestrator import fan_out
from ..models import BuildRequest, ParallelBuildRequest
from .. import config, persistence

router = APIRouter()


@router.post("/api/build", dependencies=[Depends(require_auth), Depends(require_rate_limit)])
async def build(body: BuildRequest):
    evaluator_enabled = body.evaluator_enabled if body.evaluator_enabled is not None else config.EVALUATOR_ENABLED
    # RA-677: per-request budget overrides global default; global default overrides None
    budget = body.budget_minutes or config.AUTONOMY_BUDGET_MINS or None
    try:
        session = await create_session(
            body.repo_url, body.brief, body.model,
            evaluator_enabled=evaluator_enabled,
            intent=body.intent,
            budget_minutes=budget,
            scope=body.scope,                       # RA-676: session scope contract
            plan_discovery=body.plan_discovery,     # RA-679: plan variation discovery
            complexity_tier=body.complexity_tier,   # RA-681: brief tier override
        )
    except RuntimeError as e:
        raise HTTPException(429, str(e))
    return {"session_id": session.id, "status": session.status}


@router.post("/api/build/parallel", dependencies=[Depends(require_auth), Depends(require_rate_limit)])
async def build_parallel(body: ParallelBuildRequest):
    """Fan-out a complex brief across N parallel worker sessions (RA-464)."""
    if not body.brief:
        raise HTTPException(400, "brief required for parallel builds")
    evaluator_enabled = body.evaluator_enabled if body.evaluator_enabled is not None else config.EVALUATOR_ENABLED
    result = await fan_out(
        body.repo_url, body.brief,
        n_workers=body.n_workers, model=body.model,
        intent=body.intent, evaluator_enabled=evaluator_enabled,
    )
    return result


def _find_active_session_for_repo(repo_url: str) -> str | None:
    """Return the session ID of the first non-terminal session for repo_url, or None."""
    terminal = {"done", "complete", "failed", "killed", "interrupted"}
    for s in _sessions.values():
        if s.repo_url == repo_url and s.status not in terminal:
            return s.id
    return None


@router.get("/api/sessions", dependencies=[Depends(require_auth)])
async def get_sessions():
    return list_sessions()


@router.post("/api/sessions/{sid}/kill", dependencies=[Depends(require_auth)])
async def stop_session(sid: str):
    if not await kill_session(sid):
        raise HTTPException(404, "Not found")
    return {"ok": True}


@router.get("/api/sessions/{sid}/logs", dependencies=[Depends(require_auth)])
async def stream_session_logs(sid: str, after: int = 0):
    """SSE stream of build log events for a session.

    Query param `after` = index of the last event the client has seen (0 = all).
    Streams existing events immediately, then polls for new ones until terminal.
    """
    session = get_session(sid)
    if not session:
        raise HTTPException(404, "Session not found")

    terminal = {"done", "complete", "failed", "killed"}

    async def generate():
        cursor = after
        while True:
            lines = session.output_lines
            while cursor < len(lines):
                event = lines[cursor]
                yield f"data: {json.dumps({'i': cursor, **event})}\n\n"
                cursor += 1
            if session.status in terminal:
                yield "data: {\"type\":\"done\",\"text\":\"\"}\n\n"
                break
            await asyncio.sleep(0.3)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/sessions/{sid}/resume", dependencies=[Depends(require_auth)])
async def resume_session(sid: str):
    """Resume an interrupted session from its last completed phase (GROUP E)."""
    session = get_session(sid)
    if not session:
        raise HTTPException(404, "Session not found")
    if session.status != "interrupted":
        raise HTTPException(400, f"Status is '{session.status}', not 'interrupted'")
    last_phase = getattr(session, "last_completed_phase", "")
    if not last_phase:
        raise HTTPException(400, "No phase checkpoint — cannot resume")
    session.status = "building"
    persistence.save_session(session)
    asyncio.create_task(run_build(session, resume_from=last_phase))
    return {"session_id": session.id, "resumed_from": last_phase}
