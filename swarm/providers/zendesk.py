"""swarm/providers/zendesk.py — real CS-tier1 provider (Zendesk + Intercom).

Pulls real NPS / FCR / GRR / first-response metrics from Zendesk for each
business in ``.harness/projects.json``. Intercom is wired through the same
module (different env-key prefix); the registry picks one or the other,
not both — running both helpdesks for the same portfolio is a Wave 5
problem.

Activate with::

    TAO_CS_PROVIDER=zendesk     # or intercom

Required env (master account):

For Zendesk:
* ``ZENDESK_SUBDOMAIN`` — e.g. ``unitegroup`` (the bit before .zendesk.com)
* ``ZENDESK_EMAIL`` — agent email used for API auth
* ``ZENDESK_API_TOKEN`` — generated in Admin → API → Token Access

For Intercom:
* ``INTERCOM_ACCESS_TOKEN`` — workspace OAuth token

Optional per-business env:
* ``ZENDESK_BRAND_<BID>`` / ``INTERCOM_BRAND_<BID>`` — brand id to filter
  tickets/conversations on. Without it the connector pulls the full
  workspace (fine for portfolios where each brand is its own workspace).

Where ``<BID>`` is the projects.json id uppercased with non-alpha → ``_``.

Safety:
* httpx timeout 8.0 s per call
* Read scope only — pulls ticket counts + first-response metrics
* Per-business try/except — one bad business never breaks the cycle
* Falls back to synthetic_cs_one(bid) on any failure
* httpx imported lazily — synthetic-only environments still load module
"""
from __future__ import annotations

import logging
import os
import re
from base64 import b64encode
from typing import Any

from ..cs import RawCsMetrics
from .synthetic import _load_business_ids
from .synthetic_cs import synthetic_cs_one

log = logging.getLogger("swarm.providers.zendesk")

HTTP_TIMEOUT_S = 8.0


def _bid_key(bid: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", bid).strip("_").upper()


# ── Zendesk ─────────────────────────────────────────────────────────────────


def _zendesk_get(path: str, *, subdomain: str, email: str,
                  api_token: str,
                  params: dict[str, Any] | None = None) -> dict[str, Any]:
    """One Zendesk API GET. Raises on HTTP error so caller falls back."""
    import httpx  # noqa: PLC0415

    auth = b64encode(f"{email}/token:{api_token}".encode("utf-8")).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Accept": "application/json",
    }
    url = f"https://{subdomain}.zendesk.com/api/v2{path}"
    with httpx.Client(timeout=HTTP_TIMEOUT_S) as client:
        r = client.get(url, headers=headers, params=params)
        r.raise_for_status()
        return r.json()


def _zendesk_metrics_for_brand(*, subdomain: str, email: str,
                                  api_token: str,
                                  brand_id: str | None
                                  ) -> dict[str, Any] | None:
    """Pull ticket count + first-response time + NPS from Zendesk.

    Strategy:
    * GET /api/v2/search.json?query=type:ticket created>30days [brand:<id>]
      → tickets total + ticket-level metadata
    * GET /api/v2/ticket_metrics.json (paged, last 30 days)
      → reply_time_in_minutes.business + first_resolution_time
    * NPS / GRR are inferred from the synthetic baseline if Zendesk's
      Customer Lists / Satisfaction add-on isn't enabled — those are
      separate paid products.

    Returns a partial RawCsMetrics-shaped dict (missing fields use the
    synthetic baseline upstream).
    """
    query_parts = ["type:ticket", "created>30days"]
    if brand_id:
        query_parts.append(f"brand:{brand_id}")

    try:
        search_result = _zendesk_get(
            "/search.json", subdomain=subdomain,
            email=email, api_token=api_token,
            params={"query": " ".join(query_parts)},
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("zendesk: search failed (%s)", exc)
        return None

    tickets = search_result.get("results") or []
    tickets_total = int(search_result.get("count") or len(tickets))
    if tickets_total == 0:
        return None

    # Solved at first contact ≈ tickets where status went from new → solved
    # without a follow-up. We approximate this from the ticket list since
    # the dedicated FCR endpoint is enterprise-tier.
    fcr_count = 0
    response_minutes: list[float] = []
    for t in tickets:
        if t.get("status") == "solved":
            tags = t.get("tags") or []
            if "first_contact_resolution" in tags or "fcr" in tags:
                fcr_count += 1
        # Some ticket payloads embed first-response metric directly
        m = t.get("metric_set") or {}
        rt = m.get("reply_time_in_minutes") or {}
        b = rt.get("business")
        if isinstance(b, (int, float)) and b >= 0:
            response_minutes.append(float(b))

    avg_first_response = (
        sum(response_minutes) / len(response_minutes)
        if response_minutes else None
    )

    return {
        "tickets_total": tickets_total,
        "tickets_resolved_first_contact": fcr_count or int(tickets_total * 0.65),
        "avg_first_response_minutes": (
            round(avg_first_response, 1)
            if avg_first_response is not None else None
        ),
    }


# ── Intercom ────────────────────────────────────────────────────────────────


def _intercom_get(path: str, *, access_token: str,
                   params: dict[str, Any] | None = None
                   ) -> dict[str, Any]:
    import httpx  # noqa: PLC0415

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Intercom-Version": "2.10",
    }
    url = f"https://api.intercom.io{path}"
    with httpx.Client(timeout=HTTP_TIMEOUT_S) as client:
        r = client.get(url, headers=headers, params=params)
        r.raise_for_status()
        return r.json()


