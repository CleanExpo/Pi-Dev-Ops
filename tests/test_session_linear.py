"""
test_session_linear.py — Unit tests for session_linear.py (RA-1430).

Verifies the Linear two-way sync that the gap audit claimed was absent.
The audit inspected webhook.py only; the outbound sync lives in session_linear.py.
These tests prove the sync exists and behaves correctly under each terminal state.

Coverage:
  - _update_linear_state: no-op when LINEAR_API_KEY unset, GraphQL sequence,
    HTTP error swallowed, state-not-found gracefully logged
  - _post_linear_comment: no-op when no key, mutation sent, error swallowed
  - _sync_linear_on_completion: comment + state update on complete/failed,
    skipped when no linear_issue_id
  - _record_session_outcome: correct JSONL row written to disk
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import urllib.error
from unittest.mock import MagicMock, patch

import pytest


# ── helpers ────────────────────────────────────────────────────────────────────


def _fake_urlopen(responses: list[dict]):
    """Return a side_effect that yields successive JSON responses via urlopen."""
    calls: list[dict] = []

    class _FakeResp:
        def __init__(self, data: dict):
            self._data = data.encode("utf-8") if isinstance(data, str) else json.dumps(data).encode()

        def read(self):
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    it = iter(responses)

    def _side_effect(req, timeout=15):  # noqa: ARG001
        calls.append({"url": req.get_full_url(), "data": json.loads(req.data)})
        return _FakeResp(next(it))

    _side_effect.calls = calls  # type: ignore[attr-defined]
    return _side_effect


# ── _update_linear_state ───────────────────────────────────────────────────────


def test_update_linear_state_no_op_when_no_key(monkeypatch):
    """Skips all HTTP when LINEAR_API_KEY is unset."""
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    from app.server.session_linear import _update_linear_state

    with patch("urllib.request.urlopen") as mock_urlopen:
        _update_linear_state("issue-123", "In Review")
        mock_urlopen.assert_not_called()


def test_update_linear_state_sends_graphql_sequence(monkeypatch):
    """Three GraphQL requests are made in the correct order on success."""
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key")
    from app.server.session_linear import _update_linear_state

    responses = [
        # Step 1: fetch team ID
        {"data": {"issue": {"team": {"id": "team-abc"}}}},
        # Step 2: fetch workflow states
        {"data": {"team": {"states": {"nodes": [
            {"id": "state-001", "name": "In Review", "type": "started"},
            {"id": "state-002", "name": "Todo", "type": "unstarted"},
        ]}}}},
        # Step 3: issueUpdate mutation
        {"data": {"issueUpdate": {"success": True, "issue": {"id": "issue-123", "title": "Fix bug", "state": {"name": "In Review"}}}}},
    ]

    side_effect = _fake_urlopen(responses)
    with patch("urllib.request.urlopen", side_effect=side_effect):
        _update_linear_state("issue-123", "In Review")

    assert len(side_effect.calls) == 3
    # Third call should be the mutation with the correct stateId
    mutation_call = side_effect.calls[2]
    assert mutation_call["data"]["variables"]["stateId"] == "state-001"
    assert mutation_call["data"]["variables"]["id"] == "issue-123"


def test_update_linear_state_swallows_http_error(monkeypatch):
    """HTTPError from Linear API does not propagate — function returns silently."""
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key")
    from app.server.session_linear import _update_linear_state

    def _raise(*args, **kwargs):
        raise urllib.error.HTTPError(
            url="https://api.linear.app/graphql",
            code=401,
            msg="Unauthorized",
            hdrs={},  # type: ignore[arg-type]
            fp=io.BytesIO(b"Unauthorized"),
        )

    with patch("urllib.request.urlopen", side_effect=_raise):
        # Must not raise
        _update_linear_state("issue-123", "In Review")


def test_update_linear_state_skips_when_state_not_found(monkeypatch):
    """Logs warning and returns when state name has no match in team's workflow."""
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key")
    from app.server.session_linear import _update_linear_state

    responses = [
        {"data": {"issue": {"team": {"id": "team-abc"}}}},
        {"data": {"team": {"states": {"nodes": [
            {"id": "state-001", "name": "Todo", "type": "unstarted"},
        ]}}}},
        # No third call should happen
    ]

    side_effect = _fake_urlopen(responses)
    with patch("urllib.request.urlopen", side_effect=side_effect):
        _update_linear_state("issue-123", "NonExistentState")

    # Only 2 requests made — mutation skipped because state wasn't found
    assert len(side_effect.calls) == 2


# ── _post_linear_comment ───────────────────────────────────────────────────────


def test_post_linear_comment_no_op_when_no_key(monkeypatch):
    """Skips HTTP when LINEAR_API_KEY is unset."""
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    from app.server.session_linear import _post_linear_comment

    with patch("urllib.request.urlopen") as mock_urlopen:
        _post_linear_comment("issue-123", "Build complete")
        mock_urlopen.assert_not_called()


