"""cost_report.py — RA-1909 phase-1 cost visibility endpoint.

Exposes today's LLM spend (read from .harness/llm-cost.jsonl via
swarm.budget_tracker) at GET /api/cost-report.

Auth: ``X-Pi-CEO-Secret`` header == ``TAO_WEBHOOK_SECRET`` — same scheme
the margot + morning-intel routes use.
"""
from __future__ import annotations

import hmac as _hmac
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from .. import config

log = logging.getLogger("pi-ceo.routes.cost_report")

router = APIRouter()


def _check_secret(x_pi_ceo_secret: Optional[str]) -> None:
    if not config.WEBHOOK_SECRET:
        raise HTTPException(503, "TAO_WEBHOOK_SECRET not configured on server")
    if not x_pi_ceo_secret:
        raise HTTPException(401, "Missing X-Pi-CEO-Secret header")
    if not _hmac.compare_digest(x_pi_ceo_secret, config.WEBHOOK_SECRET):
        raise HTTPException(401, "Invalid X-Pi-CEO-Secret")


@router.get("/api/cost-report")
async def cost_report(
    since: str = Query(default="24h", description="Time window — only '24h' supported in phase 1"),
    tenant_id: str = Query(default="pi-ceo", description="Tenant filter"),
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
):
    """Return today's spend summary.

    Response shape:
      {
        "by_provider": {provider: usd},
        "by_role": {role: usd},
        "total_usd": float,
        "day_iso": "YYYY-MM-DD",
        "since": "24h",
        "tenant_id": "pi-ceo"
      }
    """
    _check_secret(x_pi_ceo_secret)

    # Lazy import — keeps the route importable in test envs without
    # the swarm dependency wired up.
    try:
        from swarm import budget_tracker  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        log.exception("budget_tracker import failed")
        raise HTTPException(500, f"budget_tracker unavailable: {exc}") from exc

    try:
        by_provider = budget_tracker.by_provider_24h(tenant_id=tenant_id)
        by_role = budget_tracker.by_role_24h(tenant_id=tenant_id)
        total = budget_tracker.daily_total_usd(tenant_id=tenant_id)
    except Exception as exc:  # noqa: BLE001 — defensive; budget tracker should never raise
        log.exception("cost_report aggregation failed")
        raise HTTPException(500, f"cost_report failed: {exc}") from exc

    day_iso = datetime.now(timezone.utc).date().isoformat()
    return {
        "by_provider": by_provider,
        "by_role": by_role,
        "total_usd": total,
        "day_iso": day_iso,
        "since": since,
        "tenant_id": tenant_id,
    }
