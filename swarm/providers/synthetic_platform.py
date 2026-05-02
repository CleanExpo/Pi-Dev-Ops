"""swarm/providers/synthetic_platform.py — deterministic CTO platform provider.

Reads ``.harness/projects.json`` and emits one ``RawPlatformMetrics`` per
business with deterministic, plausible DORA + ops numbers. Same input →
same output across cycles.
"""
from __future__ import annotations

import hashlib
import logging

from ..cto import RawPlatformMetrics
from .synthetic import _load_business_ids

log = logging.getLogger("swarm.providers.synthetic_platform")


def _seed_int(business_id: str, salt: str) -> int:
    h = hashlib.sha256(f"{business_id}:cto:{salt}".encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _scale(business_id: str, salt: str, *, lo: float, hi: float) -> float:
    n = _seed_int(business_id, salt)
    return lo + (n % 10_000) / 10_000.0 * (hi - lo)


def _synth_one(bid: str) -> RawPlatformMetrics:
    deploys = int(_scale(bid, "deploys", lo=0.5, hi=12))
    lead_h = _scale(bid, "lead", lo=0.2, hi=72)
    mttr = _scale(bid, "mttr", lo=0.1, hi=30)
    total_changes = max(1, int(_scale(bid, "changes", lo=5, hi=80)))
    failures = int(_scale(bid, "failures", lo=0, hi=total_changes * 0.4))
    p99 = _scale(bid, "p99", lo=80, hi=1500)
    uptime = _scale(bid, "uptime", lo=0.985, hi=0.99999)
    cost_per_req = _scale(bid, "cost", lo=0.0002, hi=0.008)

    return RawPlatformMetrics(
        business_id=bid,
        deploys_last_week=deploys,
        lead_time_hours_p50=round(lead_h, 2),
        mttr_hours=round(mttr, 2),
        change_failure_count=failures,
        change_total_count=total_changes,
        p99_latency_ms=round(p99, 1),
        uptime_pct=round(uptime, 5),
        cost_per_request_usd=round(cost_per_req, 6),
        is_production_branch=True,
    )


def synthetic_platform_provider() -> list[RawPlatformMetrics]:
    """Deterministic provider — one RawPlatformMetrics per business."""
    out: list[RawPlatformMetrics] = []
    for bid in _load_business_ids():
        try:
            out.append(_synth_one(bid))
        except Exception as exc:  # noqa: BLE001
            log.warning("synthetic_platform: skip %s (%s)", bid, exc)
    return out


def synthetic_platform_one(business_id: str) -> RawPlatformMetrics:
    return _synth_one(business_id)


__all__ = ["synthetic_platform_provider", "synthetic_platform_one"]
