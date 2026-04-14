"""Ship Chain pipeline routes: spec, plan, test, ship, pipeline state (RA-937)."""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from ..auth import require_auth
from ..models import SpecRequest, PlanRequest, TestRequest, ShipRequest

log = logging.getLogger("pi-ceo.main")

router = APIRouter()


@router.post("/api/spec", dependencies=[Depends(require_auth)])
async def run_spec(body: SpecRequest, background_tasks: BackgroundTasks):
    """Phase 1: Convert a raw idea into a structured spec.md."""
    from ..pipeline import run_spec_phase
    import uuid as _uuid

    pipeline_id = body.pipeline_id or _uuid.uuid4().hex[:8]

    def _run():
        try:
            run_spec_phase(body.idea, body.repo_url, pipeline_id=pipeline_id, model=body.model)
        except Exception as exc:
            log.error("Spec phase failed: pipeline=%s err=%s", pipeline_id, exc)

    background_tasks.add_task(_run)
    return {"ok": True, "pipeline_id": pipeline_id}


@router.post("/api/plan", dependencies=[Depends(require_auth)])
async def run_plan(body: PlanRequest, background_tasks: BackgroundTasks):
    """Phase 2: Convert spec.md into a concrete implementation plan.md."""
    from ..pipeline import run_plan_phase

    def _run():
        try:
            run_plan_phase(body.pipeline_id, model=body.model)
        except Exception as exc:
            log.error("Plan phase failed: pipeline=%s err=%s", body.pipeline_id, exc)

    background_tasks.add_task(_run)
    return {"ok": True, "pipeline_id": body.pipeline_id}


@router.post("/api/test", dependencies=[Depends(require_auth)])
async def run_test(body: TestRequest, background_tasks: BackgroundTasks):
    """Phase 4: Run smoke tests and record results."""
    from ..pipeline import run_test_phase

    def _run():
        try:
            run_test_phase(body.pipeline_id, body.session_id)
        except Exception as exc:
            log.error("Test phase failed: pipeline=%s err=%s", body.pipeline_id, exc)

    background_tasks.add_task(_run)
    return {"ok": True, "pipeline_id": body.pipeline_id}


@router.post("/api/ship", dependencies=[Depends(require_auth)])
async def run_ship(body: ShipRequest):
    """Phase 6: Hard gate + ship. Returns ship-log immediately (synchronous)."""
    from ..pipeline import run_ship_phase
    try:
        state = run_ship_phase(body.pipeline_id)
        ship_log = state.ship_log or {}
        return {"ok": ship_log.get("shipped", False), "pipeline_id": body.pipeline_id, "ship_log": ship_log}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/api/pipeline/{pipeline_id}", dependencies=[Depends(require_auth)])
async def get_pipeline(pipeline_id: str):
    """Return full PipelineState for a pipeline."""
    from ..pipeline import load_pipeline_state
    from dataclasses import asdict
    state = load_pipeline_state(pipeline_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Pipeline {pipeline_id} not found")
    return asdict(state)


@router.get("/api/pipelines", dependencies=[Depends(require_auth)])
async def get_pipelines():
    """List all pipeline summaries."""
    from ..pipeline import list_pipelines
    return list_pipelines()
