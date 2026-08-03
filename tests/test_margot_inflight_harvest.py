"""Tests for swarm.margot_inflight — async deep research harvest per chat."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from swarm import margot_inflight


def _recent_ts() -> str:
    """A timestamp inside harvest_completed_for_chat's max_age_days window.

    A literal date here is a time bomb: the entry ages past the 32-day cutoff at
    margot_inflight.py:96 and the harvest silently reclassifies it
    "harvested:expired", so `findings` comes back empty. The previous literal
    (2026-07-01) expired on 2026-08-02 and turned this into `assert 0 == 1`.
    """
    return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


def test_harvest_completed_for_chat_marks_harvested(tmp_path, monkeypatch):
    inflight = tmp_path / ".harness" / "swarm" / "margot_inflight.jsonl"
    inflight.parent.mkdir(parents=True)
    inflight.write_text(
        json.dumps({
            "ts": _recent_ts(),
            "interaction_id": "ix-1",
            "topic": "NRPG pricing",
            "originating_session_id": "margot_chat:42",
            "chat_id": "42",
            "status": "dispatched",
        }) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(margot_inflight, "INFLIGHT_LOG", inflight)

    def fake_check(interaction_id: str):
        assert interaction_id == "ix-1"
        return {"status": "completed", "report": "Pricing is $99/mo."}

    monkeypatch.setattr("swarm.margot_tools.check_research", fake_check)

    findings = margot_inflight.harvest_completed_for_chat("42")
    assert len(findings) == 1
    assert findings[0]["topic"] == "NRPG pricing"
    assert "99" in findings[0]["summary"]

    rows = [json.loads(line) for line in inflight.read_text().splitlines()]
    assert rows[0]["status"] == "harvested"


def test_harvest_skips_board_meeting_entries(tmp_path, monkeypatch):
    inflight = tmp_path / "margot_inflight.jsonl"
    inflight.write_text(
        json.dumps({
            "interaction_id": "board-1",
            "originating_session_id": "board_meeting:3:2026-07-01",
            "status": "dispatched",
            "topic": "board topic",
        }) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(margot_inflight, "INFLIGHT_LOG", inflight)
    monkeypatch.setattr(
        "swarm.margot_tools.check_research",
        lambda _id: {"status": "completed", "report": "x"},
    )
    assert margot_inflight.harvest_completed_for_chat("42") == []


def test_harvest_pending_returns_empty(tmp_path, monkeypatch):
    inflight = tmp_path / "margot_inflight.jsonl"
    inflight.write_text(
        json.dumps({
            "interaction_id": "ix-pending",
            "originating_session_id": "margot_chat:9",
            "status": "dispatched",
            "topic": "still running",
        }) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(margot_inflight, "INFLIGHT_LOG", inflight)
    monkeypatch.setattr(
        "swarm.margot_tools.check_research",
        lambda _id: {"status": "processing"},
    )
    assert margot_inflight.harvest_completed_for_chat("9") == []
