"""Idea pipeline API — intake, Board packet, one-word dispose, GO gate."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from ..auth import require_auth
from ..idea_pipeline import (
    PipelineGateError,
    append_and_examine,
    authorize_go_for,
    daily_snapshot,
    dispose_idea,
    examine_intake,
    try_execute_idea,
)

router = APIRouter(prefix="/api/idea-pipeline", tags=["idea-pipeline"])


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


class IntakeBody(BaseModel):
    text: str = Field(..., min_length=8, max_length=2000)
    source: str = Field(default="phill")

    @field_validator("source")
    @classmethod
    def valid_source(cls, value: str) -> str:
        source = (value or "").strip().lower()
        if source not in {"phill", "margot"}:
            raise ValueError("source must be phill or margot")
        return source


class DisposeBody(BaseModel):
    idea_id: str = Field(..., min_length=8, max_length=40)
    verdict: str = Field(..., min_length=3, max_length=16)


class IdeaIdBody(BaseModel):
    idea_id: str = Field(..., min_length=8, max_length=40)


def _gate(exc: PipelineGateError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


@router.get("", dependencies=[Depends(require_auth)])
async def get_pipeline() -> dict:
    root = _repo_root()
    snapshot = daily_snapshot(root)
    return {"snapshot": snapshot, "packets": examine_intake(root)}


@router.post("/intake", dependencies=[Depends(require_auth)])
async def post_intake(body: IntakeBody) -> dict:
    try:
        packet = append_and_examine(_repo_root(), body.text, source=body.source)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"packet": packet}


@router.post("/examine", dependencies=[Depends(require_auth)])
async def post_examine() -> dict:
    packets = examine_intake(_repo_root())
    return {"packets": packets, "snapshot": daily_snapshot(_repo_root())}


@router.post("/dispose", dependencies=[Depends(require_auth)])
async def post_dispose(body: DisposeBody) -> dict:
    try:
        packet = dispose_idea(_repo_root(), body.idea_id, body.verdict)
    except PipelineGateError as exc:
        raise _gate(exc) from exc
    return {"packet": packet, "executed": False}


@router.post("/go", dependencies=[Depends(require_auth)])
async def post_go(body: IdeaIdBody) -> dict:
    try:
        packet = authorize_go_for(_repo_root(), body.idea_id)
    except PipelineGateError as exc:
        raise _gate(exc) from exc
    return {"packet": packet, "executed": False, "go": True}


@router.post("/execute", dependencies=[Depends(require_auth)])
async def post_execute(body: IdeaIdBody) -> dict:
    try:
        packet = try_execute_idea(_repo_root(), body.idea_id)
    except PipelineGateError as exc:
        raise _gate(exc) from exc
    return {
        "packet": packet,
        "executed": False,
        "authorized": True,
        "note": "GO recorded. The idea pipeline does not auto-start a build.",
    }
