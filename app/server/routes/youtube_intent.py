"""Intent-only YouTube catalog APIs for Unite-Group Nexus."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..youtube_intent import (
    build_excalidraw_nodes,
    ensure_policy,
    load_state,
    synthesize_state,
    upsert_catalog,
)

try:
    from ..auth import require_auth  # type: ignore
except Exception:  # pragma: no cover
    async def require_auth():  # type: ignore[misc]
        return {"sub": "test-user"}


router = APIRouter(prefix="/api/nexus/youtube-intent", tags=["youtube-intent"])


class CatalogVideoItem(BaseModel):
    video_id: Optional[str] = None
    url: Optional[str] = None
    title: str = Field(..., min_length=1, max_length=300)
    channel: str = Field("", max_length=200)
    description: str = Field("", max_length=5000)
    tags: list[str] = Field(default_factory=list)
    watch_count_window: int = Field(1, ge=1, le=50000)
    selected_by_user: bool = False
    force_include: bool = False
    force_exclude: bool = False


class CatalogIngestRequest(BaseModel):
    items: list[CatalogVideoItem] = Field(default_factory=list)


@router.get("/policy")
async def get_policy(_auth=Depends(require_auth)):
    return {"policy": ensure_policy()}


@router.post("/catalog")
async def post_catalog(body: CatalogIngestRequest, _auth=Depends(require_auth)):
    result = upsert_catalog([item.model_dump() for item in body.items])
    return {
        "accepted": result.accepted,
        "excluded": result.excluded,
        "total": result.total,
        "status_breakdown": result.status_breakdown,
    }


@router.get("/catalog")
async def get_catalog(_auth=Depends(require_auth)):
    state = load_state()
    accepted = [row for row in state.get("videos", []) if row.get("status") == "accepted"]
    excluded = [row for row in state.get("videos", []) if row.get("status") == "excluded"]
    return {
        "updated_at": state.get("updated_at"),
        "accepted_count": len(accepted),
        "excluded_count": len(excluded),
        "accepted_items": accepted,
        "excluded_items": excluded,
    }


@router.post("/synthesize")
async def post_synthesize(_auth=Depends(require_auth)):
    state = synthesize_state()
    return {
        "updated_at": state.get("updated_at"),
        "topics": state.get("topics", []),
        "persona_traits": state.get("persona_traits", []),
        "vertical_pathway_signals": state.get("vertical_pathway_signals", []),
        "wiki_pages": state.get("wiki_pages", []),
    }


@router.get("/wiki")
async def get_wiki(_auth=Depends(require_auth)):
    state = load_state()
    previews: dict[str, Any] = {}
    for key in ("persona_traits", "topics", "vertical_pathway_signals", "wiki_pages"):
        previews[key] = state.get(key, [])
    return {"updated_at": state.get("updated_at"), **previews}


@router.get("/excalidraw-state")
async def get_excalidraw_state(_auth=Depends(require_auth)):
    state = load_state()
    return build_excalidraw_nodes(state)
