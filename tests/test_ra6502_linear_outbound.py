"""
test_ra6502_linear_outbound.py — Unit tests for RA-6502: Linear outbound sync.

Verifies:
  1. Feature flag (LINEAR_OUTBOUND_SYNC=0) makes all outbound calls no-ops.
  2. _notify_linear_session_started: moves issue to "In Progress" on session start.
  3. State-transition mapping — complete → comment (no state); failed → comment + Todo.
  4. Failure tolerance: Linear 500 / network error → logged, pipeline continues.
  5. Flag-off no-op: flag disabled means ZERO HTTP calls from any outbound helper.

These tests mock urllib.request.urlopen — no real HTTP is made.
"""
from __future__ import annotations

import io
import json
import os
import urllib.error
from unittest.mock import MagicMock, patch, call

import pytest


# ── helpers ────────────────────────────────────────────────────────────────────


def _make_session(
    *,
    issue_id: str | None = "issue-ra6502",
    status: str = "complete",
    score: float | None = 8.0,
    eval_status: str = "passed",
    session_id: str = "sess-ra6502",
    started_at: float = 0.0,
    autonomy_triggered: bool = False,
) -> MagicMock:
    s = MagicMock()
    s.linear_issue_id = issue_id
    s.status = status
    s.evaluator_score = score
    s.evaluator_status = eval_status
    s.id = session_id
    s.started_at = started_at
    s.autonomy_triggered = autonomy_triggered
    return s


def _fake_urlopen(responses: list[dict]):
    """Return a side_effect that yields successive JSON responses."""

    class _FakeResp:
        def __init__(self, data: dict):
            self._data = json.dumps(data).encode()

        def read(self):
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    calls: list[dict] = []
    it = iter(responses)

    def _side(req, timeout=15):  # noqa: ARG001
        calls.append({"url": req.get_full_url(), "body": json.loads(req.data)})
        return _FakeResp(next(it))

    _side.calls = calls  # type: ignore[attr-defined]
    return _side


# ── 1. Feature flag: LINEAR_OUTBOUND_SYNC=0 → zero HTTP calls ─────────────────


def test_flag_off_update_state_is_noop(monkeypatch):
    """_update_linear_state makes no HTTP calls when flag is off."""
    monkeypatch.setenv("LINEAR_OUTBOUND_SYNC", "0")
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key")

    # Reload to pick up patched env (module caches nothing — _outbound_enabled re-reads)
    import importlib
    import app.server.session_linear as sl
    importlib.reload(sl)

    with patch("urllib.request.urlopen") as mock_http:
        sl._update_linear_state("issue-abc", "In Progress")
        mock_http.assert_not_called()


def test_flag_off_post_comment_is_noop(monkeypatch):
    """_post_linear_comment makes no HTTP calls when flag is off."""
    monkeypatch.setenv("LINEAR_OUTBOUND_SYNC", "0")
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key")

    import importlib
    import app.server.session_linear as sl
    importlib.reload(sl)

    with patch("urllib.request.urlopen") as mock_http:
        sl._post_linear_comment("issue-abc", "Build done")
        mock_http.assert_not_called()


def test_flag_off_notify_started_is_noop(monkeypatch):
    """_notify_linear_session_started makes no HTTP calls when flag is off."""
    monkeypatch.setenv("LINEAR_OUTBOUND_SYNC", "0")
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key")

    import importlib
    import app.server.session_linear as sl
    importlib.reload(sl)

    session = _make_session()
    with patch("urllib.request.urlopen") as mock_http:
        sl._notify_linear_session_started(session)
        mock_http.assert_not_called()


def test_flag_off_sync_on_completion_is_noop(monkeypatch):
    """_sync_linear_on_completion makes no HTTP calls when flag is off."""
    monkeypatch.setenv("LINEAR_OUTBOUND_SYNC", "0")
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key")

    import importlib
    import app.server.session_linear as sl
    importlib.reload(sl)

    session = _make_session(status="complete")
    with patch("urllib.request.urlopen") as mock_http:
        with patch.object(sl, "_send_autonomy_outcome_telegram"):
            sl._sync_linear_on_completion(session)
        mock_http.assert_not_called()


# ── 2. _notify_linear_session_started ─────────────────────────────────────────


def test_notify_started_moves_issue_to_in_progress(monkeypatch):
    """On session start, the originating Linear issue is moved to 'In Progress'."""
    monkeypatch.setenv("LINEAR_OUTBOUND_SYNC", "1")
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key")

    import importlib
    import app.server.session_linear as sl
    importlib.reload(sl)

    called_states: list[str] = []

    def _capture(issue_id, state):
        called_states.append(state)

    session = _make_session(issue_id="issue-start-test")
    with patch.object(sl, "_update_linear_state", side_effect=_capture):
        sl._notify_linear_session_started(session)

    assert called_states == ["In Progress"]


def test_notify_started_skips_when_no_issue_id(monkeypatch):
    """No HTTP calls when session has no linear_issue_id."""
    monkeypatch.setenv("LINEAR_OUTBOUND_SYNC", "1")
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key")

    import importlib
    import app.server.session_linear as sl
    importlib.reload(sl)

    session = _make_session(issue_id=None)
    with patch.object(sl, "_update_linear_state") as mock_update:
        sl._notify_linear_session_started(session)
        mock_update.assert_not_called()


