"""Aggregate-only Supabase adapter for CCW support health."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Callable

from ..ccw_support_contract import (
    CHECKPOINT_ERROR_CODES,
    REQUIRED_CONSUMERS,
    TENANT_ID,
    ConsumerCheckpoint,
    SupportSnapshot,
    SupportState,
    validate_state_reason,
    validate_tenant_id,
)

STATE_VIEW = "ccw_support_state"
AGGREGATE_COLUMNS = (
    "state",
    "reason_code",
    "latest_run_id",
    "heartbeat_at",
    "source_query_ok",
    "pending_count",
    "open_over_30m_count",
    "unresolved_escalation_count",
    "consumer_checkpoint_at",
)
FetchFn = Callable[[str, tuple[str, ...]], list[dict]]
CheckpointFetchFn = Callable[[str, tuple[str, ...]], list[dict]]
CHECKPOINT_COLUMNS = (
    "tenant_id",
    "consumer_id",
    "source_run_id",
    "checked_at",
    "completed_at",
    "outcome",
    "derived_state",
    "error_code",
)


def _timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("aggregate contract timestamp is invalid")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("aggregate contract timestamp lacks timezone")
    return parsed.astimezone(timezone.utc)


def _payload_timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field} timestamp is invalid")
    return value


def _credentials() -> tuple[str, str]:
    url = (os.environ.get("SUPABASE_UNITE_GROUP_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_UNITE_GROUP_SERVICE_KEY") or ""
    if not url or not key:
        raise RuntimeError("CCW Supabase provider is not configured")
    return url, key


def _request(
    method: str,
    resource: str,
    *,
    query: dict | None = None,
    payload: dict | None = None,
    prefer: str = "return=minimal",
) -> list[dict]:
    url, key = _credentials()
    endpoint = f"{url}/rest/v1/{resource}"
    if query:
        endpoint += "?" + urllib.parse.urlencode(query)
    bounded = {
        key: value.isoformat() if isinstance(value, datetime) else value
        for key, value in (payload or {}).items()
    }
    body = json.dumps(bounded).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        endpoint,
        data=body,
        method=method,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": prefer,
        },
    )
    with urllib.request.urlopen(request, timeout=8) as response:  # noqa: S310
        data = response.read(16_384)
    if not data:
        return []
    decoded = json.loads(data)
    if not isinstance(decoded, list):
        raise ValueError("aggregate contract response is not a list")
    return decoded


def _default_fetch(view: str, columns: tuple[str, ...]) -> list[dict]:
    return _request(
        "GET",
        view,
        query={
            "select": ",".join(columns),
            "tenant_id": f"eq.{TENANT_ID}",
            "limit": "2",
        },
    )


def _nonnegative_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("aggregate counter is invalid")
    return value


def fetch_ccw_state(fetch: FetchFn = _default_fetch) -> SupportSnapshot:
    rows = fetch(STATE_VIEW, AGGREGATE_COLUMNS)
    if len(rows) != 1 or set(rows[0]) != set(AGGREGATE_COLUMNS):
        raise ValueError("CCW aggregate contract is missing or malformed")
    row = rows[0]
    try:
        state = SupportState(row["state"])
        reason_code = validate_state_reason(state, row["reason_code"])
        query_ok = row["source_query_ok"]
        if not isinstance(reason_code, str) or not reason_code:
            raise ValueError("aggregate reason is invalid")
        if query_ok is not None and not isinstance(query_ok, bool):
            raise ValueError("aggregate query health is invalid")
        return SupportSnapshot(
            state=state,
            reason_code=reason_code,
            latest_run_id=row["latest_run_id"],
            heartbeat_at=_timestamp(row["heartbeat_at"]),
            source_query_ok=query_ok,
            pending_count=_nonnegative_int(row["pending_count"]),
            open_over_30m_count=_nonnegative_int(row["open_over_30m_count"]),
            unresolved_escalation_count=_nonnegative_int(
                row["unresolved_escalation_count"]
            ),
            consumer_checkpoint_at=_timestamp(row["consumer_checkpoint_at"]),
            tenant_id=TENANT_ID,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("CCW aggregate contract contains invalid values") from exc


def ccw_supabase_provider() -> list[SupportSnapshot]:
    """Registry entry point; never substitutes synthetic CCW truth."""
    return [fetch_ccw_state()]


def _default_checkpoint_fetch(
    source_run_id: str, columns: tuple[str, ...]
) -> list[dict]:
    return _request(
        "GET",
        "ccw_support_consumer_checkpoints",
        query={
            "select": ",".join(columns),
            "tenant_id": f"eq.{TENANT_ID}",
            "source_run_id": f"eq.{source_run_id}",
            "order": "consumer_id.asc",
            "limit": "4",
        },
    )


def load_consumer_checkpoints(
    source_run_id: str,
    *,
    tenant_id: str = TENANT_ID,
    fetch: CheckpointFetchFn = _default_checkpoint_fetch,
) -> tuple[ConsumerCheckpoint, ...]:
    """Load one run's bounded consumer evidence in deterministic order."""
    validate_tenant_id(tenant_id)
    if not isinstance(source_run_id, str) or not source_run_id:
        raise ValueError("checkpoint source run is invalid")
    rows = fetch(source_run_id, CHECKPOINT_COLUMNS)
    if not isinstance(rows, list) or len(rows) > len(REQUIRED_CONSUMERS):
        raise ValueError("checkpoint response is invalid")
    parsed: dict[str, ConsumerCheckpoint] = {}
    try:
        for row in rows:
            if not isinstance(row, dict) or set(row) != set(CHECKPOINT_COLUMNS):
                raise ValueError("checkpoint row fields are invalid")
            consumer_id = row["consumer_id"]
            if consumer_id not in REQUIRED_CONSUMERS or consumer_id in parsed:
                raise ValueError("checkpoint consumer is invalid or duplicated")
            if row["tenant_id"] != TENANT_ID or row["source_run_id"] != source_run_id:
                raise ValueError("checkpoint source run mismatch")
            if row["outcome"] not in {"success", "error"}:
                raise ValueError("checkpoint outcome is invalid")
            if row["derived_state"] not in {state.value for state in SupportState}:
                raise ValueError("checkpoint derived state is invalid")
            error_code = row["error_code"]
            if error_code is not None and error_code not in CHECKPOINT_ERROR_CODES:
                raise ValueError("checkpoint error code is invalid")
            if (row["outcome"] == "success") != (error_code is None):
                raise ValueError("checkpoint outcome/error pairing is invalid")
            checked_at = _timestamp(row["checked_at"])
            completed_at = _timestamp(row["completed_at"])
            if checked_at is None or completed_at is None or completed_at < checked_at:
                raise ValueError("checkpoint chronology is invalid")
            parsed[consumer_id] = ConsumerCheckpoint(
                consumer_id=consumer_id,
                source_run_id=source_run_id,
                checked_at=checked_at,
                completed_at=completed_at,
                outcome=row["outcome"],
                error_code=error_code,
                tenant_id=TENANT_ID,
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("checkpoint contract contains invalid values") from exc
    return tuple(parsed[name] for name in REQUIRED_CONSUMERS if name in parsed)


def record_consumer_checkpoint(payload: dict) -> None:
    allowed = {
        "tenant_id",
        "consumer_id",
        "source_run_id",
        "checked_at",
        "completed_at",
        "outcome",
        "derived_state",
        "error_code",
    }
    if set(payload) != allowed:
        raise ValueError("consumer checkpoint violates bounded contract")
    source_run_id = payload.get("source_run_id")
    consumer_id = payload.get("consumer_id")
    validate_tenant_id(payload.get("tenant_id"))
    if not isinstance(source_run_id, str) or not source_run_id:
        raise ValueError("consumer checkpoint source run is invalid")
    if consumer_id not in REQUIRED_CONSUMERS:
        raise ValueError("consumer checkpoint id is invalid")
    checked_at = _payload_timestamp(payload.get("checked_at"), "checkpoint checked_at")
    completed_at = _payload_timestamp(
        payload.get("completed_at"), "checkpoint completed_at"
    )
    if completed_at < checked_at:
        raise ValueError("consumer checkpoint chronology is invalid")
    outcome = payload.get("outcome")
    error_code = payload.get("error_code")
    if outcome not in {"success", "error"}:
        raise ValueError("consumer checkpoint outcome is invalid")
    if error_code is not None and error_code not in CHECKPOINT_ERROR_CODES:
        raise ValueError("consumer checkpoint error code is invalid")
    if (outcome == "success") != (error_code is None):
        raise ValueError("consumer checkpoint outcome/error pairing is invalid")
    try:
        SupportState(payload.get("derived_state"))
    except (TypeError, ValueError) as exc:
        raise ValueError("consumer checkpoint state is invalid") from exc
    _request(
        "POST",
        "ccw_support_consumer_checkpoints",
        query={"on_conflict": "tenant_id,source_run_id,consumer_id"},
        payload=payload,
        prefer="resolution=ignore-duplicates,return=minimal",
    )


def record_alert_intent_checkpoint(
    payload: dict,
    *,
    write_checkpoint: Callable[[dict], None] = record_consumer_checkpoint,
) -> None:
    if payload.get("consumer_id") != "alert_intent":
        raise ValueError("alert_intent checkpoint writer received another consumer")
    write_checkpoint(payload)


def create_alert_intent(payload: dict) -> None:
    allowed = {
        "tenant_id",
        "dedup_key",
        "state",
        "source_run_id",
        "opened_at",
        "last_seen_at",
        "status",
    }
    if set(payload) != allowed:
        raise ValueError("alert intent violates bounded contract")
    validate_tenant_id(payload.get("tenant_id"))
    dedup_key = payload.get("dedup_key")
    if (
        not isinstance(dedup_key, str)
        or len(dedup_key) != 64
        or any(char not in "0123456789abcdef" for char in dedup_key)
    ):
        raise ValueError("alert intent dedup key is invalid")
    source_run_id = payload.get("source_run_id")
    if not isinstance(source_run_id, str) or not source_run_id:
        raise ValueError("alert intent source run is invalid")
    try:
        SupportState(payload.get("state"))
    except (TypeError, ValueError) as exc:
        raise ValueError("alert intent state is invalid") from exc
    opened_at = _payload_timestamp(payload.get("opened_at"), "alert opened_at")
    last_seen_at = _payload_timestamp(payload.get("last_seen_at"), "alert last_seen_at")
    if last_seen_at < opened_at:
        raise ValueError("alert intent chronology is invalid")
    if payload.get("status") != "pending":
        raise ValueError("alert intent initial status is invalid")
    _request(
        "POST",
        "ccw_support_alert_intents",
        query={"on_conflict": "tenant_id,dedup_key"},
        payload=payload,
        prefer="resolution=ignore-duplicates,return=minimal",
    )
    encoded_seen_at = last_seen_at.isoformat()
    _request(
        "PATCH",
        "ccw_support_alert_intents",
        query={
            "tenant_id": f"eq.{TENANT_ID}",
            "dedup_key": f"eq.{dedup_key}",
            "status": "in.(pending,drafted)",
            "last_seen_at": f"lt.{encoded_seen_at}",
            "opened_at": f"lte.{encoded_seen_at}",
        },
        payload={"last_seen_at": last_seen_at},
        prefer="return=minimal",
    )
