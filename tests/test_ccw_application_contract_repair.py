"""Regression controls for the accepted PR #600 application repair contract."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from swarm import ccw_support_contract as contract
from swarm.providers import ccw_supabase
from tools.ccw_support_watch.ledger import InMemoryLedger

NOW = datetime(2026, 7, 22, 1, 0, tzinfo=timezone.utc)


def _aggregate_row(**overrides: object) -> dict:
    row = {
        "state": "BACKLOG",
        "reason_code": "FIRST_RESPONSE_OVER_30M",
        "latest_run_id": "run-1",
        "heartbeat_at": NOW.isoformat(),
        "source_query_ok": True,
        "pending_count": 0,
        "open_over_30m_count": 1,
        "unresolved_escalation_count": 0,
        "consumer_checkpoint_at": NOW.isoformat(),
    }
    row.update(overrides)
    return row


def test_aggregate_default_read_is_tenant_scoped_and_exposes_duplicates(monkeypatch):
    calls = []
    monkeypatch.setattr(
        ccw_supabase,
        "_request",
        lambda method, resource, **kwargs: calls.append((method, resource, kwargs))
        or [_aggregate_row()],
    )

    snapshot = ccw_supabase.fetch_ccw_state()

    assert snapshot.tenant_id == "ccw"
    assert calls == [
        (
            "GET",
            "ccw_support_state",
            {
                "query": {
                    "select": ",".join(ccw_supabase.AGGREGATE_COLUMNS),
                    "tenant_id": "eq.ccw",
                    "limit": "2",
                }
            },
        )
    ]


def test_checkpoint_write_is_tenant_run_consumer_create_only(monkeypatch):
    calls = []
    monkeypatch.setattr(
        ccw_supabase,
        "_request",
        lambda method, resource, **kwargs: calls.append((method, resource, kwargs)) or [],
    )
    payload = {
        "tenant_id": "ccw",
        "consumer_id": "cs_metrics",
        "source_run_id": "run-1",
        "checked_at": NOW,
        "completed_at": NOW,
        "outcome": "success",
        "derived_state": "INGEST_STALE",
        "error_code": None,
    }

    ccw_supabase.record_consumer_checkpoint(payload)

    assert calls[0][2]["query"] == {
        "on_conflict": "tenant_id,source_run_id,consumer_id"
    }
    assert calls[0][2]["prefer"] == "resolution=ignore-duplicates,return=minimal"
    assert calls[0][2]["payload"] == payload


def test_alert_replay_creates_once_then_advances_only_nonterminal_newer_sighting(monkeypatch):
    calls = []
    monkeypatch.setattr(
        ccw_supabase,
        "_request",
        lambda method, resource, **kwargs: calls.append((method, resource, kwargs)) or [],
    )
    payload = {
        "tenant_id": "ccw",
        "dedup_key": "a" * 64,
        "state": "ESCALATION",
        "source_run_id": "run-1",
        "opened_at": NOW,
        "last_seen_at": NOW + timedelta(minutes=1),
        "status": "pending",
    }

    ccw_supabase.create_alert_intent(payload)

    assert calls[0][0] == "POST"
    assert calls[0][2]["query"] == {"on_conflict": "tenant_id,dedup_key"}
    assert calls[0][2]["prefer"] == "resolution=ignore-duplicates,return=minimal"
    assert calls[1] == (
        "PATCH",
        "ccw_support_alert_intents",
        {
            "query": {
                "tenant_id": "eq.ccw",
                "dedup_key": "eq." + "a" * 64,
                "status": "in.(pending,drafted)",
                "last_seen_at": "lt." + payload["last_seen_at"].isoformat(),
                "opened_at": "lte." + payload["last_seen_at"].isoformat(),
            },
            "payload": {"last_seen_at": payload["last_seen_at"]},
            "prefer": "return=minimal",
        },
    )


def test_terminal_and_out_of_order_in_memory_alert_replays_are_immutable():
    ledger = InMemoryLedger()
    key = "b" * 64
    first = ledger.create_alert_intent(key, "ESCALATION", "run-1", NOW, tenant_id="ccw")
    ledger.intents[("ccw", key)] = replace(first, status="sent")

    terminal = ledger.create_alert_intent(
        key,
        "ESCALATION",
        "run-2",
        NOW + timedelta(minutes=2),
        tenant_id="ccw",
    )
    stale = ledger.create_alert_intent(
        key,
        "ESCALATION",
        "run-0",
        NOW - timedelta(minutes=1),
        tenant_id="ccw",
    )

    assert terminal == stale == ledger.intents[("ccw", key)]
    assert terminal.status == "sent"
    assert terminal.source_run_id == "run-1"
    assert terminal.opened_at == terminal.last_seen_at == NOW


@pytest.mark.parametrize(
    ("state", "reason"),
    [
        ("BACKLOG", "customer@example.com"),
        ("BACKLOG", "STALE_CONSUMER"),
        ("QUIET_HEALTHY", "FIRST_RESPONSE_OVER_30M"),
        ("INGEST_STALE", "missing_consumer:cs_metrics"),
    ],
)
def test_arbitrary_dynamic_and_state_incompatible_reasons_fail_closed(state, reason):
    with pytest.raises(ValueError, match="state/reason"):
        contract.validate_state_reason(contract.SupportState(state), reason)


def test_bounded_reason_is_validated_before_six_pager_render_without_echo():
    from swarm.six_pager_client import render_ccw_client_health

    snapshot = contract.SupportSnapshot(
        state=contract.SupportState.BACKLOG,
        reason_code="private customer@example.com",
        latest_run_id="run-1",
        heartbeat_at=NOW,
        source_query_ok=True,
        pending_count=1,
        open_over_30m_count=0,
        unresolved_escalation_count=0,
        consumer_checkpoint_at=NOW,
        tenant_id="ccw",
    )
    with pytest.raises(ValueError, match="state/reason") as caught:
        render_ccw_client_health(snapshot)
    assert "customer@example.com" not in str(caught.value)


def test_six_pager_materialisation_is_silent_and_same_run_scoped():
    from swarm.six_pager_dispatcher import materialise_ccw_checkpoint

    rows = []
    snapshot = contract.SupportSnapshot(
        state=contract.SupportState.INGEST_STALE,
        reason_code="MISSING_HEARTBEAT",
        latest_run_id="run-1",
        heartbeat_at=NOW,
        source_query_ok=True,
        pending_count=0,
        open_over_30m_count=0,
        unresolved_escalation_count=0,
        consumer_checkpoint_at=None,
        tenant_id="ccw",
    )

    rendered = materialise_ccw_checkpoint(
        snapshot,
        checked_at=NOW,
        record_checkpoint=rows.append,
    )

    assert "CCW CLIENT HEALTH" in rendered
    assert rows == [
        {
            "tenant_id": "ccw",
            "consumer_id": "six_pager",
            "source_run_id": "run-1",
            "checked_at": NOW,
            "completed_at": NOW,
            "outcome": "success",
            "derived_state": "INGEST_STALE",
            "error_code": None,
        }
    ]
    json.dumps(rows[0], default=str)


def test_orchestrator_materialises_all_consumers_then_refetches_same_run():
    from swarm.orchestrator import _materialise_ccw_cycle

    initial = contract.SupportSnapshot(
        state=contract.SupportState.INGEST_STALE,
        reason_code="STALE_CONSUMER",
        latest_run_id="run-1",
        heartbeat_at=NOW,
        source_query_ok=True,
        pending_count=0,
        open_over_30m_count=0,
        unresolved_escalation_count=0,
        consumer_checkpoint_at=None,
        tenant_id="ccw",
    )
    final = replace(
        initial,
        state=contract.SupportState.QUIET_HEALTHY,
        reason_code="FRESH_SUCCESS",
        consumer_checkpoint_at=NOW,
    )
    events = []

    result = _materialise_ccw_cycle(
        initial,
        checked_at=NOW,
        process_support_state=lambda snapshot, **_kwargs: events.append(
            ("cs", snapshot.latest_run_id)
        ),
        materialise_six_pager=lambda snapshot, **_kwargs: events.append(
            ("six_pager", snapshot.latest_run_id)
        ),
        fetch_state=lambda: events.append(("refetch", "run-1")) or final,
        record_checkpoint=lambda _payload: None,
        create_intent=lambda _payload: None,
        record_alert_checkpoint=lambda _payload: None,
    )

    assert result is final
    assert events == [
        ("cs", "run-1"),
        ("six_pager", "run-1"),
        ("refetch", "run-1"),
    ]
