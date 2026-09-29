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

import hmac
import os
from typing import Optional

from fastapi import HTTPException

from . import config


def _accepted() -> list[str]:
    read_only = os.environ.get("TAO_FLEET_READ_SECRET", "").strip()
    return [s for s in (config.INTERNAL_WEBHOOK_SECRET, read_only) if s]


def check(secret: Optional[str]) -> None:
    """Raise 503 when no secret is configured, 401 when this one matches none."""
    accepted = _accepted()
    if not accepted:
        raise HTTPException(503, "TAO_INTERNAL_WEBHOOK_SECRET not configured on server")
    if not secret or not any(hmac.compare_digest(secret, ok) for ok in accepted):
        raise HTTPException(401, "Invalid or missing X-Pi-CEO-Secret")
