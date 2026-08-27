"""Mission Control Model Fabric status API."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth import require_auth
from ..model_fabric import status_snapshot

router = APIRouter(prefix="/api/model-fabric", tags=["model-fabric"])


@router.get("/status")
def model_fabric_status(_: object = Depends(require_auth)) -> dict:
    return status_snapshot()


__all__ = ["router"]
