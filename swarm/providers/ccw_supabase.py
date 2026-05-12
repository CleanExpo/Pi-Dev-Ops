"""swarm/providers/ccw_supabase.py — Wave 5.2 CCW-specific CS data path.

Reads ``ccw_support_tickets`` from the Unite-Group Supabase and produces a
``RawCsMetrics`` row with ``business_id='ccw'``. NPS / FCR / GRR fields are
left at zero (we do not yet survey CCW); the meaningful signal is
``avg_first_response_minutes`` and ``open_enterprise_churn_threats`` (via
``state='escalated'`` count).

The CS bot wrapper composes this row alongside whatever the configured
upstream provider returns, so the rest of the portfolio still ships
synthetic / zendesk metrics.

Env contract:
* SUPABASE_UNITE_GROUP_URL
* SUPABASE_UNITE_GROUP_SERVICE_KEY

Both are read at call time. Returns ``None`` (caller suppresses the CCW row)
if either env var is missing or the HTTP call fails — degrades silently
because the upstream synthetic provider already emits a ccw row.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from ..cs import RawCsMetrics

log = logging.getLogger("swarm.providers.ccw_supabase")

DEFAULT_WINDOW_HOURS = 24


def _supabase_get(path: str) -> list[dict] | None:
    url_base = os.environ.get("SUPABASE_UNITE_GROUP_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_UNITE_GROUP_SERVICE_KEY", "")
    if not url_base or not key:
        return None
    url = f"{url_base}{path}"
    req = urllib.request.Request(
        url, method="GET",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8") or "[]")
            if isinstance(data, list):
                return data
            return None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            json.JSONDecodeError) as exc:
        log.debug("ccw_supabase: GET %s failed: %s", path, exc)
        return None


def ccw_supabase_metrics(*, window_hours: int | None = None
                         ) -> RawCsMetrics | None:
    """Compute a RawCsMetrics row for CCW from ccw_support_tickets.

    Window: last ``window_hours`` (default 24). Counts received in window;
    avg first-response minutes computed over tickets where
    ``first_response_at`` is set.
    """
    if window_hours is None:
        try:
            window_hours = int(os.environ.get(
                "CCW_TICKETS_WINDOW_HOURS",
                str(DEFAULT_WINDOW_HOURS)))
        except ValueError:
            window_hours = DEFAULT_WINDOW_HOURS

    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    rows = _supabase_get(
        "/rest/v1/ccw_support_tickets"
        f"?received_at=gte.{cutoff_iso}"
        "&select=id,state,received_at,first_response_at"
    )
    if rows is None:
        return None

    open_count = 0
    escalated_count = 0
    response_minutes: list[float] = []
    oldest_open_age_min = 0.0
    now = datetime.now(timezone.utc)

    for r in rows:
        state = r.get("state") or "open"
        rec = r.get("received_at")
        frt = r.get("first_response_at")
        try:
            rec_dt = (datetime.fromisoformat(rec.replace("Z", "+00:00"))
                      if rec else None)
        except (AttributeError, ValueError):
            rec_dt = None

        if state == "open":
            open_count += 1
            if rec_dt is not None:
                age_min = (now - rec_dt).total_seconds() / 60.0
                if age_min > oldest_open_age_min:
                    oldest_open_age_min = age_min
        if state == "escalated":
            escalated_count += 1

        if frt and rec_dt is not None:
            try:
                frt_dt = datetime.fromisoformat(
                    frt.replace("Z", "+00:00"))
                response_minutes.append(
                    max(0.0, (frt_dt - rec_dt).total_seconds() / 60.0))
            except ValueError:
                pass

    avg_response_min = (sum(response_minutes) / len(response_minutes)
                         if response_minutes else 0.0)
    # When nothing is open and no responses yet, surface the oldest-open age
    # as the SLA signal so the dashboard isn't blind on a quiet day.
    surface_response = avg_response_min if response_minutes \
        else oldest_open_age_min

    return RawCsMetrics(
        business_id="ccw",
        nps_promoters=0,
        nps_passives=0,
        nps_detractors=0,
        tickets_total=len(rows),
        tickets_resolved_first_contact=sum(
            1 for r in rows if r.get("state") in ("resolved", "closed")),
        customers_at_period_start=1,   # 1 active CCW account
        customers_lost_in_period=0,
        avg_first_response_minutes=round(surface_response, 1),
        open_enterprise_churn_threats=escalated_count,
    )


__all__ = ["ccw_supabase_metrics"]
