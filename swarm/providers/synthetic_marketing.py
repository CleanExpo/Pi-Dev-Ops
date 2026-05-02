"""swarm/providers/synthetic_marketing.py — deterministic CMO metrics provider.

Reads ``.harness/projects.json`` to enumerate the 11 Unite-Group businesses
and emits one ``RawMarketingMetrics`` per business with deterministic,
plausible numbers. Same input → same output across cycles, so breach-
detection unit tests are stable and the orchestrator's first cycle is
always non-empty.

Used:
* by default when ``TAO_CMO_PROVIDER`` is unset or ``synthetic``
* as the per-business fallback inside future ad-platform providers
"""
from __future__ import annotations

import hashlib
import logging

from ..cmo import ChannelSpend, RawMarketingMetrics
from .synthetic import _load_business_ids

log = logging.getLogger("swarm.providers.synthetic_marketing")

# Fixed channel mix per business id seed — deterministic but varied.
_CHANNELS = ["google-ads", "linkedin", "meta", "seo", "referral", "youtube"]


def _seed_int(business_id: str, salt: str) -> int:
    h = hashlib.sha256(f"{business_id}:cmo:{salt}".encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _scale(business_id: str, salt: str, *, lo: float, hi: float) -> float:
    n = _seed_int(business_id, salt)
    return lo + (n % 10_000) / 10_000.0 * (hi - lo)


def _synth_one(bid: str) -> RawMarketingMetrics:
    """Generate deterministic plausible RawMarketingMetrics for one business."""
    mrr = _scale(bid, "mrr", lo=2_000, hi=40_000)
    arpu = _scale(bid, "arpu", lo=20, hi=400)
    avg_ltv_months = _scale(bid, "ltv", lo=12, hi=60)
    gross_margin = _scale(bid, "gm", lo=0.65, hi=0.92)
    total_spend = mrr * _scale(bid, "spend_pct", lo=0.05, hi=0.22)
    customers = max(1, int(_seed_int(bid, "customers") % 80))

    # Channel breakdown — pick 3-5 channels deterministically.
    channel_count = 3 + (_seed_int(bid, "ch_count") % 3)
    chosen = [_CHANNELS[(_seed_int(bid, f"ch{i}")) % len(_CHANNELS)]
              for i in range(channel_count)]
    # De-duplicate while preserving order
    seen: list[str] = []
    for c in chosen:
        if c not in seen:
            seen.append(c)
    chosen = seen

    # Distribute spend with one dominant channel
    weights = [_scale(bid, f"w_{c}", lo=0.05, hi=1.0) for c in chosen]
    # Inject dominance — first channel gets a multiplier
    weights[0] *= _scale(bid, "dom", lo=1.5, hi=4.0)
    wsum = sum(weights) or 1.0

    breakdown: list[ChannelSpend] = []
    for c, w in zip(chosen, weights):
        share = w / wsum
        breakdown.append(ChannelSpend(
            channel=c,
            spend_usd=round(total_spend * share, 2),
            customers_acquired=max(0, int(round(customers * share))),
        ))

    # Attribution decay: signal_count vs baseline_count
    baseline = len(chosen)
    signal_loss = int(_seed_int(bid, "attr_loss") % (baseline + 1))
    attr_signal = max(0, baseline - signal_loss)

    return RawMarketingMetrics(
        business_id=bid,
        mrr=round(mrr, 2),
        avg_ltv_months=round(avg_ltv_months, 2),
        total_marketing_spend_usd=round(total_spend, 2),
        total_customers_acquired=customers,
        arpu_monthly=round(arpu, 2),
        gross_margin=round(gross_margin, 4),
        channel_breakdown=breakdown,
        attr_signal_count=attr_signal,
        attr_baseline_count=baseline,
    )


def synthetic_marketing_provider() -> list[RawMarketingMetrics]:
    """Deterministic provider — one per business in projects.json."""
    out: list[RawMarketingMetrics] = []
    for bid in _load_business_ids():
        try:
            out.append(_synth_one(bid))
        except Exception as exc:  # noqa: BLE001
            log.warning("synthetic_marketing: skip %s (%s)", bid, exc)
    log.debug("synthetic_marketing: emitted %d metrics", len(out))
    return out


def synthetic_marketing_one(business_id: str) -> RawMarketingMetrics:
    """Public single-business entry-point for ad-platform per-business fallback."""
    return _synth_one(business_id)


__all__ = ["synthetic_marketing_provider", "synthetic_marketing_one"]
