"""RED controls for watcher lifecycle, reconciliation and intent idempotency."""

from __future__ import annotations

import importlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone

NOW = datetime(2026, 7, 22, 1, 0, tzinfo=timezone.utc)


def _module(name: str):
    try:
        return importlib.import_module(f"tools.ccw_support_watch.{name}")
    except ModuleNotFoundError as exc:
        raise AssertionError(f"RED watcher {name} behaviour is missing") from exc


def _observed_checkpoints(tenant_id, run_id):
    contract = importlib.import_module("swarm.ccw_support_contract")
    return tuple(
        contract.ConsumerCheckpoint(name, run_id, NOW, NOW, tenant_id=tenant_id)
        for name in ("cs_metrics", "six_pager", "alert_intent")
    )


def test_red_05_source_to_ledger_one_microsecond_over_five_minutes_is_backlog():
    ledger = _module("ledger").InMemoryLedger(accept_persistence=False)
    runner = _module("runner")
    item = {
        "provider_id": "m-1",
        "received_at": (NOW - timedelta(minutes=5, microseconds=1)).isoformat(),
    }
    result = runner.run_watch(
        lambda: {"authenticated": True, "ok": True, "items": [item]},
        ledger,
        now=NOW,
        load_checkpoints=_observed_checkpoints,
    )
    assert result.snapshot.state.value == "BACKLOG"
    assert result.snapshot.pending_count == 1


def test_red_06_replay_is_idempotent_for_ticket_and_intent():
    ledger = _module("ledger").InMemoryLedger()
    runner = _module("runner")
    item = {
        "provider_id": "same-id",
        "received_at": NOW.isoformat(),
        "priority": "urgent",
    }

    def fetch():
        return {"authenticated": True, "ok": True, "items": [item]}

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
    result = match(
        inbound,
        [
            NOW - timedelta(seconds=1),
            NOW + timedelta(minutes=9),
            NOW + timedelta(minutes=2),
        ],
    )
    assert result.responded_at == NOW + timedelta(minutes=2)


def test_red_09_escalation_creates_intent_only_within_five_minutes():
    ledger = _module("ledger").InMemoryLedger()
    runner = _module("runner")
    item = {
        "provider_id": "urgent-1",
        "received_at": NOW.isoformat(),
        "priority": "urgent",
    }
    result = runner.run_watch(
        lambda: {"authenticated": True, "ok": True, "items": [item]},
        ledger,
        now=NOW,
    )
    assert result.snapshot.state.value == "ESCALATION"
    assert ledger.intent_count == 1
    assert ledger.sent_count == 0


def test_red_13_future_or_retrograde_timestamps_never_certify_quiet():
    runner = _module("runner")
    ledger = _module("ledger").InMemoryLedger()
    future = {
        "provider_id": "future",
        "received_at": (NOW + timedelta(minutes=6)).isoformat(),
    }
    result = runner.run_watch(
        lambda: {"authenticated": True, "ok": True, "items": [future]},
        ledger,
        now=NOW,
    )
    assert result.snapshot.state.value == "INGEST_STALE"


def test_red_14_repeated_escalation_deduplicates_and_advances_last_seen():
    ledger = _module("ledger").InMemoryLedger()
    key = "a" * 64
    first = ledger.create_alert_intent(key, "ESCALATION", "run-1", NOW)
    second = ledger.create_alert_intent(
        key, "ESCALATION", "run-2", NOW + timedelta(minutes=1)
    )
    assert ledger.intent_count == 1
    assert first.intent_id == second.intent_id
    assert second.last_seen_at > first.last_seen_at


def test_terminal_and_out_of_order_alert_replays_are_immutable():
    ledger = _module("ledger").InMemoryLedger()
    key = "b" * 64
    first = ledger.create_alert_intent(key, "ESCALATION", "run-1", NOW)
    ledger.intents[("ccw", key)] = replace(first, status="sent")

    terminal = ledger.create_alert_intent(
        key, "ESCALATION", "run-2", NOW + timedelta(minutes=2)
    )
    stale = ledger.create_alert_intent(
        key, "ESCALATION", "run-0", NOW - timedelta(minutes=1)
    )

    assert terminal == stale == ledger.intents[("ccw", key)]
    assert terminal.status == "sent"
    assert terminal.source_run_id == "run-1"
    assert terminal.opened_at == terminal.last_seen_at == NOW


def test_watch_cannot_self_certify_consumer_health():
    ledger = _module("ledger").InMemoryLedger()
    runner = _module("runner")

    result = runner.run_watch(
        lambda: {"authenticated": True, "ok": True, "items": []},
        ledger,
        now=NOW,
    )

    assert result.snapshot.state.value == "INGEST_STALE"
    assert result.snapshot.reason_code == "STALE_CONSUMER"
    assert result.snapshot.consumer_checkpoint_at is None


def test_consumer_checkpoint_read_failure_fails_stale_without_escaping():
    ledger = _module("ledger").InMemoryLedger()
    runner = _module("runner")

    result = runner.run_watch(
        lambda: {"authenticated": True, "ok": True, "items": []},
        ledger,
        now=NOW,
        load_checkpoints=lambda _tenant_id, _run_id: (_ for _ in ()).throw(
            RuntimeError("private checkpoint detail")
        ),
    )

    assert result.snapshot.state.value == "INGEST_STALE"
    assert result.snapshot.reason_code == "STALE_CONSUMER"
    assert "private checkpoint detail" not in repr(result)


