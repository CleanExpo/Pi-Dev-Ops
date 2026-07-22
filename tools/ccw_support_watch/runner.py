"""Fixture-driven CCW watcher lifecycle and response reconciliation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from swarm.ccw_support_contract import (
    ConsumerCheckpoint,
    HealthEvidence,
    SupportSnapshot,
    derive_state,
)
from .ledger import InMemoryLedger, stable_source_key
from .source import SourceResult, parse_source_response


@dataclass(frozen=True)
class ResponseMatch:
    responded_at: datetime | None
    within_sla: bool


@dataclass(frozen=True)
class WatchResult:
    run_id: str
    source: SourceResult
    snapshot: SupportSnapshot


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def match_first_response(
    inbound_at: datetime,
    outbound_candidates: list[datetime] | tuple[datetime, ...],
) -> ResponseMatch:
    inbound = _utc(inbound_at)
    valid = sorted(
        _utc(value) for value in outbound_candidates if _utc(value) >= inbound
    )
    if not valid:
        return ResponseMatch(None, False)
    earliest = valid[0]
    return ResponseMatch(earliest, earliest - inbound <= timedelta(minutes=30))


def _error_snapshot(
    result: SourceResult, run_id: str, now: datetime
) -> SupportSnapshot:
    return derive_state(
        HealthEvidence(
            now=now,
            latest_run_id=run_id,
            outcome="error",
            heartbeat_at=now,
            source_auth_ok=result.authenticated,
            source_query_ok=False,
            error_code=result.error_code,
        )
    )


def run_watch(
    fetch: Callable[[], object],
    ledger: InMemoryLedger,
    *,
    now: datetime,
    load_checkpoints: Callable[[str], tuple[ConsumerCheckpoint, ...]] | None = None,
) -> WatchResult:
    """Run one bounded fixture cycle; no network or external delivery is owned here."""
    now = _utc(now)
    run = ledger.start_run(now)
    try:
        source = parse_source_response(fetch())
    except Exception:  # The boundary persists only an allow-listed error code.
        source = SourceResult(False, False, error_code="INTERNAL_ERROR")
    if not source.ok:
        ledger.complete(
            run.run_id,
            now,
            outcome="error",
            source_auth_ok=source.authenticated,
            source_query_ok=False,
            error_code=source.error_code,
        )
        return WatchResult(run.run_id, source, _error_snapshot(source, run.run_id, now))

    persisted = 0
    pending = 0
    matched = 0
    open_over_30m = 0
    oldest_pending = None
    escalation_count = 0
    future_source = False
    for item in source.items:
        if item.received_at - now > timedelta(minutes=5):
            future_source = True
            continue
        if ledger.persist(item):
            persisted += 1
        else:
            pending += 1
            oldest_pending = min(oldest_pending or item.received_at, item.received_at)
        response = match_first_response(item.received_at, item.outbound_at)
        matched += response.responded_at is not None
        if response.responded_at is None and now - item.received_at > timedelta(
            minutes=30
        ):
            open_over_30m += 1
        if item.priority in {"urgent", "escalated"}:
            escalation_count += 1
            dedup = hashlib.sha256(
                f"ESCALATION:{stable_source_key(item.provider_id)}".encode()
            ).hexdigest()
            ledger.create_alert_intent(dedup, "ESCALATION", run.run_id, now)

    cursor_hash = hashlib.sha256(
        "|".join(
            sorted(stable_source_key(item.provider_id) for item in source.items)
        ).encode()
    ).hexdigest()
    heartbeat = now + timedelta(minutes=6) if future_source else now
    ledger.heartbeat(run.run_id, heartbeat)
    ledger.complete(
        run.run_id,
        now,
        outcome="success",
        source_auth_ok=True,
        source_query_ok=True,
        source_seen_count=len(source.items),
        persisted_count=persisted,
        pending_count=pending,
        response_matched_count=matched,
        cursor_hash=cursor_hash,
        open_over_30m_count=open_over_30m,
    )
    try:
        checkpoints = load_checkpoints(run.run_id) if load_checkpoints else ()
    except Exception:
        checkpoints = ()
    evidence = HealthEvidence(
        now=now,
        latest_run_id=run.run_id,
        outcome="success",
        heartbeat_at=heartbeat,
        source_auth_ok=True,
        source_query_ok=True,
        pending_count=pending,
        source_oldest_unpersisted_at=oldest_pending,
        open_over_30m_count=open_over_30m,
        unresolved_escalation_count=escalation_count,
        checkpoints=checkpoints,
    )
    return WatchResult(run.run_id, source, derive_state(evidence))