def test_post_linear_comment_sends_mutation(monkeypatch):
    """Posts commentCreate mutation with correct issueId and body."""
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key")
    from app.server.session_linear import _post_linear_comment

    responses = [{"data": {"commentCreate": {"success": True}}}]
    side_effect = _fake_urlopen(responses)

    with patch("urllib.request.urlopen", side_effect=side_effect):
        _post_linear_comment("issue-123", "Build complete in 42s.")

    assert len(side_effect.calls) == 1
    variables = side_effect.calls[0]["data"]["variables"]
    assert variables["issueId"] == "issue-123"
    assert "Build complete" in variables["body"]


def test_post_linear_comment_swallows_error(monkeypatch):
    """Network error during comment post does not propagate."""
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key")
    from app.server.session_linear import _post_linear_comment

    with patch("urllib.request.urlopen", side_effect=OSError("network down")):
        _post_linear_comment("issue-123", "text")  # must not raise


# ── _sync_linear_on_completion ─────────────────────────────────────────────────


def test_sync_linear_skips_when_no_issue_id():
    """No HTTP calls when session.linear_issue_id is None."""
    from app.server.session_linear import _sync_linear_on_completion

    session = MagicMock()
    session.status = "complete"
    session.linear_issue_id = None
    session.autonomy_triggered = False
    session.started_at = 0.0

    with patch("urllib.request.urlopen") as mock_urlopen:
        with patch("app.server.session_linear._send_autonomy_outcome_telegram"):
            _sync_linear_on_completion(session)
    mock_urlopen.assert_not_called()


def test_sync_linear_posts_comment_on_complete(monkeypatch):
    """Complete session posts a comment to Linear (no state update — already In Review)."""
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key")
    from app.server.session_linear import _sync_linear_on_completion

    session = MagicMock()
    session.status = "complete"
    session.linear_issue_id = "issue-abc"
    session.evaluator_score = 8.5
    session.evaluator_status = "passed"
    session.id = "sess001"
    session.started_at = 0.0
    session.autonomy_triggered = False

    posted_bodies: list[str] = []

    def _capture_comment(iid, body):
        posted_bodies.append(body)

    with patch("app.server.session_linear._post_linear_comment", side_effect=_capture_comment):
        with patch("app.server.session_linear._update_linear_state") as mock_update:
            with patch("app.server.session_linear._send_autonomy_outcome_telegram"):
                _sync_linear_on_completion(session)

    assert len(posted_bodies) == 1
    assert "complete" in posted_bodies[0].lower()
    assert "sess001" in posted_bodies[0]
    # Complete sessions don't change state (already In Review from push phase)
    mock_update.assert_not_called()


def test_sync_linear_posts_comment_and_resets_state_on_failed(monkeypatch):
    """Failed session posts comment AND moves issue back to Todo."""
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key")
    from app.server.session_linear import _sync_linear_on_completion

    session = MagicMock()
    session.status = "failed"
    session.linear_issue_id = "issue-xyz"
    session.evaluator_score = None
    session.evaluator_status = ""
    session.id = "sess002"
    session.started_at = 0.0
    session.autonomy_triggered = False

    posted_bodies: list[str] = []
    updated_states: list[str] = []

    with patch("app.server.session_linear._post_linear_comment", side_effect=lambda iid, body: posted_bodies.append(body)):
        with patch("app.server.session_linear._update_linear_state", side_effect=lambda iid, state: updated_states.append(state)):
            with patch("app.server.session_linear._send_autonomy_outcome_telegram"):
                _sync_linear_on_completion(session)

    assert len(posted_bodies) == 1
    assert "failed" in posted_bodies[0].lower()
    assert updated_states == ["Todo"]


# ── _record_session_outcome ────────────────────────────────────────────────────


def test_record_session_outcome_writes_jsonl():
    """Outcome JSONL row has all required fields and is valid JSON."""
    import time
    from app.server.session_linear import _record_session_outcome
    from app.server import config

    session = MagicMock()
    session.id = "sess-test"
    session.linear_issue_id = "issue-001"
    session.status = "complete"
    session.evaluator_score = 9.0
    session.started_at = time.time()

    with tempfile.TemporaryDirectory() as tmpdir:
        # _record_session_outcome uses Path(DATA_DIR).parent.parent / ".harness"
        # so DATA_DIR must be two levels deep inside tmpdir for .harness to land
        # under tmpdir (e.g. tmpdir/app/data → tmpdir/.harness)
        fake_data = os.path.join(tmpdir, "app", "data")
        os.makedirs(fake_data)
        with patch.object(config, "DATA_DIR", fake_data):
            push_ts = time.time()
            _record_session_outcome(session, push_ok=True, push_ts=push_ts)

        # Find the written file
        outcomes_path = os.path.join(tmpdir, ".harness", "session-outcomes.jsonl")
        assert os.path.exists(outcomes_path), "session-outcomes.jsonl not created"
        with open(outcomes_path) as f:
            row = json.loads(f.readline())

    assert row["session_id"] == "sess-test"
    assert row["linear_issue_id"] == "issue-001"
    assert row["shipped"] is True
    assert row["push_ok"] is True
    assert row["review_score"] == 9.0
    assert row["linear_state_after"] == "In Review"
    assert "push_timestamp" in row
    assert "checked_at" in row
