"""POST /api/mesh/ship — append one row to mesh_ships (RA-7377).

Same X-Pi-CEO-Secret gate and service-role write path as /api/mesh/heartbeat.
Kept out of routes/mesh.py so that file stays on its 438-line ratchet.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .. import mesh_ship_write
from . import mesh as mesh_routes

router = APIRouter(prefix="/api/mesh", tags=["mesh"])


class ShipReport(BaseModel):
    machine: str = Field(min_length=1, max_length=128)
    repo: str = Field(min_length=1, max_length=256)
    branch: Optional[str] = Field(default=None, max_length=256)
    sha: Optional[str] = Field(default=None, max_length=40)
    subject: Optional[str] = Field(default=None, max_length=512)
    files_changed: int = Field(default=0, ge=0, le=100_000)


@router.post("/ship")
def ship(
    body: ShipReport,
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
):
    """Record one successful mesh ship. Machines never hold the service-role key."""
    mesh_routes._check_secret(x_pi_ceo_secret)
    try:
        row = mesh_ship_write.build_row(body.model_dump())
    except mesh_ship_write.ShipRejected as exc:
        raise HTTPException(422, str(exc)) from exc
    status, _ = mesh_routes._sb("POST", "mesh_ships", row, prefer="return=minimal")
    if status >= 300:
        raise HTTPException(502, f"ship insert failed ({status})")
    return {"ok": True, "machine": row["machine"], "repo": row["repo"], "sha": row["sha"]}


__all__ = ["router", "ShipReport"]