def test_fetch_exception_completes_one_bounded_error_run():
    ledger = _module("ledger").InMemoryLedger()
    runner = _module("runner")

    def fail_fetch():
        raise RuntimeError("private transport detail")

    result = runner.run_watch(fail_fetch, ledger, now=NOW)

    completed = list(ledger.runs.values())
    assert len(completed) == 1
    assert completed[0].outcome == "error"
    assert completed[0].completed_at == NOW
    assert completed[0].error_code == "INTERNAL_ERROR"
    assert result.source.error_code == "INTERNAL_ERROR"
    assert result.snapshot.state.value == "INGEST_ERROR"
    assert "private transport detail" not in repr(result)


def test_unanswered_item_one_microsecond_over_thirty_minutes_is_backlog():
    ledger = _module("ledger").InMemoryLedger()
    runner = _module("runner")
    item = {
        "provider_id": "unanswered-1",
        "received_at": (NOW - timedelta(minutes=30, microseconds=1)).isoformat(),
    }

    result = runner.run_watch(
        lambda: {"authenticated": True, "ok": True, "items": [item]},
        ledger,
        now=NOW,
        load_checkpoints=_observed_checkpoints,
    )

    assert result.snapshot.state.value == "BACKLOG"
    assert result.snapshot.reason_code == "FIRST_RESPONSE_OVER_30M"
    assert result.snapshot.open_over_30m_count == 1


def test_completed_run_is_re_evaluated_after_real_consumers_persist_evidence(
    monkeypatch,
):
    ledger = _module("ledger").InMemoryLedger()
    runner = _module("runner")
    from swarm.providers import ccw_supabase

    rows = []
    load_rows = ccw_supabase.load_consumer_checkpoints
    monkeypatch.setattr(
        ccw_supabase,
        "load_consumer_checkpoints",
        lambda run_id, *, tenant_id="ccw": load_rows(
            run_id, tenant_id=tenant_id, fetch=lambda _run, _columns: rows
        ),
    )
    first = runner.run_watch_persisted(
        lambda: {"authenticated": True, "ok": True, "items": []},
        ledger,
        now=NOW,
    )
    assert first.snapshot.state.value == "INGEST_STALE"
    for consumer_id in ("cs_metrics", "six_pager", "alert_intent"):
        rows.append(
            {
                "tenant_id": "ccw",
                "consumer_id": consumer_id,
                "source_run_id": first.run_id,
                "checked_at": NOW.isoformat(),
                "completed_at": NOW.isoformat(),
                "outcome": "success",
                "derived_state": "INGEST_STALE",
                "error_code": None,
            }
        )
    result = runner.re_evaluate_persisted_run(ledger, first.run_id, now=NOW)
    assert result.state.value == "QUIET_HEALTHY"
    assert result.latest_run_id == first.run_id
    assert len(ledger.runs) == 1
    assert ledger.intent_count == 0


def test_re_evaluation_fails_closed_for_missing_malformed_stale_and_cross_run_evidence():
    ledger = _module("ledger").InMemoryLedger()
    runner = _module("runner")
    first = runner.run_watch(
        lambda: {"authenticated": True, "ok": True, "items": []},
        ledger,
        now=NOW,
    )

    missing = runner.re_evaluate_run(
        ledger, first.run_id, now=NOW,
        load_checkpoints=lambda _tenant, _run: ()
    )
    assert missing.reason_code == "STALE_CONSUMER"

    stale = runner.re_evaluate_run(
        ledger,
        first.run_id,
        now=NOW,
        load_checkpoints=lambda tenant_id, run_id: tuple(
            importlib.import_module("swarm.ccw_support_contract").ConsumerCheckpoint(
                name,
                run_id,
                NOW - timedelta(hours=26, microseconds=1),
                NOW - timedelta(hours=26, microseconds=1),
                tenant_id=tenant_id,
            )
            for name in ("cs_metrics", "six_pager", "alert_intent")
        ),
    )
    assert stale.reason_code == "STALE_CONSUMER"

    cross_run = runner.re_evaluate_run(
        ledger,
        first.run_id,
        now=NOW,
        load_checkpoints=lambda tenant_id, _run: _observed_checkpoints(
            tenant_id, "another-run"
        ),
    )
    assert cross_run.reason_code == "STALE_CONSUMER"

    malformed = runner.re_evaluate_run(
        ledger,
        first.run_id,
        now=NOW,
        load_checkpoints=lambda _tenant, _run: (_ for _ in ()).throw(
            ValueError("private row")
        ),
    )
    assert malformed.reason_code == "STALE_CONSUMER"
    assert "private row" not in repr(malformed)


def test_re_evaluation_rejects_unknown_or_incomplete_runs_without_allocating_new_run():
    ledger = _module("ledger").InMemoryLedger()
    runner = _module("runner")
    with __import__("pytest").raises(ValueError, match="completed run"):
        runner.re_evaluate_run(
            ledger, "missing", now=NOW,
            load_checkpoints=lambda _tenant, _run: ()
        )
    active = ledger.start_run(NOW)
    with __import__("pytest").raises(ValueError, match="completed run"):
        runner.re_evaluate_run(
            ledger, active.run_id, now=NOW,
            load_checkpoints=lambda _tenant, _run: ()
        )
    assert len(ledger.runs) == 1
