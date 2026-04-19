"""
test_create_session_concurrency.py — RA-1375 regression tests.

Locks:
  - create_session() raises RuntimeError when MAX_CONCURRENT_SESSIONS active
    sessions already exist (status in "created"/"cloning"/"building"/"evaluating").
  - create_session() succeeds when all existing sessions are in terminal states.
  - Each active status individually counts toward the cap.
  - Terminal statuses do NOT count toward the cap.
"""
import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

import app.server.session_model as _model_mod
from app.server.session_model import BuildSession


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_bs(status: str) -> BuildSession:
    """Return a BuildSession with the given status and a stable started_at."""
    s = BuildSession(repo_url="https://github.com/org/repo", started_at=time.time())
    s.status = status
    return s


# ── cap-enforcement tests ─────────────────────────────────────────────────────

async def test_cap_enforced_when_three_building():
    """3 sessions with status='building' → create_session raises RuntimeError."""
    original = dict(_model_mod._sessions)
    try:
        _model_mod._sessions.clear()
        for _ in range(3):
            s = _make_bs("building")
            _model_mod._sessions[s.id] = s

        with (
            patch("app.server.sessions.persistence.save_session"),
            patch("app.server.sessions.asyncio.create_task", side_effect=lambda coro: coro.close()),
            patch("app.server.sessions._select_model", return_value="claude-sonnet-4-5"),
        ):
            with pytest.raises(RuntimeError, match="Max sessions reached"):
                from app.server.sessions import create_session
                await create_session("https://github.com/org/repo")
    finally:
        _model_mod._sessions.clear()
        _model_mod._sessions.update(original)


async def test_cap_not_enforced_when_three_complete():
    """3 sessions with status='complete' → create_session spawns the new session."""
    original = dict(_model_mod._sessions)
    try:
        _model_mod._sessions.clear()
        for _ in range(3):
            s = _make_bs("complete")
            _model_mod._sessions[s.id] = s

        with (
            patch("app.server.sessions.persistence.save_session"),
            patch("app.server.sessions.asyncio.create_task", side_effect=lambda coro: coro.close()) as mock_task,
            patch("app.server.sessions._select_model", return_value="claude-sonnet-4-5"),
        ):
            from app.server.sessions import create_session
            session = await create_session("https://github.com/org/new-repo")

        assert session is not None
        mock_task.assert_called_once()
    finally:
        _model_mod._sessions.clear()
        _model_mod._sessions.update(original)


# ── active-status coverage ────────────────────────────────────────────────────

@pytest.mark.parametrize("status", ["created", "cloning", "building", "evaluating"])
async def test_each_active_status_counts_toward_cap(status: str):
    """Each active status ('created'/'cloning'/'building'/'evaluating') counts."""
    original = dict(_model_mod._sessions)
    try:
        _model_mod._sessions.clear()
        for _ in range(3):
            s = _make_bs(status)
            _model_mod._sessions[s.id] = s

        with (
            patch("app.server.sessions.persistence.save_session"),
            patch("app.server.sessions.asyncio.create_task", side_effect=lambda coro: coro.close()),
            patch("app.server.sessions._select_model", return_value="claude-sonnet-4-5"),
        ):
            with pytest.raises(RuntimeError, match="Max sessions reached"):
                from app.server.sessions import create_session
                await create_session("https://github.com/org/repo")
    finally:
        _model_mod._sessions.clear()
        _model_mod._sessions.update(original)


@pytest.mark.parametrize("status", ["complete", "failed", "killed", "interrupted"])
async def test_terminal_statuses_do_not_count_toward_cap(status: str):
    """Terminal statuses never count toward MAX_CONCURRENT_SESSIONS."""
    original = dict(_model_mod._sessions)
    try:
        _model_mod._sessions.clear()
        for _ in range(3):
            s = _make_bs(status)
            _model_mod._sessions[s.id] = s

        with (
            patch("app.server.sessions.persistence.save_session"),
            patch("app.server.sessions.asyncio.create_task", side_effect=lambda coro: coro.close()) as mock_task,
            patch("app.server.sessions._select_model", return_value="claude-sonnet-4-5"),
        ):
            from app.server.sessions import create_session
            session = await create_session("https://github.com/org/repo")

        assert session is not None
        mock_task.assert_called_once()
    finally:
        _model_mod._sessions.clear()
        _model_mod._sessions.update(original)


# ── boundary test ─────────────────────────────────────────────────────────────

async def test_cap_at_exact_boundary():
    """2 active sessions → allowed; add a 3rd (the new one) → now at limit, next raises."""
    original = dict(_model_mod._sessions)
    try:
        _model_mod._sessions.clear()
        for _ in range(2):
            s = _make_bs("building")
            _model_mod._sessions[s.id] = s

        with (
            patch("app.server.sessions.persistence.save_session"),
            patch("app.server.sessions.asyncio.create_task", side_effect=lambda coro: coro.close()),
            patch("app.server.sessions._select_model", return_value="claude-sonnet-4-5"),
        ):
            from app.server.sessions import create_session
            # 2 active → should succeed (creates the 3rd slot)
            session = await create_session("https://github.com/org/repo")
            assert session is not None

            # Now 3 active (including the session we just created which is "created") → must block
            with pytest.raises(RuntimeError, match="Max sessions reached"):
                await create_session("https://github.com/org/repo")
    finally:
        _model_mod._sessions.clear()
        _model_mod._sessions.update(original)
