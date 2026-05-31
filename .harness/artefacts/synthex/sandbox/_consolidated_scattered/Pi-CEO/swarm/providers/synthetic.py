"""swarm/providers/synthetic.py — deterministic CFO metrics provider.

Reads ``.harness/projects.json`` to enumerate the 11 Unite-Group businesses
and emits one ``RawMetrics`` per business with deterministic, plausible
numbers. Same input → same output across cycles, so breach-detection unit
tests are stable and the orchestrator's first cycle is always non-empty.

Used:
* by default when ``TAO_CFO_PROVIDER`` is unset or ``synthetic``
* as the per-business fallback inside ``stripe_xero`` provider when real
  credentials aren't configured for that business (so a partially-wired
  portfolio still emits a coherent brief)

The numbers are plausible but NOT real. Use ``stripe_xero`` provider once
real credentials are in env.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Literal

from ..cfo import RawMetrics

log = logging.getLogger("swarm.providers.synthetic")

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECTS_JSON_REL = ".harness/projects.json"

# Businesses default to b2b unless their projects.json id is in this set.
_PROSUMER_IDS: set[str] = {"synthex", "nodejs-starter"}


def _seed_int(business_id: str, salt: str) -> int:
    """Deterministic non-negative int from (business_id, salt)."""
    h = hashlib.sha256(f"{business_id}:{salt}".encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _scale(business_id: str, salt: str, *, lo: float, hi: float) -> float:
    """Deterministic float in [lo, hi] from (business_id, salt)."""
    n = _seed_int(business_id, salt)
    return lo + (n % 10_000) / 10_000.0 * (hi - lo)


def _business_type(bid: str) -> Literal["b2b", "prosumer"]:
    return "prosumer" if bid in _PROSUMER_IDS else "b2b"


def _synth_one(bid: str) -> RawMetrics:
    """Generate one plausible RawMetrics for a business id."""
    btype = _business_type(bid)

    # MRR scale: b2b 5k–50k, prosumer 0.5k–5k. Deterministic per id.
    if btype == "b2b":
        mrr = _scale(bid, "mrr", lo=5_000, hi=50_000)
    else:
        mrr = _scale(bid, "mrr", lo=500, hi=5_000)

    starting_mrr = mrr * _scale(bid, "start_mrr_ratio", lo=0.92, hi=1.05)
    expansion = mrr * _scale(bid, "expansion", lo=0.01, hi=0.08)
    contraction = mrr * _scale(bid, "contraction", lo=0.00, hi=0.04)
    churn = mrr * _scale(bid, "churn", lo=0.00, hi=0.05)
    new_mrr = mrr * _scale(bid, "new_mrr", lo=0.02, hi=0.15)

    # Cost structure
    revenue = mrr * _scale(bid, "rev_window", lo=0.95, hi=1.10)
    cogs = revenue * _scale(bid, "cogs_pct", lo=0.10, hi=0.25)
    monthly_burn = mrr * _scale(bid, "burn_ratio", lo=0.30, hi=0.95)
    cash_on_hand = monthly_burn * _scale(bid, "runway_months", lo=10, hi=36)

    # Acquisition
    customers = max(1, int(_seed_int(bid, "customers") % 50))
    cac_paid = mrr * _scale(bid, "cac_pct", lo=0.05, hi=0.20)

    # AI inference
    inference_cost = mrr * _scale(bid, "inference_pct", lo=0.005, hi=0.06)

    return RawMetrics(
        business_id=bid,
        mrr=round(mrr, 2),
        starting_mrr=round(starting_mrr, 2),
        expansion_mrr=round(expansion, 2),
        contraction_mrr=round(contraction, 2),
        churn_mrr=round(churn, 2),
        new_mrr=round(new_mrr, 2),
        cogs=round(cogs, 2),
        revenue=round(revenue, 2),
        cash_on_hand=round(cash_on_hand, 2),
        monthly_burn=round(monthly_burn, 2),
        cac_paid=round(cac_paid, 2),
        customers_acquired=customers,
        inference_cost=round(inference_cost, 2),
        business_type=btype,
    )


def _load_business_ids() -> list[str]:
    """Read .harness/projects.json and return the business id list."""
    p = REPO_ROOT / PROJECTS_JSON_REL
    if not p.exists():
        log.warning("synthetic: %s missing — returning []", p)
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("synthetic: %s unreadable (%s) — returning []", p, exc)
        return []
    return [proj["id"] for proj in data.get("projects", []) if proj.get("id")]


def synthetic_provider() -> list[RawMetrics]:
    """Deterministic provider — one RawMetrics per business in projects.json."""
    out: list[RawMetrics] = []
    for bid in _load_business_ids():
        try:
            out.append(_synth_one(bid))
        except Exception as exc:  # noqa: BLE001 — never crash the cycle
            log.warning("synthetic: skip %s (%s)", bid, exc)
    log.debug("synthetic: emitted %d metrics", len(out))
    return out


def synthetic_one(business_id: str) -> RawMetrics:
    """Public single-business entry-point for stripe_xero per-business fallback."""
    return _synth_one(business_id)


__all__ = ["synthetic_provider", "synthetic_one"]
