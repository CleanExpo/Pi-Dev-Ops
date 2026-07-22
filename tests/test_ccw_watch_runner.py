"""RED controls for watcher lifecycle, reconciliation and intent idempotency."""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone

NOW = datetime(2026, 7, 22, 1, 0, tzinfo=timezone.utc)


def _module(name: str):
    try:
        return importlib.import_module(f"tools.ccw_support_watch.{name}")
    except ModuleNotFoundError as exc:
        raise AssertionError(f"RED watcher {name} behaviour is missing") from exc


def test_red_05_source_to_ledger_one_microsecond_over_five_minutes_is_backlog():
    ledger = _module("ledger").InMemoryLedger()
    runner = _module("runner")
    item = {"provider_id": "m-1", "received_at": NOW - timedelta(minutes=5, microseconds=1)}
    result = runner.run_watch(lambda: {"authenticated": True, "ok": True, "items": [item]}, ledger, now=NOW)
    assert result.snapshot.state.value == "BACKLOG"
    assert result.snapshot.pending_count == 1


def test_red_06_replay_is_idempotent_for_ticket_and_intent():
    ledger = _module("ledger").InMemoryLedger()
    runner = _module("runner")
    item = {"provider_id": "same-id", "received_at": NOW.isoformat(), "priority": "urgent"}
    fetch = lambda: {"authenticated": True, "ok": True, "items": [item]}
    runner.run_watch(fetch, ledger, now=NOW)
    runner.run_watch(fetch, ledger, now=NOW + timedelta(minutes=1))
    assert ledger.ticket_count == 1
    assert ledger.intent_count == 1


def test_red_08_exact_thirty_minutes_is_inside_but_one_microsecond_over_is_not():
    match = _module("runner").match_first_response
    inbound = NOW
    exact = match(inbound, [NOW + timedelta(minutes=30)])
    over = match(inbound, [NOW + timedelta(minutes=30, microseconds=1)])
    assert exact.within_sla is True
    assert over.within_sla is False


def test_red_08_earliest_valid_outbound_wins_and_clock_skew_is_ignored():
    match = _module("runner").match_first_response
    inbound = NOW
    result = match(inbound, [NOW - timedelta(seconds=1), NOW + timedelta(minutes=9), NOW + timedelta(minutes=2)])
    assert result.responded_at == NOW + timedelta(minutes=2)


def test_red_09_escalation_creates_intent_only_within_five_minutes():
    ledger = _module("ledger").InMemoryLedger()
    runner = _module("runner")
    item = {"provider_id": "urgent-1", "received_at": NOW.isoformat(), "priority": "urgent"}
    result = runner.run_watch(
        lambda: {"authenticated": True, "ok": True, "items": [item]}, ledger, now=NOW,
    )
    assert result.snapshot.state.value == "ESCALATION"
    assert ledger.intent_count == 1
    assert ledger.sent_count == 0


def test_red_13_future_or_retrograde_timestamps_never_certify_quiet():
    runner = _module("runner")
    ledger = _module("ledger").InMemoryLedger()
    future = {"provider_id": "future", "received_at": NOW + timedelta(minutes=6)}
    result = runner.run_watch(
        lambda: {"authenticated": True, "ok": True, "items": [future]}, ledger, now=NOW,
    )
    assert result.snapshot.state.value == "INGEST_STALE"


def test_red_14_repeated_escalation_deduplicates_and_advances_last_seen():
    ledger = _module("ledger").InMemoryLedger()
    key = "a" * 64
    first = ledger.create_alert_intent(key, "ESCALATION", "run-1", NOW)
    second = ledger.create_alert_intent(key, "ESCALATION", "run-2", NOW + timedelta(minutes=1))
    assert ledger.intent_count == 1
    assert first.intent_id == second.intent_id
    assert second.last_seen_at > first.last_seen_at
