"""Margot asset preview routes — manifest dry-run + build packet browser."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth import require_auth
from ..margot_assets_service import (
    MargotAssetsError,
    create_build_packet,
    get_options,
    list_build_packets,
    list_generated_assets,
    preview_asset,
    read_build_packet,
)
from scripts.margot_generate import MargotGenerationError

router = APIRouter(prefix="/api/margot/assets", tags=["margot-assets"])


class BuildPacketRequest(BaseModel):
    projects: list[str] | None = None
    variants: list[str] | None = None
    notes: str = Field(default="", max_length=500)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, MargotAssetsError):
        return HTTPException(404, str(exc))
    if isinstance(exc, MargotGenerationError):
        return HTTPException(400, str(exc))
    return HTTPException(500, str(exc))


@router.get("/options", dependencies=[Depends(require_auth)])
async def margot_asset_options():
    """Manifest summary: projects, variants, model, canonical asset state."""
    try:
        return get_options()
    except MargotGenerationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/preview", dependencies=[Depends(require_auth)])
async def margot_asset_preview(
    project: str = Query(..., min_length=1, max_length=64),
    variant: str = Query(..., min_length=1, max_length=64),
    notes: str = Query(default="", max_length=500),
):
    """Dry-run payload + provenance for one project/variant pair."""
    try:
        return preview_asset(project=project, variant=variant, notes=notes)
    except (MargotGenerationError, MargotAssetsError) as exc:
        raise _http_error(exc) from exc


@router.get("/packets", dependencies=[Depends(require_auth)])
async def margot_build_packets(limit: int = Query(default=10, ge=1, le=50)):
    return {"packets": list_build_packets(limit=limit)}


@router.get("/packets/{filename}", dependencies=[Depends(require_auth)])
async def margot_build_packet_detail(filename: str):
    try:
        return read_build_packet(filename)
    except (MargotAssetsError, MargotGenerationError) as exc:
        raise _http_error(exc) from exc


@router.post("/packets", dependencies=[Depends(require_auth)])
async def margot_build_packet_create(body: BuildPacketRequest):
    """Build a dry-run matrix packet (never calls OpenAI)."""
    try:
        return create_build_packet(
            projects=body.projects,
            variants=body.variants,
            notes=body.notes,
        )
    except MargotGenerationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/generated", dependencies=[Depends(require_auth)])
async def margot_generated_assets(limit: int = Query(default=20, ge=1, le=100)):
    return {"assets": list_generated_assets(limit=limit)}
