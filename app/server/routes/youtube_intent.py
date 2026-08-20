"""Intent-only YouTube catalog APIs for Unite-Group Nexus."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..youtube_connector import (
    build_oauth_start_payload,
    exchange_code,
    import_takeout,
    load_oauth_state,
    pull_live_signals,
)
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


class OAuthCallbackRequest(BaseModel):
    code: str = Field(..., min_length=1)
    state: str = Field("", max_length=500)
    redirect_uri: Optional[str] = None


class TakeoutImportRequest(BaseModel):
    entries: Optional[list[dict[str, Any]]] = None
    items: Optional[list[dict[str, Any]]] = None


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


@router.get("/oauth/start")
async def get_oauth_start(redirect_uri: Optional[str] = None, _auth=Depends(require_auth)):
    return build_oauth_start_payload(redirect_uri=redirect_uri)


@router.get("/oauth/state")
async def get_oauth_state(_auth=Depends(require_auth)):
    state = load_oauth_state()
    return {
        "connected": bool(state.get("connected")),
        "scope": state.get("scope", ""),
        "expires_at": state.get("expires_at", ""),
        "updated_at": state.get("updated_at", ""),
    }


@router.post("/oauth/callback")
async def post_oauth_callback(body: OAuthCallbackRequest, _auth=Depends(require_auth)):
    try:
        return exchange_code(code=body.code, state_value=body.state, redirect_uri=body.redirect_uri)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/pull-live")
async def post_pull_live(_auth=Depends(require_auth)):
    try:
        return pull_live_signals()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/import-takeout")
async def post_import_takeout(body: TakeoutImportRequest, _auth=Depends(require_auth)):
    payload: dict[str, Any] = {}
    if body.entries is not None:
        payload["entries"] = body.entries
    elif body.items is not None:
        payload["items"] = body.items
    try:
        return import_takeout(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
