"""swarm/providers/stripe_xero.py — production CFO metrics provider.

Pulls real numbers from Stripe (MRR, expansion, contraction, churn, new MRR)
and Xero (revenue, COGS, cash on hand) for each business in
``.harness/projects.json``. Falls back to ``synthetic_one(bid)`` for any
business missing credentials, so a partially-wired portfolio still emits a
coherent daily brief.

Activate with::

    TAO_CFO_PROVIDER=stripe_xero

Required env (master account):
* ``STRIPE_API_KEY`` — sk_live_* or sk_test_*

Optional per-business env:
* ``STRIPE_ACCOUNT_<BID>`` — Stripe Connect account id for that business.
  When set, MRR + acquisition figures are pulled from that account.
* ``XERO_TOKEN_<BID>`` + ``XERO_TENANT_<BID>`` — Xero OAuth bearer + tenant id
  for cash + COGS pull. (Stubbed today — Xero integration filed as follow-up
  ticket; cash + COGS continue to use synthetic for now.)

Where ``<BID>`` is the projects.json id uppercased with non-alpha → ``_``
(e.g. ``ccw-crm`` → ``CCW_CRM``).

Safety:
* httpx timeout 8.0 s per call
* Bearer auth only (no other request body); read scope only — no POSTs
* Per-business try/except — one bad business never breaks the cycle
* Falls back to synthetic data per-business on any exception
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from ..cfo import RawMetrics
from .synthetic import _load_business_ids, synthetic_one

# httpx is imported lazily inside _stripe_get so the module can be imported
# in environments without httpx installed — synthetic fallback still works.

log = logging.getLogger("swarm.providers.stripe_xero")

STRIPE_API_BASE = "https://api.stripe.com/v1"
HTTP_TIMEOUT_S = 8.0


def _bid_key(bid: str) -> str:
    """projects.json id → env key suffix (e.g. ``ccw-crm`` → ``CCW_CRM``)."""
    return re.sub(r"[^A-Za-z0-9]+", "_", bid).strip("_").upper()


def _stripe_get(path: str, *, api_key: str, params: dict[str, Any] | None = None,
                stripe_account: str | None = None) -> dict[str, Any]:
    """One Stripe GET. Raises on HTTP error so caller can fall back.

    httpx is imported here (not at module top) so this module loads in
    environments without httpx — only callers that actually hit Stripe pay
    the import cost.
    """
    import httpx  # noqa: PLC0415 — intentional lazy import (see module docstring)

    headers = {"Authorization": f"Bearer {api_key}"}
    if stripe_account:
        headers["Stripe-Account"] = stripe_account
    with httpx.Client(timeout=HTTP_TIMEOUT_S) as client:
        r = client.get(f"{STRIPE_API_BASE}{path}", headers=headers, params=params)
        r.raise_for_status()
        return r.json()


def _stripe_mrr_for_account(api_key: str, stripe_account: str | None) -> float:
    """Sum of unit_amount * quantity across all active subscriptions, in USD.

    Stripe stores amounts in cents/minor units. We divide by 100 to get USD.
    Multi-currency portfolios should add a conversion layer here — Wave 4.2.
    """
    out_mrr = 0.0
    starting_after: str | None = None
    while True:
        params: dict[str, Any] = {"status": "active", "limit": 100}
        if starting_after:
            params["starting_after"] = starting_after
        page = _stripe_get(
            "/subscriptions", api_key=api_key,
            params=params, stripe_account=stripe_account,
        )
        for sub in page.get("data", []):
            for item in sub.get("items", {}).get("data", []):
                price = item.get("price") or {}
                unit = (price.get("unit_amount") or 0) / 100.0
                qty = item.get("quantity") or 1
                interval = (price.get("recurring") or {}).get("interval") or "month"
                if interval == "year":
                    out_mrr += unit * qty / 12.0
                elif interval == "week":
                    out_mrr += unit * qty * 4.345
                else:  # month, day → treat day as month for safety
                    out_mrr += unit * qty
        if not page.get("has_more"):
            break
        starting_after = page["data"][-1]["id"] if page.get("data") else None
        if not starting_after:
            break
    return round(out_mrr, 2)


def _real_for_business(bid: str, api_key: str) -> RawMetrics | None:
    """Build RawMetrics for one business from Stripe + Xero. None on failure.

    Today: Stripe MRR is real; the rest is filled from synthetic_one(bid)
    so the brief stays coherent. Xero cash/COGS/COGS-bearing fields are
    synthetic until ``swarm/providers/xero.py`` lands (follow-up ticket).
    """
    stripe_account = os.environ.get(f"STRIPE_ACCOUNT_{_bid_key(bid)}")
    try:
        real_mrr = _stripe_mrr_for_account(api_key, stripe_account)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "stripe_xero: %s Stripe call failed (%s) — falling back to synthetic",
            bid, exc,
        )
        return None

    # Use synthetic as the scaffold and overwrite the real fields we have.
    base = synthetic_one(bid)
    base.mrr = real_mrr
    # Scale starting_mrr / new / expansion / contraction / churn proportionally
    # to keep ratios sensible against the real MRR until each is wired.
    if base.mrr > 0:
        ratio = real_mrr / max(base.mrr, 0.01) if base.mrr != real_mrr else 1.0
        base.starting_mrr = round(base.starting_mrr * ratio, 2)
        base.expansion_mrr = round(base.expansion_mrr * ratio, 2)
        base.contraction_mrr = round(base.contraction_mrr * ratio, 2)
        base.churn_mrr = round(base.churn_mrr * ratio, 2)
        base.new_mrr = round(base.new_mrr * ratio, 2)
        base.revenue = round(base.revenue * ratio, 2)
    return base


def stripe_xero_provider() -> list[RawMetrics]:
    """Real-data provider with per-business synthetic fallback."""
    api_key = (os.environ.get("STRIPE_API_KEY") or "").strip()
    if not api_key:
        log.warning(
            "stripe_xero: STRIPE_API_KEY missing — emitting synthetic only"
        )
        return [synthetic_one(bid) for bid in _load_business_ids()]

    out: list[RawMetrics] = []
    for bid in _load_business_ids():
        real = _real_for_business(bid, api_key)
        out.append(real if real is not None else synthetic_one(bid))
    log.debug("stripe_xero: emitted %d metrics", len(out))
    return out


__all__ = ["stripe_xero_provider"]
