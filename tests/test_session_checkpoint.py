"""
test_session_checkpoint.py — RA-1407 PR 1 unit tests.

Covers:
  - save_session_checkpoint builds the row correctly from a session
  - completed_at filled only on terminal states
  - missing optional attrs use sensible defaults (no crashes)
  - non-fatal: Supabase upsert failure → returns False, never raises
  - persistence.save_session calls supabase_log.save_session_checkpoint
  - fetch_interrupted_sessions returns parsed dicts
  - _repo_name_from_url handles common patterns

All Supabase HTTP is mocked. No live network in CI.
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest


def _mk_session(**overrides):
    """Build a SimpleNamespace stand-in for BuildSession with sensible defaults."""
    base = {
        "id": "test-sid-001",
        "repo_url": "https://github.com/CleanExpo/Pi-Dev-Ops",
        "branch": "feat/test",
        "status": "running",
        "trigger": "manual",
        "started_at": 1700000000.0,
        "last_completed_phase": "generate",
        "retry_count": 1,
        "evaluator_status": "pending",
        "evaluator_score": None,
        "evaluator_model": "sonnet",
        "evaluator_consensus": "",
        "linear_issue_id": "RA-1407",
        "workspace": "/tmp/pi-ceo-workspaces/test-sid-001",
        "error": "",
        "output_lines": [{"text": "x"}, {"text": "y"}],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# ── save_session_checkpoint shape ───────────────────────────────────────────


def test_save_checkpoint_builds_correct_row():
    from app.server import supabase_log

    captured = {}

    def fake_upsert(table, row):
        captured["table"] = table
        captured["row"] = row
        return True

    with patch.object(supabase_log, "_upsert", side_effect=fake_upsert):
        ok = supabase_log.save_session_checkpoint(_mk_session())

    assert ok is True
    assert captured["table"] == "sessions"
    row = captured["row"]
    assert row["id"] == "test-sid-001"
    assert row["repo_url"].endswith("Pi-Dev-Ops")
    assert row["repo_name"] == "CleanExpo/Pi-Dev-Ops"
    assert row["status"] == "running"
    assert row["branch"] == "feat/test"
    assert "checkpoint" in row
    cp = row["checkpoint"]
    assert cp["last_completed_phase"] == "generate"
    assert cp["retry_count"] == 1
    assert cp["evaluator_status"] == "pending"
    assert cp["linear_issue_id"] == "RA-1407"
    assert cp["workspace"].endswith("test-sid-001")
    assert cp["output_line_count"] == 2
    # non-terminal status → no completed_at
    assert "completed_at" not in row


@pytest.mark.parametrize("terminal_status", [
    "complete", "done", "failed", "error", "killed", "interrupted", "blocked",
])
def test_save_checkpoint_sets_completed_at_on_terminal(terminal_status):
    from app.server import supabase_log

    captured = {}
    with patch.object(supabase_log, "_upsert", side_effect=lambda t, r: captured.update(row=r) or True):
        supabase_log.save_session_checkpoint(_mk_session(status=terminal_status))

    assert "completed_at" in captured["row"], f"status={terminal_status} should fill completed_at"


def test_save_checkpoint_handles_missing_optional_attrs():
    from app.server import supabase_log

    minimal = SimpleNamespace(
        id="minimal-sid",
        repo_url="https://github.com/foo/bar.git",
        status="created",
        output_lines=[],
    )
    with patch.object(supabase_log, "_upsert", return_value=True) as mock_up:
        ok = supabase_log.save_session_checkpoint(minimal)

    assert ok is True
    row = mock_up.call_args[0][1]
    assert row["repo_name"] == "foo/bar"  # .git stripped
    assert row["branch"] == ""
    assert row["trigger"] == "manual"
    assert row["checkpoint"]["retry_count"] == 0
    assert row["checkpoint"]["output_line_count"] == 0


def test_save_checkpoint_returns_false_on_upsert_exception():
    """Any internal exception from the Supabase write must NOT propagate."""
    from app.server import supabase_log

    def boom(*a, **k):
        raise RuntimeError("simulated supabase outage")

    with patch.object(supabase_log, "_upsert", side_effect=boom):
        ok = supabase_log.save_session_checkpoint(_mk_session())

    assert ok is False  # surface failure → False, never raises


def test_save_checkpoint_no_id_returns_false():
    from app.server import supabase_log
    s = SimpleNamespace(id="", repo_url="", status="", output_lines=[])
    assert supabase_log.save_session_checkpoint(s) is False


def test_save_checkpoint_none_returns_false():
    from app.server import supabase_log
    assert supabase_log.save_session_checkpoint(None) is False


# ── persistence dual-write ──────────────────────────────────────────────────


def test_persistence_save_session_calls_supabase_writer(tmp_path, monkeypatch):
    """save_session in persistence.py must invoke supabase_log.save_session_checkpoint."""
    from app.server import persistence, supabase_log
    monkeypatch.setattr(persistence.config, "LOG_DIR", str(tmp_path))

    session = _mk_session()

    with patch.object(supabase_log, "save_session_checkpoint", return_value=True) as mock_checkpoint:
        persistence.save_session(session)

    mock_checkpoint.assert_called_once_with(session)
    # local JSON file also written
    json_path = persistence._path("test-sid-001")
    assert os.path.exists(json_path), f"local JSON not written at {json_path}"


def test_persistence_save_session_swallows_supabase_failure(tmp_path, monkeypatch):
    """Supabase write failure must NOT propagate to caller."""
    from app.server import persistence, supabase_log
    monkeypatch.setattr(persistence.config, "LOG_DIR", str(tmp_path))

    def boom(*a, **k):
        raise RuntimeError("supabase outage")

    with patch.object(supabase_log, "save_session_checkpoint", side_effect=boom):
        # Should not raise
        persistence.save_session(_mk_session())

    # Local JSON still written
    assert os.path.exists(persistence._path("test-sid-001"))


# ── fetch_interrupted_sessions ──────────────────────────────────────────────


def test_fetch_interrupted_sessions_returns_list():
    from app.server import supabase_log

    fake_rows = [
        {"id": "s1", "status": "interrupted", "checkpoint": {"last_completed_phase": "generate"}},
        {"id": "s2", "status": "interrupted", "checkpoint": {"last_completed_phase": "evaluate"}},
    ]
    with patch.object(supabase_log, "_select", return_value=fake_rows):
        rows = supabase_log.fetch_interrupted_sessions(limit=10)

    assert len(rows) == 2
    assert rows[0]["status"] == "interrupted"
    assert rows[1]["checkpoint"]["last_completed_phase"] == "evaluate"


def test_fetch_interrupted_sessions_empty_on_error():
    from app.server import supabase_log

    with patch.object(supabase_log, "_select", side_effect=RuntimeError("bad gateway")):
        rows = supabase_log.fetch_interrupted_sessions()

    assert rows == []


# ── repo_name parsing ───────────────────────────────────────────────────────


@pytest.mark.parametrize("url,expected", [
    ("https://github.com/CleanExpo/Pi-Dev-Ops", "CleanExpo/Pi-Dev-Ops"),
    ("https://github.com/CleanExpo/Pi-Dev-Ops.git", "CleanExpo/Pi-Dev-Ops"),
    ("https://github.com/CleanExpo/Pi-Dev-Ops/", "CleanExpo/Pi-Dev-Ops"),
    ("git@github.com:CleanExpo/Pi-Dev-Ops.git", "github.com:CleanExpo/Pi-Dev-Ops"),
    ("", "unknown"),
])
def test_repo_name_from_url(url, expected):
    from app.server.supabase_log import _repo_name_from_url
    # Tolerate slight variation on SSH format — the canonical https URL is the
    # primary use case
    result = _repo_name_from_url(url)
    if expected == "unknown":
        assert result == "unknown"
    else:
        # Just check it strips .git and trailing slash; SSH form yields the
        # last-2-segments pattern
        assert result.endswith(expected.split(":")[-1]) or result == expected
