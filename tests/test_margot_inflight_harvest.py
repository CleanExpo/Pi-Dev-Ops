"""Tests for swarm.margot_inflight — async deep research harvest per chat."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from swarm import margot_inflight


def test_harvest_completed_for_chat_marks_harvested(tmp_path, monkeypatch):
    inflight = tmp_path / ".harness" / "swarm" / "margot_inflight.jsonl"
    inflight.parent.mkdir(parents=True)
    inflight.write_text(
        json.dumps({
            "ts": "2026-07-01T12:00:00+00:00",
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

    monkeypatch.setattr(
        "swarm.margot_tools.check_research",
        fake_check,
        raising=False,
    )

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
        raising=False,
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
        raising=False,
    )
    assert margot_inflight.harvest_completed_for_chat("9") == []