def test_notify_started_tolerates_linear_error(monkeypatch):
    """Linear HTTP 500 on session start does not propagate — pipeline continues."""
    monkeypatch.setenv("LINEAR_OUTBOUND_SYNC", "1")
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key")

    import importlib
    import app.server.session_linear as sl
    importlib.reload(sl)

    def _raise_500(issue_id, state):
        raise urllib.error.HTTPError(
            url="https://api.linear.app/graphql",
            code=500,
            msg="Internal Server Error",
            hdrs={},  # type: ignore[arg-type]
            fp=io.BytesIO(b"Server Error"),
        )

    session = _make_session(issue_id="issue-500")
    with patch.object(sl, "_update_linear_state", side_effect=_raise_500):
        # Must not raise — fire-and-forget
        sl._notify_linear_session_started(session)


# ── 3. State-transition mapping ───────────────────────────────────────────────


def test_state_mapping_complete_posts_comment_no_state_change(monkeypatch):
    """Complete session posts a comment but does NOT change state (stays In Review)."""
    monkeypatch.setenv("LINEAR_OUTBOUND_SYNC", "1")
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key")

    import importlib
    import app.server.session_linear as sl
    importlib.reload(sl)

    session = _make_session(status="complete", issue_id="issue-done", score=9.1, eval_status="passed")
    posted: list[str] = []
    updated: list[str] = []

    with patch.object(sl, "_post_linear_comment", side_effect=lambda i, b: posted.append(b)):
        with patch.object(sl, "_update_linear_state", side_effect=lambda i, s: updated.append(s)):
            with patch.object(sl, "_send_autonomy_outcome_telegram"):
                sl._sync_linear_on_completion(session)

    assert len(posted) == 1, "Expected exactly one comment"
    assert "complete" in posted[0].lower()
    assert updated == [], "Complete should not change state (already In Review after push)"


def test_state_mapping_failed_posts_comment_and_resets_to_todo(monkeypatch):
    """Failed session posts a comment AND moves issue back to Todo."""
    monkeypatch.setenv("LINEAR_OUTBOUND_SYNC", "1")
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key")

    import importlib
    import app.server.session_linear as sl
    importlib.reload(sl)

    session = _make_session(status="failed", issue_id="issue-fail", score=None)
    posted: list[str] = []
    updated: list[str] = []

    with patch.object(sl, "_post_linear_comment", side_effect=lambda i, b: posted.append(b)):
        with patch.object(sl, "_update_linear_state", side_effect=lambda i, s: updated.append(s)):
            with patch.object(sl, "_send_autonomy_outcome_telegram"):
                sl._sync_linear_on_completion(session)

    assert len(posted) == 1
    assert "failed" in posted[0].lower()
    assert updated == ["Todo"], "Failed build must reset issue to Todo"


def test_state_mapping_killed_no_linear_update(monkeypatch):
    """Killed/interrupted sessions do not post anything to Linear."""
    monkeypatch.setenv("LINEAR_OUTBOUND_SYNC", "1")
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key")

    import importlib
    import app.server.session_linear as sl
    importlib.reload(sl)

    session = _make_session(status="killed", issue_id="issue-kill")
    with patch.object(sl, "_post_linear_comment") as mock_comment:
        with patch.object(sl, "_update_linear_state") as mock_update:
            with patch.object(sl, "_send_autonomy_outcome_telegram"):
                sl._sync_linear_on_completion(session)
    mock_comment.assert_not_called()
    mock_update.assert_not_called()


# ── 4. Full GraphQL sequence when flag is ON ───────────────────────────────────


def test_update_state_full_graphql_sequence_when_flag_on(monkeypatch):
    """When flag=1, _update_linear_state sends all three GraphQL requests."""
    monkeypatch.setenv("LINEAR_OUTBOUND_SYNC", "1")
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key")

    import importlib
    import app.server.session_linear as sl
    importlib.reload(sl)

    responses = [
        {"data": {"issue": {"team": {"id": "team-ra6502"}}}},
        {"data": {"team": {"states": {"nodes": [
            {"id": "state-ip", "name": "In Progress", "type": "started"},
            {"id": "state-todo", "name": "Todo", "type": "unstarted"},
        ]}}}},
        {"data": {"issueUpdate": {"success": True, "issue": {
            "id": "issue-ra6502", "title": "Test", "state": {"name": "In Progress"},
        }}}},
    ]
    side_effect = _fake_urlopen(responses)
    with patch("urllib.request.urlopen", side_effect=side_effect):
        sl._update_linear_state("issue-ra6502", "In Progress")

    assert len(side_effect.calls) == 3
    mutation_vars = side_effect.calls[2]["body"]["variables"]
    assert mutation_vars["stateId"] == "state-ip"
    assert mutation_vars["id"] == "issue-ra6502"


# ── 5. Failure tolerance with flag ON ─────────────────────────────────────────


def test_linear_500_on_comment_is_logged_not_raised(monkeypatch):
    """HTTP 500 from Linear during commentCreate is logged, not re-raised."""
    monkeypatch.setenv("LINEAR_OUTBOUND_SYNC", "1")
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key")

    import importlib
    import app.server.session_linear as sl
    importlib.reload(sl)

    def _raise_500(req, timeout=15):  # noqa: ARG001
        raise urllib.error.HTTPError(
            url="https://api.linear.app/graphql",
            code=500,
            msg="Internal Server Error",
            hdrs={},  # type: ignore[arg-type]
            fp=io.BytesIO(b"error"),
        )

    with patch("urllib.request.urlopen", side_effect=_raise_500):
        # Must not raise — failure tolerance is core requirement
        sl._post_linear_comment("issue-abc", "Build done")


def test_network_error_on_update_state_is_swallowed(monkeypatch):
    """Generic network error on _update_linear_state is swallowed."""
    monkeypatch.setenv("LINEAR_OUTBOUND_SYNC", "1")
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key")

    import importlib
    import app.server.session_linear as sl
    importlib.reload(sl)

    with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        sl._update_linear_state("issue-abc", "In Progress")  # must not raise
