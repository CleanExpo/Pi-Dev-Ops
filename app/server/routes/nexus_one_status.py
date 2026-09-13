"""RA-7539 — read-only Nexus One synthetic status.

GET /api/nexus-one/status reports whether a live nexus_one router is mounted.
The status surface itself is not live registration. Unregistered never looks
healthy. Does not enroll a worker, dispatch work, or claim SHIPPED.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..auth import require_auth
from ..nexus_one.status import status_payload_for_app

router = APIRouter(prefix="/api/nexus-one", tags=["nexus-one-status"])


@router.get("/status")
def nexus_one_status(
    request: Request, _: object = Depends(require_auth)
) -> dict:
    return status_payload_for_app(request.app)


__all__ = ["router"]
