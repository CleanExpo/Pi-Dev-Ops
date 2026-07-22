"""RED controls for fail-closed CS, six-pager and checkpoint consumers."""

from __future__ import annotations

import importlib
import sys
import types
from datetime import datetime, timezone

import pytest

from swarm.ccw_support_contract import SupportSnapshot, SupportState

NOW = datetime(2026, 7, 22, 1, 0, tzinfo=timezone.utc)


def _snapshot(state=SupportState.INGEST_STALE, reason="MISSING_HEARTBEAT"):
    return SupportSnapshot(state, reason, "run-1", NOW, True, 0, 0, 0, NOW)


def _client():
    try:
        return importlib.import_module("swarm.six_pager_client")
    except ModuleNotFoundError as exc:
        raise AssertionError(
            "RED-10 fail-closed six-pager client section is missing"
        ) from exc


def test_nonhealthy_ccw_section_is_mandatory_and_cannot_be_suppressed():
    text = _client().render_ccw_client_health(_snapshot())
    assert "CCW CLIENT HEALTH" in text
    assert "INGEST_STALE" in text
    assert "MISSING_HEARTBEAT" in text
    assert "all clear" not in text.lower()


def test_quiet_requires_ids_and_renders_certified_not_synthetic():
    text = _client().render_ccw_client_health(
        _snapshot(SupportState.QUIET_HEALTHY, "FRESH_SUCCESS")
    )
    assert "QUIET_HEALTHY" in text
    assert "run-1" in text
    assert "certified" in text.lower()


def test_six_pager_always_renders_missing_ccw_health_as_stale(tmp_path):
    from swarm.six_pager import assemble_six_pager

    text = assemble_six_pager(repo_root=tmp_path, date_str="2026-07-22")

    assert "CCW CLIENT HEALTH" in text
    assert "INGEST_STALE" in text
    assert "MISSING_HEARTBEAT" in text


def test_cs_consumer_records_checkpoint_and_intent_without_external_send():
    from swarm.bots import cs

    checkpoints, intents = [], []
    result = cs.process_ccw_support_state(
        _snapshot(SupportState.ESCALATION, "UNRESOLVED_ESCALATION"),
        checked_at=NOW,
        record_checkpoint=checkpoints.append,
        create_intent=intents.append,
    )
    assert result["status"] == "non_healthy"
    assert [row["consumer_id"] for row in checkpoints] == [
        "alert_intent",
        "cs_metrics",
    ]
    assert intents[0]["state"] == "ESCALATION"
    assert "delivery" not in intents[0]


def test_quiet_cs_consumer_records_noop_alert_intent_checkpoint_without_creating_intent():
    from swarm.bots import cs

    checkpoints, intents = [], []
    result = cs.process_ccw_support_state(
        _snapshot(SupportState.QUIET_HEALTHY, "FRESH_SUCCESS"),
        checked_at=NOW,
        record_checkpoint=checkpoints.append,
        create_intent=intents.append,
    )

    assert result["status"] == "healthy"
    assert intents == []
    assert [row["consumer_id"] for row in checkpoints] == [
        "alert_intent",
        "cs_metrics",
    ]


def test_cs_escalation_intent_dedup_is_stable_across_source_runs():
    from swarm.bots import cs

    intents = []
    for run_id in ("run-1", "run-2"):
        snapshot = SupportSnapshot(
            SupportState.ESCALATION,
            "UNRESOLVED_ESCALATION",
            run_id,
            NOW,
            True,
            0,
            0,
            1,
            NOW,
        )
        cs.process_ccw_support_state(
            snapshot,
            checked_at=NOW,
            record_checkpoint=lambda _row: None,
            create_intent=intents.append,
        )
    assert intents[0]["dedup_key"] == intents[1]["dedup_key"]


