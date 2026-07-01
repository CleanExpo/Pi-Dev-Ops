"""Spec pipeline API routes."""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import require_auth
from ..spec_pipeline import run_pipeline
from ..spec_pipeline import persistence as persist

log = logging.getLogger("pi-ceo.routes.spec_pipeline")

router = APIRouter(prefix="/api/spec-pipeline", tags=["spec-pipeline"])

_running: dict[str, str] = {}


class RunRequest(BaseModel):
    proposal: str = Field(..., min_length=10, max_length=8000)
    dry_run: bool = True


async def _run_bg(pipeline_id: str, proposal: str, dry_run: bool) -> None:
    _running[pipeline_id] = "running"
    try:
        result = await run_pipeline(
            proposal,
            trigger="mission_control",
            dry_run=dry_run,
            pipeline_id=pipeline_id,
        )
        _running[pipeline_id] = result.status
    except Exception as exc:  # noqa: BLE001
        log.exception("spec pipeline failed")
        _running[pipeline_id] = f"error:{exc}"


@router.get("", dependencies=[Depends(require_auth)])
async def list_pipelines(limit: int = 20):
    return {"pipelines": persist.list_pipelines(limit=limit)}


@router.get("/{pipeline_id}", dependencies=[Depends(require_auth)])
async def get_pipeline(pipeline_id: str):
    if not pipeline_id.startswith("spec-"):
        raise HTTPException(400, "invalid pipeline id")
    meta = persist.read_json(pipeline_id, "meta.json")
    if meta is None:
        raise HTTPException(404, "pipeline not found")
    return {
        "meta": meta,
        "running": _running.get(pipeline_id),
        "handoff": (persist.pipeline_dir(pipeline_id) / "08-handoff.md").is_file(),
    }


@router.post("/run", dependencies=[Depends(require_auth)])
async def start_pipeline(body: RunRequest, background_tasks: BackgroundTasks):
    pipeline_id = persist.new_pipeline_id()
    background_tasks.add_task(_run_bg, pipeline_id, body.proposal, body.dry_run)
    return {"pipeline_id": pipeline_id, "status": "queued", "dry_run": body.dry_run}
