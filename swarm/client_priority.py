"""swarm/client_priority.py — first-client elevation across senior bots.

A flat env-driven configuration that any senior bot consults to decide
whether a business_id deserves first-class treatment in the daily brief
and a tighter SLA.

Today the first-client is CCW (`ccw-crm`), live + paying SaaS subscriber
of the codebase Unite-Group built and ships. Every CS-tier1 ticket from
CCW is a top-of-page event; first-response SLA tightens from 60min → 15min.

The list is intentionally a comma-separated env so it can be flipped at
deploy time without code change. As more first-clients land, append.

Public API:
  is_first_client(business_id) -> bool
  list_first_clients() -> list[str]
  first_client_first_response_alert(business_id) -> int   # tighter SLA in min
  first_client_first_response_critical(business_id) -> int
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger("swarm.client_priority")

DEFAULT_FIRST_CLIENTS = "ccw-crm"

DEFAULT_TIGHT_ALERT_MIN = 15.0
DEFAULT_TIGHT_CRITICAL_MIN = 60.0


def list_first_clients() -> list[str]:
    """Read ``TAO_FIRST_CLIENTS`` (comma-separated business_ids).

    Defaults to ``ccw-crm`` so the system tracks CCW from cycle 1
    without any env config needed.
    """
    raw = os.environ.get("TAO_FIRST_CLIENTS", DEFAULT_FIRST_CLIENTS)
    return [s.strip() for s in raw.split(",") if s.strip()]


def is_first_client(business_id: str) -> bool:
    """True when the business should get top-of-brief + tightened SLA."""
    return business_id in list_first_clients()


def first_client_first_response_alert(business_id: str) -> float:
    """Tightened first-response warning threshold in minutes for first
    clients. Default 15min vs the 60min standard.
    """
    if not is_first_client(business_id):
        from .cs import ALERT_FIRST_RESPONSE_MINUTES
        return ALERT_FIRST_RESPONSE_MINUTES
    raw = os.environ.get("TAO_FIRST_CLIENT_RESPONSE_ALERT_MIN")
    try:
        return float(raw) if raw else DEFAULT_TIGHT_ALERT_MIN
    except ValueError:
        return DEFAULT_TIGHT_ALERT_MIN


def first_client_first_response_critical(business_id: str) -> float:
    """Tightened first-response critical threshold in minutes for first
    clients. Default 60min vs the 240min standard.
    """
    if not is_first_client(business_id):
        from .cs import CRITICAL_FIRST_RESPONSE_MINUTES
        return CRITICAL_FIRST_RESPONSE_MINUTES
    raw = os.environ.get("TAO_FIRST_CLIENT_RESPONSE_CRITICAL_MIN")
    try:
        return float(raw) if raw else DEFAULT_TIGHT_CRITICAL_MIN
    except ValueError:
        return DEFAULT_TIGHT_CRITICAL_MIN


__all__ = [
    "is_first_client", "list_first_clients",
    "first_client_first_response_alert",
    "first_client_first_response_critical",
    "DEFAULT_FIRST_CLIENTS",
    "DEFAULT_TIGHT_ALERT_MIN",
    "DEFAULT_TIGHT_CRITICAL_MIN",
]
