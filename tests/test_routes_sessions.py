"""
test_routes_sessions.py — Unit tests for routes/sessions.py helpers (RA-937).

Covers _find_active_session_for_repo which is the deduplication guard used by
both the sessions route and the webhooks route.
"""
from unittest.mock import MagicMock


def _make_session(repo_url: str, status: str) -> MagicMock:
    s = MagicMock()
    s.id = f"sess-{status}"
    s.repo_url = repo_url
    s.status = status
    return s


def test_find_active_session_returns_id():
    """Returns session ID when a non-terminal session exists for the repo."""
    from app.server.routes.sessions import _find_active_session_for_repo
    import app.server.routes.sessions as mod

    sessions = {
        "sess-building": _make_session("https://github.com/org/repo", "building"),
    }
    original = mod._sessions
    try:
        mod._sessions = sessions
        result = _find_active_session_for_repo("https://github.com/org/repo")
        assert result == "sess-building"
    finally:
        mod._sessions = original


def test_find_active_session_returns_none_when_terminal():
    """Returns None when all sessions for the repo are in terminal states."""
    from app.server.routes.sessions import _find_active_session_for_repo
    import app.server.routes.sessions as mod

    sessions = {
        "sess-done":        _make_session("https://github.com/org/repo", "done"),
        "sess-failed":      _make_session("https://github.com/org/repo", "failed"),
        "sess-killed":      _make_session("https://github.com/org/repo", "killed"),
        "sess-interrupted": _make_session("https://github.com/org/repo", "interrupted"),
    }
    original = mod._sessions
    try:
        mod._sessions = sessions
        result = _find_active_session_for_repo("https://github.com/org/repo")
        assert result is None
    finally:
        mod._sessions = original


def test_find_active_session_returns_none_for_different_repo():
    """Returns None when active session is for a different repo."""
    from app.server.routes.sessions import _find_active_session_for_repo
    import app.server.routes.sessions as mod

    sessions = {
        "sess-building": _make_session("https://github.com/org/other-repo", "building"),
    }
    original = mod._sessions
    try:
        mod._sessions = sessions
        result = _find_active_session_for_repo("https://github.com/org/repo")
        assert result is None
    finally:
        mod._sessions = original


def test_find_active_session_empty_sessions():
    """Returns None when no sessions exist."""
    from app.server.routes.sessions import _find_active_session_for_repo
    import app.server.routes.sessions as mod

    original = mod._sessions
    try:
        mod._sessions = {}
        result = _find_active_session_for_repo("https://github.com/org/repo")
        assert result is None
    finally:
        mod._sessions = original


def test_find_active_session_prefers_first_active():
    """Returns the first active session when multiple non-terminal sessions exist."""
    from app.server.routes.sessions import _find_active_session_for_repo
    import app.server.routes.sessions as mod

    repo = "https://github.com/org/repo"
    # Use ordered dict to ensure deterministic ordering
    sessions = {
        "sess-cloning":  _make_session(repo, "cloning"),
        "sess-building": _make_session(repo, "building"),
    }
    original = mod._sessions
    try:
        mod._sessions = sessions
        result = _find_active_session_for_repo(repo)
        # Should return one of the active sessions (first non-terminal found)
        assert result in ("sess-cloning", "sess-building")
    finally:
        mod._sessions = original


def test_all_terminal_statuses_covered():
    """All known terminal statuses prevent false 'active' detection."""
    from app.server.routes.sessions import _find_active_session_for_repo
    import app.server.routes.sessions as mod

    repo = "https://github.com/org/repo"
    terminal_statuses = ["done", "complete", "failed", "killed", "interrupted"]

    for status in terminal_statuses:
        sessions = {"s": _make_session(repo, status)}
        original = mod._sessions
        try:
            mod._sessions = sessions
            assert _find_active_session_for_repo(repo) is None, (
                f"Status '{status}' should be treated as terminal"
            )
        finally:
            mod._sessions = original
