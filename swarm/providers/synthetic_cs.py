"""swarm/providers/synthetic_cs.py — deterministic CS-tier1 provider."""
from __future__ import annotations

import hashlib
import logging

from ..cs import RawCsMetrics
from .synthetic import _load_business_ids

log = logging.getLogger("swarm.providers.synthetic_cs")


def _seed_int(business_id: str, salt: str) -> int:
    h = hashlib.sha256(f"{business_id}:cs:{salt}".encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _scale(business_id: str, salt: str, *, lo: float, hi: float) -> float:
    n = _seed_int(business_id, salt)
    return lo + (n % 10_000) / 10_000.0 * (hi - lo)


def _synth_one(bid: str) -> RawCsMetrics:
    promoters = int(_scale(bid, "promoters", lo=20, hi=120))
    passives = int(_scale(bid, "passives", lo=10, hi=60))
    detractors = int(_scale(bid, "detractors", lo=0, hi=80))
    tickets_total = max(1, int(_scale(bid, "tickets", lo=10, hi=200)))
    fcr_pct = _scale(bid, "fcr", lo=0.45, hi=0.92)
    customers_at_start = max(1, int(_scale(bid, "cust_start", lo=20, hi=500)))
    customers_lost = int(_scale(bid, "cust_lost", lo=0,
                                 hi=customers_at_start * 0.20))
    first_response_m = _scale(bid, "first_response", lo=5, hi=300)
    enterprise_threats = int(_scale(bid, "enterprise", lo=0, hi=4))

    return RawCsMetrics(
        business_id=bid,
        nps_promoters=promoters,
        nps_passives=passives,
        nps_detractors=detractors,
        tickets_total=tickets_total,
        tickets_resolved_first_contact=int(round(tickets_total * fcr_pct)),
        customers_at_period_start=customers_at_start,
        customers_lost_in_period=customers_lost,
        avg_first_response_minutes=round(first_response_m, 1),
        open_enterprise_churn_threats=enterprise_threats,
    )


def synthetic_cs_provider() -> list[RawCsMetrics]:
    out: list[RawCsMetrics] = []
    for bid in _load_business_ids():
        try:
            out.append(_synth_one(bid))
        except Exception as exc:  # noqa: BLE001
            log.warning("synthetic_cs: skip %s (%s)", bid, exc)
    return out


def synthetic_cs_one(business_id: str) -> RawCsMetrics:
    return _synth_one(business_id)


__all__ = ["synthetic_cs_provider", "synthetic_cs_one"]
