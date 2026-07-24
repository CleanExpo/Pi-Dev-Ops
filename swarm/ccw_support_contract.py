"""Pure CCW support-ingest health contract shared by fixture-only consumers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum


class SupportState(str, Enum):
    ESCALATION = "ESCALATION"
    INGEST_ERROR = "INGEST_ERROR"
    INGEST_STALE = "INGEST_STALE"
    BACKLOG = "BACKLOG"
    QUIET_HEALTHY = "QUIET_HEALTHY"


TENANT_ID = "ccw"
STATE_PRECEDENCE = tuple(SupportState)
REQUIRED_CONSUMERS = ("cs_metrics", "six_pager", "alert_intent")
WATCHER_CADENCE = timedelta(minutes=5)
HEARTBEAT_STALE_AFTER = timedelta(minutes=10)
SOURCE_TO_LEDGER_AFTER = timedelta(minutes=5)
FIRST_RESPONSE_AFTER = timedelta(minutes=30)
CONSUMER_STALE_AFTER = timedelta(hours=26)
ESCALATION_INTENT_AFTER = timedelta(minutes=5)
FUTURE_HEARTBEAT_TOLERANCE = timedelta(minutes=5)

CHECKPOINT_ERROR_CODES = frozenset(
    {
        "QUERY_FAILED",
        "STATE_INVALID",
        "CHECKPOINT_FAILED",
        "DRAFT_FAILED",
        "INTENT_FAILED",
        "INTERNAL_ERROR",
    }
)
STATE_REASON_MATRIX = {
    SupportState.ESCALATION: frozenset({"UNRESOLVED_ESCALATION"}),
    SupportState.INGEST_ERROR: frozenset(
        {
            "AUTH_FAILED",
            "QUERY_FAILED",
            "MALFORMED_RESPONSE",
            "MISSING_SOURCE_ID",
            "PERSIST_FAILED",
            "RECONCILE_FAILED",
            "INTERNAL_ERROR",
        }
    ),
    SupportState.INGEST_STALE: frozenset(
        {
            "MISSING_HEARTBEAT",
            "RUN_IN_PROGRESS",
            "STALE_HEARTBEAT",
            "STALE_CONSUMER",
            "SOURCE_TO_LEDGER_LAG",
        }
    ),
    SupportState.BACKLOG: frozenset(
        {"SOURCE_TO_LEDGER_LAG", "FIRST_RESPONSE_OVER_30M"}
    ),
    SupportState.QUIET_HEALTHY: frozenset({"FRESH_SUCCESS"}),
}
REASON_CODES = frozenset().union(*STATE_REASON_MATRIX.values())
ERROR_CODES = CHECKPOINT_ERROR_CODES | STATE_REASON_MATRIX[SupportState.INGEST_ERROR]


def validate_tenant_id(tenant_id: object) -> str:
    if tenant_id != TENANT_ID:
        raise ValueError("CCW tenant identity is invalid")
    return TENANT_ID


def validate_state_reason(state: SupportState, reason_code: object) -> str:
    if not isinstance(reason_code, str) or reason_code not in STATE_REASON_MATRIX[state]:
        raise ValueError("CCW state/reason contract is invalid")
    return reason_code


@dataclass(frozen=True)
class ConsumerCheckpoint:
    consumer_id: str
    source_run_id: str
    checked_at: datetime
    completed_at: datetime
    outcome: str = "success"
    error_code: str | None = None
    tenant_id: str = TENANT_ID


@dataclass(frozen=True)
class HealthEvidence:
    now: datetime
    latest_run_id: str | None = None
    outcome: str | None = None
    heartbeat_at: datetime | None = None
    source_auth_ok: bool | None = None
    source_query_ok: bool | None = None
    error_code: str | None = None
    pending_count: int = 0
    source_oldest_unpersisted_at: datetime | None = None
    open_over_30m_count: int = 0
    unresolved_escalation_count: int = 0
    checkpoints: tuple[ConsumerCheckpoint, ...] = field(default_factory=tuple)
    tenant_id: str = TENANT_ID


@dataclass(frozen=True)
class SupportSnapshot:
    state: SupportState
    reason_code: str
    latest_run_id: str | None
    heartbeat_at: datetime | None
    source_query_ok: bool | None
    pending_count: int
    open_over_30m_count: int
    unresolved_escalation_count: int
    consumer_checkpoint_at: datetime | None
    tenant_id: str = TENANT_ID


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _stale_consumer(evidence: HealthEvidence) -> str | None:
    by_id = {item.consumer_id: item for item in evidence.checkpoints}
    for consumer_id in REQUIRED_CONSUMERS:
        checkpoint = by_id.get(consumer_id)
        if checkpoint is None:
            return "STALE_CONSUMER"
        if (
            checkpoint.tenant_id != evidence.tenant_id
            or checkpoint.source_run_id != evidence.latest_run_id
        ):
            return "STALE_CONSUMER"
        if checkpoint.outcome != "success":
            return "STALE_CONSUMER"
        if _utc(evidence.now) - _utc(checkpoint.completed_at) > CONSUMER_STALE_AFTER:
            return "STALE_CONSUMER"
    return None


def derive_state(evidence: HealthEvidence) -> SupportSnapshot:
    """Derive fail-closed state using the frozen precedence and boundaries."""
    tenant_id = validate_tenant_id(evidence.tenant_id)
    now = _utc(evidence.now)
    checkpoint_at = max(
        (item.completed_at for item in evidence.checkpoints),
        default=None,
    )
    state = SupportState.QUIET_HEALTHY
    reason = "FRESH_SUCCESS"
    if evidence.unresolved_escalation_count > 0:
        state, reason = SupportState.ESCALATION, "UNRESOLVED_ESCALATION"
    elif (
        evidence.outcome == "error"
        or evidence.source_auth_ok is False
        or evidence.source_query_ok is False
        or evidence.error_code
    ):
        state = SupportState.INGEST_ERROR
        reason = (
            evidence.error_code
            if evidence.error_code in STATE_REASON_MATRIX[SupportState.INGEST_ERROR]
            else "INTERNAL_ERROR"
        )
    elif evidence.latest_run_id is None or evidence.heartbeat_at is None:
        state, reason = SupportState.INGEST_STALE, "MISSING_HEARTBEAT"
    else:
        heartbeat = _utc(evidence.heartbeat_at)
        age = now - heartbeat
        stale_reason = _stale_consumer(evidence)
        if heartbeat - now > FUTURE_HEARTBEAT_TOLERANCE:
            state, reason = SupportState.INGEST_STALE, "STALE_HEARTBEAT"
        elif age > HEARTBEAT_STALE_AFTER:
            state, reason = SupportState.INGEST_STALE, "STALE_HEARTBEAT"
        elif evidence.outcome != "success":
            state, reason = SupportState.INGEST_STALE, "RUN_IN_PROGRESS"
        elif stale_reason:
            state, reason = SupportState.INGEST_STALE, stale_reason
        elif evidence.pending_count and evidence.source_oldest_unpersisted_at:
            lag = now - _utc(evidence.source_oldest_unpersisted_at)
            if lag > SOURCE_TO_LEDGER_AFTER:
                state, reason = SupportState.BACKLOG, "SOURCE_TO_LEDGER_LAG"
        if state is SupportState.QUIET_HEALTHY and evidence.open_over_30m_count:
            state, reason = SupportState.BACKLOG, "FIRST_RESPONSE_OVER_30M"
    validate_state_reason(state, reason)
    return SupportSnapshot(
        state=state,
        reason_code=reason,
        latest_run_id=evidence.latest_run_id,
        heartbeat_at=evidence.heartbeat_at,
        source_query_ok=evidence.source_query_ok,
        pending_count=evidence.pending_count,
        open_over_30m_count=evidence.open_over_30m_count,
        unresolved_escalation_count=evidence.unresolved_escalation_count,
        consumer_checkpoint_at=checkpoint_at,
        tenant_id=tenant_id,
    )
