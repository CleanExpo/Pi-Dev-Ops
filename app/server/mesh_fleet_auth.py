"""mesh_fleet_auth.py — who may read `GET /api/mesh/fleet` (RA-7846).

The fleet snapshot is read-only, but it sat behind the same shared secret that
lets a machine write heartbeats and claim work. The dashboard on Vercel holds
none of that and should not: giving it the write-capable secret to draw a tile
would hand a browser-facing host the keys to the whole fleet.

`TAO_FLEET_READ_SECRET` is a second, read-only credential accepted by the
fleet snapshot and by nothing else. The shared secret keeps working for
machines, so nothing already running is disturbed.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from . import internal_secret


def check(secret: Optional[str]) -> None:
    """Raise 503 when no key is configured, 401 when this one matches none.

    The decision, the read-only key included, belongs to internal_secret (RA-8408).
    """
    result = internal_secret.classify_fleet_read(secret)
    if result == "unconfigured":
        raise HTTPException(503, "TAO_INTERNAL_WEBHOOK_SECRET not configured on server")
    if not internal_secret.accepted(result):
        raise HTTPException(401, "Invalid or missing X-Pi-CEO-Secret")
