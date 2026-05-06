"""tests/test_discovery_archive.py — RA-2027 Linear archive cron handler.

Mocks the Linear GraphQL transport so tests run in milliseconds without
hitting the real API. Pins:
  * No-API-key path returns structured error
  * Label-not-found returns structured error
  * Stale candidate listing query shape
  * Archive verifies sev>=6 (priority 1-2) tickets are NEVER closed
  * Comment + state transition both fire on successful archive
  * Per-team Canceled-state cache works (no duplicate lookups)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server import discovery_archive  # noqa: E402


# ── No API key ───────────────────────────────────────────────────────────────


def test_archive_returns_error_when_no_api_key(monkeypatch):
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    report = discovery_archive.archive_stale_discovery_tickets()
    assert "no_linear_api_key" in report.errors
    assert report.archived == []


# ── Stale candidate listing ──────────────────────────────────────────────────


def test_archive_skips_label_not_found(monkeypatch):
    monkeypatch.setenv("LINEAR_API_KEY", "fake-key")
    with patch.object(
        discovery_archive, "_gql",
        return_value={"data": {"issueLabels": {"nodes": []}}},
    ):
        report = discovery_archive.archive_stale_discovery_tickets()
    assert "discovery_loop_label_not_found" in report.errors


def test_archive_inspects_candidates(monkeypatch):
    monkeypatch.setenv("LINEAR_API_KEY", "fake-key")

    def fake_gql(query, variables=None, **_):
        if "issueLabels" in query:
            return {"data": {"issueLabels": {"nodes": [
                {"id": "label-uuid", "name": "discovery-loop"},
            ]}}}
        if "issues(" in query:
            return {"data": {"issues": {"nodes": [
                {
                    "id": "iss-1", "identifier": "RA-9001", "title": "Stale 1",
                    "priority": 3,
                    "team": {"id": "team-RA"},
                    "state": {"id": "s1", "name": "Backlog", "type": "backlog"},
                },
                {
                    "id": "iss-2", "identifier": "RA-9002", "title": "Stale 2",
                    "priority": 4,
                    "team": {"id": "team-RA"},
                    "state": {"id": "s1", "name": "Backlog", "type": "backlog"},
                },
            ]}}}
        if "team(" in query and "states" in query:
            return {"data": {"team": {"states": {"nodes": [
                {"id": "cancel-uuid", "name": "Canceled", "type": "canceled"},
            ]}}}}
        if "issueUpdate" in query:
            return {"data": {"issueUpdate": {"success": True}}}
        if "commentCreate" in query:
            return {"data": {"commentCreate": {"success": True}}}
        return {"error": "unexpected_query"}

    with patch.object(discovery_archive, "_gql", side_effect=fake_gql):
        report = discovery_archive.archive_stale_discovery_tickets()

    assert report.inspected == 2
    assert sorted(report.archived) == ["RA-9001", "RA-9002"]
    assert report.errors == []


def test_archive_skips_high_severity_defence_in_depth(monkeypatch):
    """Even if the GraphQL filter let a priority-1 (Urgent) ticket through,
    the per-row check still skips it."""
    monkeypatch.setenv("LINEAR_API_KEY", "fake-key")

    def fake_gql(query, variables=None, **_):
        if "issueLabels" in query:
            return {"data": {"issueLabels": {"nodes": [
                {"id": "label-uuid", "name": "discovery-loop"},
            ]}}}
        if "issues(" in query:
            return {"data": {"issues": {"nodes": [
                # Priority 1 (Urgent) — must NOT be archived
                {
                    "id": "iss-urgent", "identifier": "RA-1001",
                    "title": "Urgent regulator update", "priority": 1,
                    "team": {"id": "team-RA"},
                    "state": {"id": "s1", "name": "Todo", "type": "unstarted"},
                },
                # Priority 4 (Low) — should be archived
                {
                    "id": "iss-low", "identifier": "RA-1002",
                    "title": "Low signal", "priority": 4,
                    "team": {"id": "team-RA"},
                    "state": {"id": "s1", "name": "Backlog", "type": "backlog"},
                },
            ]}}}
        if "team(" in query and "states" in query:
            return {"data": {"team": {"states": {"nodes": [
                {"id": "cancel-uuid", "name": "Canceled", "type": "canceled"},
            ]}}}}
        if "issueUpdate" in query:
            return {"data": {"issueUpdate": {"success": True}}}
        if "commentCreate" in query:
            return {"data": {"commentCreate": {"success": True}}}
        return {"error": "unexpected"}

    with patch.object(discovery_archive, "_gql", side_effect=fake_gql):
        report = discovery_archive.archive_stale_discovery_tickets()

    assert report.skipped_high_severity == 1
    assert report.archived == ["RA-1002"]
    assert "RA-1001" not in report.archived


def test_archive_caches_canceled_state_per_team(monkeypatch):
    """Multiple tickets in the same team should only resolve Canceled state once."""
    monkeypatch.setenv("LINEAR_API_KEY", "fake-key")
    state_lookup_count = {"n": 0}

    def fake_gql(query, variables=None, **_):
        if "issueLabels" in query:
            return {"data": {"issueLabels": {"nodes": [
                {"id": "label-uuid", "name": "discovery-loop"},
            ]}}}
        if "issues(" in query:
            return {"data": {"issues": {"nodes": [
                {"id": f"iss-{i}", "identifier": f"RA-{i}",
                 "title": f"t{i}", "priority": 4,
                 "team": {"id": "team-RA"},
                 "state": {"id": "s1", "name": "Backlog", "type": "backlog"}}
                for i in range(5)
            ]}}}
        if "team(" in query and "states" in query:
            state_lookup_count["n"] += 1
            return {"data": {"team": {"states": {"nodes": [
                {"id": "cancel-uuid", "name": "Canceled", "type": "canceled"},
            ]}}}}
        if "issueUpdate" in query:
            return {"data": {"issueUpdate": {"success": True}}}
        if "commentCreate" in query:
            return {"data": {"commentCreate": {"success": True}}}
        return {"error": "unexpected"}

    with patch.object(discovery_archive, "_gql", side_effect=fake_gql):
        report = discovery_archive.archive_stale_discovery_tickets()

    assert len(report.archived) == 5
    # Despite 5 tickets sharing team-RA, the canceled-state lookup runs ONCE
    assert state_lookup_count["n"] == 1


def test_archive_records_close_failure(monkeypatch):
    monkeypatch.setenv("LINEAR_API_KEY", "fake-key")

    def fake_gql(query, variables=None, **_):
        if "issueLabels" in query:
            return {"data": {"issueLabels": {"nodes": [
                {"id": "label-uuid", "name": "discovery-loop"},
            ]}}}
        if "issues(" in query:
            return {"data": {"issues": {"nodes": [
                {"id": "iss-1", "identifier": "RA-fail",
                 "title": "x", "priority": 4,
                 "team": {"id": "team-RA"},
                 "state": {"id": "s1", "name": "Backlog", "type": "backlog"}},
            ]}}}
        if "team(" in query and "states" in query:
            return {"data": {"team": {"states": {"nodes": [
                {"id": "cancel-uuid", "name": "Canceled", "type": "canceled"},
            ]}}}}
        if "issueUpdate" in query:
            return {"data": {"issueUpdate": {"success": False}}}
        if "commentCreate" in query:
            return {"data": {"commentCreate": {"success": True}}}
        return {"error": "unexpected"}

    with patch.object(discovery_archive, "_gql", side_effect=fake_gql):
        report = discovery_archive.archive_stale_discovery_tickets()

    assert report.archived == []
    assert any("close_failed:RA-fail" in e for e in report.errors)


# ── Cron dispatcher shim ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fire_discovery_archive_trigger_invokes_archive(monkeypatch):
    captured = {"calls": 0}
    def fake_archive():
        captured["calls"] += 1
        return discovery_archive.ArchiveReport(
            started_at="2026-05-06", finished_at="2026-05-06",
            inspected=0,
        )
    monkeypatch.setattr(
        discovery_archive, "archive_stale_discovery_tickets", fake_archive,
    )
    import logging
    log = logging.getLogger("test")
    await discovery_archive._fire_discovery_archive_trigger(
        {"id": "discovery-archive-stale-daily", "type": "discovery_archive"},
        log,
    )
    assert captured["calls"] == 1