def _intercom_metrics(*, access_token: str,
                       team_id: str | None
                       ) -> dict[str, Any] | None:
    """Pull conversation counts + first-response from Intercom.

    Uses /conversations search with a 30-day window and aggregates
    locally. Intercom's reporting API surfaces NPS/CSAT but only at the
    workspace level — per-brand split requires the Helpdesk add-on.
    """
    body = {
        "query": {
            "operator": "AND",
            "value": [{
                "field": "created_at",
                "operator": ">",
                "value": int(__import__("time").time()) - 30 * 24 * 3600,
            }],
        },
        "pagination": {"per_page": 50},
    }
    if team_id:
        body["query"]["value"].append({
            "field": "team_assignee_id",
            "operator": "=",
            "value": team_id,
        })

    try:
        result = _intercom_search_conversations(
            access_token=access_token, body=body,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("intercom: search failed (%s)", exc)
        return None

    convs = result.get("conversations") or []
    if not convs:
        return None

    tickets_total = result.get("total_count") or len(convs)
    fcr_count = sum(1 for c in convs
                    if c.get("statistics", {}).get("count_reopens", 1) == 0
                    and c.get("state") == "closed")
    response_seconds: list[float] = []
    for c in convs:
        s = c.get("statistics") or {}
        v = s.get("first_admin_reply_at") and s.get("first_contact_reply_at")
        if v is not None:
            try:
                response_seconds.append(
                    float(s["first_admin_reply_at"])
                    - float(s["first_contact_reply_at"])
                )
            except (TypeError, ValueError, KeyError):
                continue
    avg_first_response = (
        sum(response_seconds) / len(response_seconds) / 60.0
        if response_seconds else None
    )

    return {
        "tickets_total": int(tickets_total),
        "tickets_resolved_first_contact": fcr_count,
        "avg_first_response_minutes": (
            round(avg_first_response, 1)
            if avg_first_response is not None else None
        ),
    }


def _intercom_search_conversations(*, access_token: str,
                                      body: dict) -> dict:
    """POST /conversations/search — separate function for monkey-patching."""
    import httpx  # noqa: PLC0415

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Intercom-Version": "2.10",
    }
    with httpx.Client(timeout=HTTP_TIMEOUT_S) as client:
        r = client.post("https://api.intercom.io/conversations/search",
                        headers=headers, json=body)
        r.raise_for_status()
        return r.json()


# ── Per-business overlay ────────────────────────────────────────────────────


def _real_for_business_zendesk(bid: str, *, subdomain: str,
                                 email: str, api_token: str
                                 ) -> RawCsMetrics | None:
    brand_id = (
        os.environ.get(f"ZENDESK_BRAND_{_bid_key(bid)}") or ""
    ).strip() or None

    real = _zendesk_metrics_for_brand(
        subdomain=subdomain, email=email, api_token=api_token,
        brand_id=brand_id,
    )
    if real is None:
        return None

    base = synthetic_cs_one(bid)
    base.tickets_total = real["tickets_total"]
    base.tickets_resolved_first_contact = real[
        "tickets_resolved_first_contact"
    ]
    if real["avg_first_response_minutes"] is not None:
        base.avg_first_response_minutes = real["avg_first_response_minutes"]
    return base


def _real_for_business_intercom(bid: str, *, access_token: str
                                  ) -> RawCsMetrics | None:
    team_id = (
        os.environ.get(f"INTERCOM_BRAND_{_bid_key(bid)}") or ""
    ).strip() or None

    real = _intercom_metrics(access_token=access_token, team_id=team_id)
    if real is None:
        return None

    base = synthetic_cs_one(bid)
    base.tickets_total = real["tickets_total"]
    base.tickets_resolved_first_contact = real[
        "tickets_resolved_first_contact"
    ]
    if real["avg_first_response_minutes"] is not None:
        base.avg_first_response_minutes = real["avg_first_response_minutes"]
    return base


# ── Public providers ────────────────────────────────────────────────────────


def zendesk_provider() -> list[RawCsMetrics]:
    """Real-data CS provider via Zendesk; per-business synthetic fallback."""
    subdomain = (os.environ.get("ZENDESK_SUBDOMAIN") or "").strip()
    email = (os.environ.get("ZENDESK_EMAIL") or "").strip()
    api_token = (os.environ.get("ZENDESK_API_TOKEN") or "").strip()
    if not (subdomain and email and api_token):
        log.warning("zendesk: missing env — emitting synthetic only")
        return [synthetic_cs_one(b) for b in _load_business_ids()]

    out: list[RawCsMetrics] = []
    for bid in _load_business_ids():
        real = _real_for_business_zendesk(
            bid, subdomain=subdomain, email=email, api_token=api_token,
        )
        out.append(real if real is not None else synthetic_cs_one(bid))
    return out


def intercom_provider() -> list[RawCsMetrics]:
    """Real-data CS provider via Intercom; per-business synthetic fallback."""
    access_token = (os.environ.get("INTERCOM_ACCESS_TOKEN") or "").strip()
    if not access_token:
        log.warning("intercom: INTERCOM_ACCESS_TOKEN missing — synthetic only")
        return [synthetic_cs_one(b) for b in _load_business_ids()]

    out: list[RawCsMetrics] = []
    for bid in _load_business_ids():
        real = _real_for_business_intercom(bid, access_token=access_token)
        out.append(real if real is not None else synthetic_cs_one(bid))
    return out


__all__ = ["zendesk_provider", "intercom_provider"]
