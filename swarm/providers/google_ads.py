"""swarm/providers/google_ads.py — real ad-platform CMO provider.

Pulls real spend per channel from Google Ads for each business in
``.harness/projects.json``. Other channels (LinkedIn, Meta, etc.) are
follow-up tickets — for now this connector handles Google Ads and falls
back to synthetic for everything else in the channel mix.

Activate with::

    TAO_CMO_PROVIDER=google_ads

Required env (master account):
* ``GOOGLE_ADS_DEVELOPER_TOKEN``
* ``GOOGLE_ADS_OAUTH_TOKEN`` — current OAuth bearer (refresh sidecar
  required for production)
* ``GOOGLE_ADS_LOGIN_CUSTOMER_ID`` — manager account ID (no dashes)

Optional per-business env:
* ``GOOGLE_ADS_CUSTOMER_<BID>`` — child customer ID for that business

Where ``<BID>`` is the projects.json id uppercased with non-alpha → ``_``
(e.g. ``ccw-crm`` → ``CCW_CRM``).

Safety:
* httpx timeout 8.0 s per call
* Read scope only — `googleAds:searchStream` is a read query
* Per-business try/except — one bad business never breaks the cycle
* Falls back to synthetic_marketing_one(bid) on any failure
* httpx imported lazily — synthetic-only environments still load module
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from ..cmo import ChannelSpend, RawMarketingMetrics
from .synthetic import _load_business_ids
from .synthetic_marketing import synthetic_marketing_one

log = logging.getLogger("swarm.providers.google_ads")

GOOGLE_ADS_API_BASE = "https://googleads.googleapis.com/v17"
HTTP_TIMEOUT_S = 8.0

# GAQL: spend in micros + customer count (last 7 days, by network)
# Returns one row per ad_group_ad_network_type — we aggregate to "google-ads"
# as a single channel. Granular per-network breakdown is a follow-up.
_GAQL_LAST_7_DAYS_SPEND = (
    "SELECT metrics.cost_micros, metrics.conversions "
    "FROM customer "
    "WHERE segments.date DURING LAST_7_DAYS"
)


def _bid_key(bid: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", bid).strip("_").upper()


def _ads_post(path: str, *, oauth_token: str, developer_token: str,
               login_customer_id: str | None, body: dict[str, Any]
               ) -> dict[str, Any]:
    """One Google Ads searchStream POST. Raises on HTTP error so caller falls back.

    httpx imported here so this module loads in environments without httpx.
    """
    import httpx  # noqa: PLC0415

    headers = {
        "Authorization": f"Bearer {oauth_token}",
        "developer-token": developer_token,
        "Content-Type": "application/json",
    }
    if login_customer_id:
        headers["login-customer-id"] = login_customer_id

    with httpx.Client(timeout=HTTP_TIMEOUT_S) as client:
        r = client.post(f"{GOOGLE_ADS_API_BASE}{path}",
                        headers=headers, json=body)
        r.raise_for_status()
        return r.json()


def _query_customer_spend(*, customer_id: str, oauth_token: str,
                            developer_token: str,
                            login_customer_id: str | None
                            ) -> tuple[float, int] | None:
    """Sum cost_micros + conversions for one customer over LAST_7_DAYS.

    Returns (spend_usd, conversions) or None on error. Cost is reported
    in micros (1e6 = 1 unit of account currency). Treats account currency
    as USD — multi-currency consolidation is a follow-up.
    """
    path = f"/customers/{customer_id}/googleAds:searchStream"
    body = {"query": _GAQL_LAST_7_DAYS_SPEND}
    try:
        result = _ads_post(
            path,
            oauth_token=oauth_token,
            developer_token=developer_token,
            login_customer_id=login_customer_id,
            body=body,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("google_ads: customer %s query failed (%s)",
                    customer_id, exc)
        return None

    # searchStream returns a list of response chunks, each with `results`.
    total_micros = 0
    total_conversions = 0.0
    if not isinstance(result, list):
        result = [result]
    for chunk in result:
        for row in chunk.get("results", []) or []:
            metrics = row.get("metrics") or {}
            try:
                total_micros += int(metrics.get("costMicros") or 0)
            except (TypeError, ValueError):
                continue
            try:
                total_conversions += float(metrics.get("conversions") or 0)
            except (TypeError, ValueError):
                continue
    spend_usd = total_micros / 1_000_000.0
    return round(spend_usd, 2), int(round(total_conversions))


def _real_for_business(bid: str, *, oauth_token: str,
                         developer_token: str,
                         login_customer_id: str | None
                         ) -> RawMarketingMetrics | None:
    """Build RawMarketingMetrics for one business from Google Ads.

    Today: Google Ads spend on the "google-ads" channel slot is real;
    other channels (linkedin, meta, seo, referral, youtube) are filled
    from synthetic_marketing_one(bid) so the brief stays coherent. Each
    additional channel is a follow-up ticket.
    """
    customer_id = (
        os.environ.get(f"GOOGLE_ADS_CUSTOMER_{_bid_key(bid)}") or ""
    ).strip()
    if not customer_id:
        log.debug("google_ads: %s no GOOGLE_ADS_CUSTOMER_<BID> — using synthetic",
                  bid)
        return None

    out = _query_customer_spend(
        customer_id=customer_id,
        oauth_token=oauth_token,
        developer_token=developer_token,
        login_customer_id=login_customer_id,
    )
    if out is None:
        return None
    real_spend, real_conversions = out

    # Use synthetic as the scaffold and overwrite the google-ads channel row.
    base = synthetic_marketing_one(bid)

    new_breakdown: list[ChannelSpend] = []
    found_google = False
    for ch in base.channel_breakdown:
        if ch.channel == "google-ads":
            new_breakdown.append(ChannelSpend(
                channel="google-ads",
                spend_usd=real_spend,
                customers_acquired=real_conversions,
            ))
            found_google = True
        else:
            new_breakdown.append(ch)
    if not found_google:
        # Synthetic mix didn't include google-ads — append it so real spend
        # at least surfaces in the brief.
        new_breakdown.append(ChannelSpend(
            channel="google-ads",
            spend_usd=real_spend,
            customers_acquired=real_conversions,
        ))
    base.channel_breakdown = new_breakdown

    # Recompute totals — keep synthetic for non-google channels, only the
    # google-ads slice is real today.
    base.total_marketing_spend_usd = round(
        sum(c.spend_usd for c in new_breakdown), 2,
    )
    base.total_customers_acquired = sum(
        c.customers_acquired for c in new_breakdown
    )
    return base


def google_ads_provider() -> list[RawMarketingMetrics]:
    """Real-data provider with per-business synthetic fallback."""
    oauth_token = (os.environ.get("GOOGLE_ADS_OAUTH_TOKEN") or "").strip()
    developer_token = (
        os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN") or ""
    ).strip()
    login_customer_id = (
        os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID") or ""
    ).strip() or None

    if not oauth_token or not developer_token:
        log.warning(
            "google_ads: missing OAUTH or DEVELOPER token — emitting "
            "synthetic only"
        )
        return [synthetic_marketing_one(b) for b in _load_business_ids()]

    out: list[RawMarketingMetrics] = []
    for bid in _load_business_ids():
        real = _real_for_business(
            bid,
            oauth_token=oauth_token,
            developer_token=developer_token,
            login_customer_id=login_customer_id,
        )
        out.append(real if real is not None else synthetic_marketing_one(bid))
    log.debug("google_ads: emitted %d metrics", len(out))
    return out


__all__ = ["google_ads_provider"]
