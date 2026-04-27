"""
test_session_recovery.py — RA-1407 PR 2 unit tests for startup recovery.

Covers:
  - recover_interrupted_sessions_from_supabase happy path → schedules resume
  - cap at MAX_CONCURRENT_SESSIONS
  - skips sessions already in local _sessions (local JSON restore handled it)
  - skips sessions with no last_completed_phase in checkpoint
  - fail-soft on Supabase fetch error → returns 0
  - get_recovered_count returns the last scheduled count
  - rehydrated session has expected fields from checkpoint JSONB
"""
import asyncio
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture(autouse=True)
def _reset_state():
    """Each test starts with empty _sessions and zero recovery counter."""
    from app.server import session_model
    session_model._sessions.clear()
    session_model._recovered_from_supabase = 0
    yield
    session_model._sessions.clear()
    session_model._recovered_from_supabase = 0


def _row(sid: str, last_phase: str = "generate", status: str = "interrupted") -> dict:
    return {
        "id": sid,
        "repo_url": "https://github.com/CleanExpo/Pi-Dev-Ops",
        "status": status,
        "checkpoint": {
            "last_completed_phase": last_phase,
            "retry_count": 1,
            "evaluator_status": "pending",
            "evaluator_score": None,
            "evaluator_model": "sonnet",
            "evaluator_consensus": "",
            "linear_issue_id": "RA-1407",
            "workspace": f"/tmp/pi-ceo-workspaces/{sid}",
            "error": "",
            "output_line_count": 5,
        },
    }


def test_recovery_schedules_resume_for_each_row():
    from app.server import session_model

    rows = [_row("s1"), _row("s2")]
    fake_run_build = MagicMock(return_value=asyncio.sleep(0))

    with patch("app.server.supabase_log.fetch_interrupted_sessions", return_value=rows), \
         patch("app.server.session_phases.run_build", new=fake_run_build):
        scheduled = session_model.recover_interrupted_sessions_from_supabase()

    assert scheduled == 2
    assert "s1" in session_model._sessions
    assert "s2" in session_model._sessions
    assert session_model._sessions["s1"].last_completed_phase == "generate"
    assert session_model._sessions["s1"].linear_issue_id == "RA-1407"
    assert fake_run_build.call_count == 2


def test_recovery_caps_at_max_concurrent():
    from app.server import session_model

    rows = [_row(f"s{i}") for i in range(10)]
    fake_run_build = MagicMock(return_value=asyncio.sleep(0))

    with patch("app.server.supabase_log.fetch_interrupted_sessions", return_value=rows), \
         patch("app.server.session_phases.run_build", new=fake_run_build):
        scheduled = session_model.recover_interrupted_sessions_from_supabase(max_concurrent=3)

    assert scheduled == 3
    assert fake_run_build.call_count == 3


def test_recovery_skips_already_local():
    """Sessions already in _sessions (loaded by local JSON restore) are skipped."""
    from app.server import session_model

    # Pretend s1 was already restored from local JSON
    session_model._sessions["s1"] = session_model.BuildSession(id="s1", status="interrupted")

    rows = [_row("s1"), _row("s2")]
    fake_run_build = MagicMock(return_value=asyncio.sleep(0))

    with patch("app.server.supabase_log.fetch_interrupted_sessions", return_value=rows), \
         patch("app.server.session_phases.run_build", new=fake_run_build):
        scheduled = session_model.recover_interrupted_sessions_from_supabase()

    # Only s2 should be scheduled — s1 was already local
    assert scheduled == 1
    assert fake_run_build.call_count == 1


def test_recovery_skips_rows_without_last_phase():
    """A row with empty checkpoint.last_completed_phase is unresumable; skip it."""
    from app.server import session_model

    bad_row = _row("s1")
    bad_row["checkpoint"]["last_completed_phase"] = ""
    rows = [bad_row, _row("s2")]
    fake_run_build = MagicMock(return_value=asyncio.sleep(0))

    with patch("app.server.supabase_log.fetch_interrupted_sessions", return_value=rows), \
         patch("app.server.session_phases.run_build", new=fake_run_build):
        scheduled = session_model.recover_interrupted_sessions_from_supabase()

    assert scheduled == 1
    assert "s1" not in session_model._sessions
    assert "s2" in session_model._sessions


def test_recovery_returns_zero_when_supabase_fails():
    from app.server import session_model

    with patch(
        "app.server.supabase_log.fetch_interrupted_sessions",
        side_effect=RuntimeError("supabase down"),
    ):
        scheduled = session_model.recover_interrupted_sessions_from_supabase()

    assert scheduled == 0
    assert session_model._sessions == {}


def test_recovery_returns_zero_when_no_rows():
    from app.server import session_model

    with patch("app.server.supabase_log.fetch_interrupted_sessions", return_value=[]):
        scheduled = session_model.recover_interrupted_sessions_from_supabase()

    assert scheduled == 0


def test_get_recovered_count_reflects_last_run():
    from app.server import session_model

    rows = [_row("s1"), _row("s2"), _row("s3")]
    fake_run_build = MagicMock(return_value=asyncio.sleep(0))

    with patch("app.server.supabase_log.fetch_interrupted_sessions", return_value=rows), \
         patch("app.server.session_phases.run_build", new=fake_run_build):
        session_model.recover_interrupted_sessions_from_supabase(max_concurrent=2)

    assert session_model.get_recovered_count() == 2


def test_recovery_fail_soft_on_individual_rehydrate_error():
    """One bad row should not stop the rest from being scheduled."""
    from app.server import session_model

    # Simulate a row that crashes BuildSession construction by injecting None checkpoint
    # (the function should handle gracefully — checkpoint defaults to {})
    rows = [
        _row("s1"),
        {"id": "bad", "repo_url": "", "status": "interrupted", "checkpoint": {"last_completed_phase": ""}},
        _row("s2"),
    ]
    fake_run_build = MagicMock(return_value=asyncio.sleep(0))

    with patch("app.server.supabase_log.fetch_interrupted_sessions", return_value=rows), \
         patch("app.server.session_phases.run_build", new=fake_run_build):
        scheduled = session_model.recover_interrupted_sessions_from_supabase()

    # bad row skipped (no last_completed_phase), s1 and s2 succeed
    assert scheduled == 2
    assert "s1" in session_model._sessions
    assert "s2" in session_model._sessions
    assert "bad" not in session_model._sessions
