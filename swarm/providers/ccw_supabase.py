"""Aggregate-only Supabase adapter for CCW support health."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Callable

from ..ccw_support_contract import SupportSnapshot, SupportState

STATE_VIEW = "ccw_support_state"
AGGREGATE_COLUMNS = (
    "state", "reason_code", "latest_run_id", "heartbeat_at", "source_query_ok",
    "pending_count", "open_over_30m_count", "unresolved_escalation_count",
    "consumer_checkpoint_at",
)
FetchFn = Callable[[str, tuple[str, ...]], list[dict]]


def _timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("aggregate contract timestamp is invalid")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("aggregate contract timestamp lacks timezone")
    return parsed.astimezone(timezone.utc)


def _credentials() -> tuple[str, str]:
    url = (os.environ.get("SUPABASE_UNITE_GROUP_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_UNITE_GROUP_SERVICE_KEY") or ""
    if not url or not key:
        raise RuntimeError("CCW Supabase provider is not configured")
    return url, key


def _request(method: str, resource: str, *, query: dict | None = None,
             payload: dict | None = None) -> list[dict]:
    url, key = _credentials()
    endpoint = f"{url}/rest/v1/{resource}"
    if query:
        endpoint += "?" + urllib.parse.urlencode(query)
    bounded = {
        key: value.isoformat() if isinstance(value, datetime) else value
        for key, value in (payload or {}).items()
    }
    body = json.dumps(bounded).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(endpoint, data=body, method=method, headers={
        "apikey": key, "Authorization": f"Bearer {key}",
        "Content-Type": "application/json", "Prefer": "return=minimal",
    })
    with urllib.request.urlopen(request, timeout=8) as response:  # noqa: S310
        data = response.read(16_384)
    if not data:
        return []
    decoded = json.loads(data)
    if not isinstance(decoded, list):
        raise ValueError("aggregate contract response is not a list")
    return decoded


def _default_fetch(view: str, columns: tuple[str, ...]) -> list[dict]:
    return _request("GET", view, query={"select": ",".join(columns), "limit": "1"})


def fetch_ccw_state(fetch: FetchFn = _default_fetch) -> SupportSnapshot:
    rows = fetch(STATE_VIEW, AGGREGATE_COLUMNS)
    if len(rows) != 1 or set(rows[0]) != set(AGGREGATE_COLUMNS):
        raise ValueError("CCW aggregate contract is missing or malformed")
    row = rows[0]
    try:
        state = SupportState(row["state"])
        return SupportSnapshot(
            state=state, reason_code=str(row["reason_code"]),
            latest_run_id=row["latest_run_id"],
            heartbeat_at=_timestamp(row["heartbeat_at"]),
            source_query_ok=row["source_query_ok"],
            pending_count=int(row["pending_count"]),
            open_over_30m_count=int(row["open_over_30m_count"]),
            unresolved_escalation_count=int(row["unresolved_escalation_count"]),
            consumer_checkpoint_at=_timestamp(row["consumer_checkpoint_at"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("CCW aggregate contract contains invalid values") from exc


def ccw_supabase_provider() -> list[SupportSnapshot]:
    """Registry entry point; never substitutes synthetic CCW truth."""
    return [fetch_ccw_state()]


def record_consumer_checkpoint(payload: dict) -> None:
    allowed = {
        "consumer_id", "source_run_id", "checked_at", "completed_at", "outcome",
        "derived_state", "error_code",
    }
    if set(payload) != allowed:
        raise ValueError("consumer checkpoint violates bounded contract")
    _request("POST", "ccw_support_consumer_checkpoints", payload=payload)


def create_alert_intent(payload: dict) -> None:
    allowed = {"dedup_key", "state", "source_run_id", "opened_at", "last_seen_at", "status"}
    if set(payload) != allowed:
        raise ValueError("alert intent violates bounded contract")
    _request("POST", "ccw_support_alert_intents", payload=payload)
