"""RED controls for the frozen aggregate health-state contract."""
from datetime import datetime, timedelta, timezone

from swarm.ccw_support_contract import (
    ConsumerCheckpoint, HealthEvidence, SupportState, derive_state,
)

NOW = datetime(2026, 7, 22, 1, 0, tzinfo=timezone.utc)


def _checkpoints(completed_at=NOW):
    return tuple(ConsumerCheckpoint(name, "run-1", completed_at, completed_at)
                 for name in ("cs_metrics", "six_pager", "alert_intent"))


def _healthy(**overrides):
    values = dict(
        now=NOW, latest_run_id="run-1", outcome="success", heartbeat_at=NOW,
        source_auth_ok=True, source_query_ok=True, checkpoints=_checkpoints(),
    )
    values.update(overrides)
    return HealthEvidence(**values)


def test_red_01_zero_tickets_without_health_is_stale_not_all_clear():
    snapshot = derive_state(HealthEvidence(now=NOW))
    assert snapshot.state is SupportState.INGEST_STALE
    assert snapshot.reason_code == "missing_heartbeat"


def test_red_02_heartbeat_equality_is_fresh_then_one_microsecond_is_stale():
    exact = derive_state(_healthy(heartbeat_at=NOW - timedelta(minutes=10)))
    over = derive_state(_healthy(heartbeat_at=NOW - timedelta(minutes=10, microseconds=1)))
    assert exact.state is SupportState.QUIET_HEALTHY
    assert over.state is SupportState.INGEST_STALE


def test_red_10_consumer_equality_is_fresh_then_one_microsecond_is_stale():
    exact = derive_state(_healthy(checkpoints=_checkpoints(NOW - timedelta(hours=26))))
    over = derive_state(_healthy(checkpoints=_checkpoints(NOW - timedelta(hours=26, microseconds=1))))
    assert exact.state is SupportState.QUIET_HEALTHY
    assert over.state is SupportState.INGEST_STALE
    assert "stale_consumer" in over.reason_code


def test_red_11_fresh_complete_evidence_can_certify_quiet():
    snapshot = derive_state(_healthy())
    assert snapshot.state is SupportState.QUIET_HEALTHY
    assert snapshot.latest_run_id == "run-1"
    assert snapshot.consumer_checkpoint_at == NOW


def test_red_13_heartbeat_more_than_five_minutes_future_is_stale():
    exact = derive_state(_healthy(heartbeat_at=NOW + timedelta(minutes=5)))
    over = derive_state(_healthy(heartbeat_at=NOW + timedelta(minutes=5, microseconds=1)))
    assert exact.state is SupportState.QUIET_HEALTHY
    assert over.state is SupportState.INGEST_STALE
    assert over.reason_code == "future_heartbeat"


def test_precedence_escalation_beats_error_stale_and_backlog():
    snapshot = derive_state(_healthy(
        outcome="error", error_code="QUERY_FAILED", heartbeat_at=None,
        pending_count=1, open_over_30m_count=1, unresolved_escalation_count=1,
    ))
    assert snapshot.state is SupportState.ESCALATION
