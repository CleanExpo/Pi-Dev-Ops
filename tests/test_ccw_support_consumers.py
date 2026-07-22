"""RED controls for fail-closed CS, six-pager and checkpoint consumers."""
from __future__ import annotations

import importlib
import sys
import types
from datetime import datetime, timezone

from swarm.ccw_support_contract import SupportSnapshot, SupportState

NOW = datetime(2026, 7, 22, 1, 0, tzinfo=timezone.utc)


def _snapshot(state=SupportState.INGEST_STALE, reason="missing_heartbeat"):
    return SupportSnapshot(state, reason, "run-1", NOW, True, 0, 0, 0, NOW)


def _client():
    try:
        return importlib.import_module("swarm.six_pager_client")
    except ModuleNotFoundError as exc:
        raise AssertionError("RED-10 fail-closed six-pager client section is missing") from exc


def test_nonhealthy_ccw_section_is_mandatory_and_cannot_be_suppressed():
    text = _client().render_ccw_client_health(_snapshot())
    assert "CCW CLIENT HEALTH" in text
    assert "INGEST_STALE" in text
    assert "missing_heartbeat" in text
    assert "all clear" not in text.lower()


def test_quiet_requires_ids_and_renders_certified_not_synthetic():
    text = _client().render_ccw_client_health(_snapshot(SupportState.QUIET_HEALTHY, "fresh_zero_backlog"))
    assert "QUIET_HEALTHY" in text
    assert "run-1" in text
    assert "certified" in text.lower()


def test_cs_consumer_records_checkpoint_and_intent_without_external_send():
    from swarm.bots import cs

    checkpoints, intents = [], []
    result = cs.process_ccw_support_state(
        _snapshot(SupportState.ESCALATION, "unresolved_escalation"),
        checked_at=NOW, record_checkpoint=checkpoints.append,
        create_intent=intents.append,
    )
    assert result["status"] == "non_healthy"
    assert checkpoints[0]["consumer_id"] == "cs_metrics"
    assert intents[0]["state"] == "ESCALATION"
    assert "delivery" not in intents[0]


def test_cs_escalation_intent_dedup_is_stable_across_source_runs():
    from swarm.bots import cs

    intents = []
    for run_id in ("run-1", "run-2"):
        snapshot = SupportSnapshot(
            SupportState.ESCALATION, "unresolved_escalation", run_id,
            NOW, True, 0, 0, 1, NOW,
        )
        cs.process_ccw_support_state(
            snapshot, checked_at=NOW, record_checkpoint=lambda _row: None,
            create_intent=intents.append,
        )
    assert intents[0]["dedup_key"] == intents[1]["dedup_key"]


def test_six_pager_checkpoint_is_recorded_only_after_all_drafts_succeed(monkeypatch, tmp_path):
    from swarm import six_pager_dispatcher as dispatcher

    monkeypatch.setenv("TAO_SIX_PAGER_HOUR_UTC", "1")
    monkeypatch.setenv("TAO_DRAFT_REVIEW_TEST", "1")
    fake_redactor = types.SimpleNamespace(redact=lambda text: text)
    monkeypatch.setitem(sys.modules, "swarm.pii_redactor", fake_redactor)
    checkpoints = []
    calls = {"count": 0}

    def fail_second(**_kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("partial draft")
        return {"draft_id": "draft-1"}

    monkeypatch.setitem(sys.modules, "swarm.draft_review", types.SimpleNamespace(post_draft=fail_second))
    monkeypatch.setattr("swarm.six_pager.chunk_for_telegram", lambda _text: ["one", "two"])
    fired = dispatcher.maybe_fire_daily(
        {}, repo_root=tmp_path, now=NOW,
        ccw_snapshot=_snapshot(), record_checkpoint=checkpoints.append,
    )
    assert fired is False
    assert checkpoints == []


def test_six_pager_success_records_checkpoint_after_draft(monkeypatch, tmp_path):
    from swarm import six_pager_dispatcher as dispatcher

    monkeypatch.setenv("TAO_SIX_PAGER_HOUR_UTC", "1")
    monkeypatch.setitem(sys.modules, "swarm.pii_redactor", types.SimpleNamespace(redact=lambda text: text))
    monkeypatch.setitem(sys.modules, "swarm.draft_review", types.SimpleNamespace(
        post_draft=lambda **_kwargs: {"draft_id": "draft-ok"},
    ))
    checkpoints = []
    fired = dispatcher.maybe_fire_daily(
        {}, repo_root=tmp_path, now=NOW,
        ccw_snapshot=_snapshot(), record_checkpoint=checkpoints.append,
    )
    assert fired is True
    assert checkpoints == [{
        "consumer_id": "six_pager", "source_run_id": "run-1",
        "checked_at": NOW, "completed_at": NOW, "outcome": "success",
        "derived_state": "INGEST_STALE", "error_code": None,
    }]