def test_six_pager_checkpoint_is_recorded_only_after_all_drafts_succeed(
    monkeypatch, tmp_path
):
    import swarm
    from swarm import six_pager_dispatcher as dispatcher

    monkeypatch.setenv("TAO_SIX_PAGER_HOUR_UTC", "1")
    monkeypatch.setenv("TAO_DRAFT_REVIEW_TEST", "1")
    fake_redactor = types.SimpleNamespace(redact=lambda text: text)
    monkeypatch.setitem(sys.modules, "swarm.pii_redactor", fake_redactor)
    monkeypatch.setattr(swarm, "pii_redactor", fake_redactor, raising=False)
    checkpoints = []
    calls = {"count": 0}

    def fail_second(**_kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("partial draft")
        return {"draft_id": "draft-1"}

    fake_draft_review = types.SimpleNamespace(post_draft=fail_second)
    monkeypatch.setitem(sys.modules, "swarm.draft_review", fake_draft_review)
    monkeypatch.setattr(swarm, "draft_review", fake_draft_review, raising=False)
    monkeypatch.setattr(
        "swarm.six_pager.chunk_for_telegram", lambda _text: ["one", "two"]
    )
    fired = dispatcher.maybe_fire_daily(
        {},
        repo_root=tmp_path,
        now=NOW,
        ccw_snapshot=_snapshot(),
        record_checkpoint=checkpoints.append,
    )
    assert fired is False
    assert checkpoints == []


def test_daily_six_pager_does_not_own_checkpoint_certification(monkeypatch, tmp_path):
    import swarm
    from swarm import six_pager_dispatcher as dispatcher

    monkeypatch.setenv("TAO_SIX_PAGER_HOUR_UTC", "1")
    fake_redactor = types.SimpleNamespace(redact=lambda text: text)
    fake_draft_review = types.SimpleNamespace(
        post_draft=lambda **_kwargs: {"draft_id": "draft-ok"},
    )
    monkeypatch.setitem(sys.modules, "swarm.pii_redactor", fake_redactor)
    monkeypatch.setattr(swarm, "pii_redactor", fake_redactor, raising=False)
    monkeypatch.setitem(sys.modules, "swarm.draft_review", fake_draft_review)
    monkeypatch.setattr(swarm, "draft_review", fake_draft_review, raising=False)
    checkpoints = []
    fired = dispatcher.maybe_fire_daily(
        {},
        repo_root=tmp_path,
        now=NOW,
        ccw_snapshot=_snapshot(),
        record_checkpoint=checkpoints.append,
    )
    assert fired is True
    assert checkpoints == []


def test_real_consumer_writers_close_same_run_without_replaying_alerts(
    monkeypatch, tmp_path
):
    from swarm.bots import cs
    from swarm.providers import ccw_supabase
    from swarm import six_pager_dispatcher as dispatcher
    from tools.ccw_support_watch.ledger import InMemoryLedger
    from tools.ccw_support_watch.runner import re_evaluate_run, run_watch

    checkpoint_rows, intents = {}, {}

    def fake_request(method, resource, *, query=None, payload=None, prefer=None):
        assert payload is not None
        row = {
            key: value.isoformat() if isinstance(value, datetime) else value
            for key, value in payload.items()
        }
        if resource == "ccw_support_consumer_checkpoints":
            assert method == "POST"
            assert prefer == "resolution=ignore-duplicates,return=minimal"
            assert query == {"on_conflict": "tenant_id,source_run_id,consumer_id"}
            identity = (row["tenant_id"], row["source_run_id"], row["consumer_id"])
            checkpoint_rows.setdefault(identity, row)
        elif resource == "ccw_support_alert_intents":
            if method == "POST":
                assert prefer == "resolution=ignore-duplicates,return=minimal"
                assert query == {"on_conflict": "tenant_id,dedup_key"}
                intents.setdefault((row["tenant_id"], row["dedup_key"]), row)
            else:
                assert method == "PATCH"
                assert prefer == "return=minimal"
        else:
            raise AssertionError(resource)
        return []

    monkeypatch.setattr(ccw_supabase, "_request", fake_request)
    ledger = InMemoryLedger()
    first = run_watch(
        lambda: {"authenticated": True, "ok": True, "items": []},
        ledger,
        now=NOW,
    )
    cs.process_ccw_support_state(
        first.snapshot,
        checked_at=NOW,
        record_checkpoint=ccw_supabase.record_consumer_checkpoint,
        create_intent=ccw_supabase.create_alert_intent,
        record_alert_checkpoint=ccw_supabase.record_alert_intent_checkpoint,
    )

    dispatcher.materialise_ccw_checkpoint(
        first.snapshot,
        checked_at=NOW,
        record_checkpoint=ccw_supabase.record_consumer_checkpoint,
    )

    result = re_evaluate_run(
        ledger,
        first.run_id,
        now=NOW,
        load_checkpoints=lambda tenant_id, run_id: ccw_supabase.load_consumer_checkpoints(
            run_id,
            tenant_id=tenant_id,
            fetch=lambda source_run_id, _columns: [
                row
                for row in checkpoint_rows.values()
                if row["source_run_id"] == source_run_id
                and row["tenant_id"] == tenant_id
            ],
        ),
    )
    assert result.state is SupportState.QUIET_HEALTHY
    assert {identity[2] for identity in checkpoint_rows} == {
        "cs_metrics", "six_pager", "alert_intent",
    }
    assert len(ledger.runs) == 1
    assert len(intents) == 1
    assert all(intent["status"] == "pending" for intent in intents.values())


def test_six_pager_rejects_unbounded_reason_without_echo():
    snapshot = _snapshot(SupportState.BACKLOG, "private customer@example.com")
    with pytest.raises(ValueError, match="state/reason") as caught:
        _client().render_ccw_client_health(snapshot)
    assert "customer@example.com" not in str(caught.value)


def test_six_pager_materialisation_is_silent_and_same_run_scoped():
    from swarm.six_pager_dispatcher import materialise_ccw_checkpoint

    rows = []
    rendered = materialise_ccw_checkpoint(
        _snapshot(),
        checked_at=NOW,
        record_checkpoint=rows.append,
    )

    assert "CCW CLIENT HEALTH" in rendered
    assert rows == [{
        "tenant_id": "ccw",
        "consumer_id": "six_pager",
        "source_run_id": "run-1",
        "checked_at": NOW,
        "completed_at": NOW,
        "outcome": "success",
        "derived_state": "INGEST_STALE",
        "error_code": None,
    }]
