"""routing.py — RA-7434 read-only routing view for Mission Control.

GET /api/routing → per role: provider, model, the source of the choice
(``code-default`` / ``env:<NAME>`` / ``ladder-step-N``) and today's spend for
that role read from Supabase ``llm_costs``. When that read cannot happen the
cost is ``null`` with a ``reason`` — never a fake 0.

Auth: ``X-Pi-CEO-Secret`` header == ``TAO_WEBHOOK_SECRET`` — the cost_report
scheme, reused verbatim.
"""
from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Header, Query

from .. import provider_router as PR
from .cost_report import _check_secret

log = logging.getLogger("pi-ceo.routes.routing")

router = APIRouter()

# PostgREST's default max-rows is 1000; a page that size may be hiding rows,
# and a truncated sum would render as a smaller-than-real number.
_PAGE_CAP = 1000


def _env_set(name: str) -> bool:
    return bool((os.environ.get(name) or "").strip())


def _tier_source(pm: PR.ProviderModel) -> str:
    """Which env var decided a tier-default resolution, else code-default.

    Mirrors the precedence in provider_router._tier_default /
    _resolve_cheap_tier without re-deciding anything.
    """
    if pm.tier == "top":
        if os.environ.get("TAO_TOP_USE_CLAUDE_PRINT", "").strip() == "1":
            return "env:TAO_TOP_USE_CLAUDE_PRINT"
        return "env:TAO_TOP_MODEL" if _env_set("TAO_TOP_MODEL") else "code-default"
    if pm.tier == "mid":
        if os.environ.get("TAO_MID_USE_CLAUDE_PRINT", "").strip() == "1":
            return "env:TAO_MID_USE_CLAUDE_PRINT"
        return "env:TAO_MID_MODEL" if _env_set("TAO_MID_MODEL") else "code-default"
    if pm.tier == "cheap":
        if _env_set("TAO_CHEAP_MODEL"):
            return "env:TAO_CHEAP_MODEL"
        if pm.provider == "openrouter" and _env_set("TAO_CHEAP_REMOTE_MODEL"):
            return "env:TAO_CHEAP_REMOTE_MODEL"
        if pm.provider == "ollama" and _env_set("TAO_CHEAP_LOCAL_MODEL"):
            return "env:TAO_CHEAP_LOCAL_MODEL"
        # provider_router ignores an unknown pin and falls through to the probe;
        # only a value it honours may be credited as the source.
        if (os.environ.get("TAO_CHEAP_PROVIDER") or "").strip().lower() in ("ollama", "openrouter"):
            return "env:TAO_CHEAP_PROVIDER"
    return "code-default"


def _source_label(pm: PR.ProviderModel) -> str:
    if pm.source.startswith(("ladder-step-", "env:")):
        return pm.source
    if pm.source == "env_role_override":
        return f"env:{PR._env_role_key(pm.role)}"
    # "env_tier_default" and "tier_downgrade_corrected" both end on the tier default.
    return _tier_source(pm)


def _resolve(role: str) -> dict[str, Any]:
    try:
        # Read-only: never append a tier-downgrade row to the violations ledger.
        pm = PR.select_provider_model(role, record_observation=False)
    except PR.RefusedModelError as exc:
        return {
            "tier": PR.ROLE_TIER.get(role, "mid"), "provider": None, "model": None,
            "source": f"env:{PR.MARGOT_CASUAL_ENV}", "error": str(exc),
        }
    return {
        "tier": pm.tier, "provider": pm.provider, "model": pm.model_id,
        "source": _source_label(pm), "error": None,
    }


def _cost_today_by_role(day_iso: str, tenant_id: str) -> tuple[Optional[dict[str, float]], Optional[str]]:
    """({role: usd}, None) from Supabase llm_costs, or (None, reason)."""
    from .. import supabase_log  # noqa: PLC0415

    url, key = supabase_log._cfg()
    if not url or not key:
        return None, "supabase not configured (NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY)"
    params = (
        f"select=role,cost_usd&ts=gte.{day_iso}T00:00:00Z"
        f"&tenant_id=eq.{supabase_log._q(tenant_id)}&limit={_PAGE_CAP}"
    )
    status, rows = supabase_log._request("GET", f"llm_costs?{params}", None, "")
    if not (200 <= status < 300) or not isinstance(rows, list):
        return None, f"llm_costs read failed (HTTP {status})"
    if len(rows) >= _PAGE_CAP:
        return None, f"llm_costs read hit the {_PAGE_CAP}-row page cap; a partial sum would be wrong"
    # One unusable row fails the whole aggregation closed: a partial sum would
    # render as a smaller-than-real number with no reason attached.
    out: dict[str, float] = {}
    for i, r in enumerate(rows):
        raw = r.get("cost_usd") if isinstance(r, dict) else None
        try:
            cost = float(raw)
        except (TypeError, ValueError):
            cost = math.nan
        if not math.isfinite(cost):
            return None, f"llm_costs row {i} has an unusable cost_usd={raw!r}; cost unknown"
        role = str(r.get("role") or "")  # role is nullable in the table; "" is the no-role bucket
        out[role] = round(out.get(role, 0.0) + cost, 6)
    return out, None


@router.get("/api/routing")
async def routing(
    tenant_id: str = Query(default="pi-ceo", description="Tenant filter for llm_costs"),
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
):
    _check_secret(x_pi_ceo_secret)
    day_iso = datetime.now(timezone.utc).date().isoformat()
    costs, cost_reason = _cost_today_by_role(day_iso, tenant_id)

    roles: dict[str, Any] = {}
    for role in sorted(PR.ROLE_TIER):
        row = _resolve(role)
        if costs is None:
            row["cost_today_usd"], row["cost_reason"] = None, cost_reason
        else:
            row["cost_today_usd"], row["cost_reason"] = costs.get(role, 0.0), None
        roles[role] = row

    return {
        "day_iso": day_iso,
        "tenant_id": tenant_id,
        "cost_source": None if costs is None else "supabase:llm_costs",
        "cost_reason": cost_reason,
        "roles": roles,
        "margot_casual": {
            "ladder": [f"{p}:{m}" for p, m in PR.MARGOT_CASUAL_LADDER],
            "override_env": PR.MARGOT_CASUAL_ENV,
            "refused_markers": list(PR.MARGOT_CASUAL_REFUSED_MARKERS),
        },
    }
