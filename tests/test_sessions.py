"""
test_sessions.py — Unit and route tests for routes/sessions.py and session
lifecycle (RA-1432).

Covers:
- POST /api/build: happy path, 429 cap, evaluator flag forwarding (2 variants)
- POST /api/build/parallel: fan-out result, empty-brief 400, worker cap
- GET /api/sessions: list + empty list
- POST /api/sessions/{sid}/kill: ok + 404
- GET /api/sessions/{sid}/logs: 404, after-param clamping (neg + overflow), terminal signal
- POST /api/sessions/{sid}/resume: success, status-to-building, 404, wrong-status 400,
  no-checkpoint 400
- kill_session: returns False (no process / unknown sid), writes disk on success
- restore_sessions: marks in-flight interrupted, preserves terminal, skips already-loaded
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── Test app fixture (bypasses real auth) ─────────────────────────────────────

def _make_app():
    from app.server.routes.sessions import router
    from app.server.auth import require_auth, require_rate_limit

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_auth] = lambda: None
    app.dependency_overrides[require_rate_limit] = lambda: None
    return app


@pytest.fixture()
def client():
    return TestClient(_make_app(), raise_server_exceptions=True)


# ── Session stub ──────────────────────────────────────────────────────────────

def _stub_session(sid="abc123", status="building", last_phase="phase-2"):
    s = MagicMock()
    s.id = sid
    s.repo_url = "https://github.com/org/repo"
    s.status = status
    s.output_lines = []
    s.last_completed_phase = last_phase
    s.process = None
    return s


# ── POST /api/build ───────────────────────────────────────────────────────────

def test_build_happy_path(client):
    """Returns session_id and status when create_session succeeds."""
    mock_session = _stub_session("new-sess-id", "created")
    with patch("app.server.routes.sessions.create_session", new=AsyncMock(return_value=mock_session)):
        r = client.post("/api/build", json={"repo_url": "https://github.com/org/repo"})
    assert r.status_code == 200
    assert r.json()["session_id"] == "new-sess-id"
    assert r.json()["status"] == "created"


def test_build_429_when_session_cap_reached(client):
    """Returns 429 when create_session raises RuntimeError (concurrent cap)."""
    with patch(
        "app.server.routes.sessions.create_session",
        new=AsyncMock(side_effect=RuntimeError("Max sessions reached")),
    ):
        r = client.post("/api/build", json={"repo_url": "https://github.com/org/repo"})
    assert r.status_code == 429


def test_build_evaluator_flag_true_forwarded(client):
    """evaluator_enabled=True in the request body is forwarded to create_session."""
    mock_session = _stub_session()
    captured: dict = {}

    async def _fake_create(repo_url, brief="", model="", evaluator_enabled=True, **kw):
        captured["evaluator_enabled"] = evaluator_enabled
        return mock_session

    with patch("app.server.routes.sessions.create_session", new=_fake_create):
        client.post(
            "/api/build",
            json={"repo_url": "https://github.com/org/repo", "evaluator_enabled": True},
        )
    assert captured["evaluator_enabled"] is True


def test_build_evaluator_flag_false_forwarded(client):
    """evaluator_enabled=False in the request body is forwarded to create_session."""
    mock_session = _stub_session()
    captured: dict = {}

    async def _fake_create(repo_url, brief="", model="", evaluator_enabled=True, **kw):
        captured["evaluator_enabled"] = evaluator_enabled
        return mock_session

    with patch("app.server.routes.sessions.create_session", new=_fake_create):
        client.post(
            "/api/build",
            json={"repo_url": "https://github.com/org/repo", "evaluator_enabled": False},
        )
    assert captured["evaluator_enabled"] is False


# ── POST /api/build/parallel ──────────────────────────────────────────────────

def test_build_parallel_fan_out_result(client):
    """Returns fan_out result on successful parallel build."""
    expected = {"workers": [{"id": "w1", "status": "created"}, {"id": "w2", "status": "created"}]}
    with patch("app.server.routes.sessions.fan_out", new=AsyncMock(return_value=expected)):
        r = client.post(
            "/api/build/parallel",
            json={
                "repo_url": "https://github.com/org/repo",
                "brief": "add tests",
                "n_workers": 2,
            },
        )
    assert r.status_code == 200
    assert r.json() == expected


def test_build_parallel_empty_brief_400(client):
    """Returns 400 when brief is empty string."""
    with patch("app.server.routes.sessions.fan_out", new=AsyncMock(return_value={})):
        r = client.post(
            "/api/build/parallel",
            json={"repo_url": "https://github.com/org/repo", "brief": "", "n_workers": 2},
        )
    assert r.status_code == 400


def test_build_parallel_worker_cap_applied(client):
    """Server-side min(n_workers, 10) cap is enforced regardless of model validation."""
    captured: dict = {}

    async def _fake_fan_out(repo_url, brief, n_workers=2, **kw):
        captured["n_workers"] = n_workers
        return {}

    with patch("app.server.routes.sessions.fan_out", new=_fake_fan_out):
        client.post(
            "/api/build/parallel",
            json={"repo_url": "https://github.com/org/repo", "brief": "work", "n_workers": 10},
        )
    assert captured["n_workers"] <= 10


# ── GET /api/sessions ─────────────────────────────────────────────────────────

def test_get_sessions_returns_list(client):
    """Returns the list produced by list_sessions()."""
    sessions_data = [{"id": "s1", "repo": "https://github.com/org/repo", "status": "building"}]
    with patch("app.server.routes.sessions.list_sessions", return_value=sessions_data):
        r = client.get("/api/sessions")
    assert r.status_code == 200
    assert r.json() == sessions_data


def test_get_sessions_empty_list(client):
    """Returns empty list when no sessions exist."""
    with patch("app.server.routes.sessions.list_sessions", return_value=[]):
        r = client.get("/api/sessions")
    assert r.status_code == 200
    assert r.json() == []


# ── POST /api/sessions/{sid}/kill ─────────────────────────────────────────────

def test_kill_session_ok(client):
    """Returns 200 {"ok": true} when kill_session returns True."""
    with patch("app.server.routes.sessions.kill_session", new=AsyncMock(return_value=True)):
        r = client.post("/api/sessions/abc123/kill")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_kill_session_404(client):
    """Returns 404 when kill_session returns False (unknown or unkillable)."""
    with patch("app.server.routes.sessions.kill_session", new=AsyncMock(return_value=False)):
        r = client.post("/api/sessions/unknown-sid/kill")
    assert r.status_code == 404


# ── GET /api/sessions/{sid}/logs ─────────────────────────────────────────────

def test_logs_404_for_unknown_session(client):
    """Returns 404 when the session does not exist."""
    with patch("app.server.routes.sessions.get_session", return_value=None):
        r = client.get("/api/sessions/does-not-exist/logs")
    assert r.status_code == 404


def test_logs_negative_after_clamped_to_zero(client):
    """Negative after param is clamped to 0 — no 422 or 500 response."""
    session = _stub_session("sess1", "done")
    with patch("app.server.routes.sessions.get_session", return_value=session):
        r = client.get("/api/sessions/sess1/logs?after=-99")
    assert r.status_code == 200


def test_logs_overflow_after_clamped_to_max(client):
    """after param beyond 100_000 is clamped — no error, endpoint responds normally."""
    session = _stub_session("sess1", "done")
    with patch("app.server.routes.sessions.get_session", return_value=session):
        r = client.get("/api/sessions/sess1/logs?after=9999999")
    assert r.status_code == 200


def test_logs_terminal_session_emits_done_event(client):
    """A session already in 'done' state streams a terminal 'done' event."""
    session = _stub_session("sess1", "done")
    with patch("app.server.routes.sessions.get_session", return_value=session):
        r = client.get("/api/sessions/sess1/logs")
    assert r.status_code == 200
    assert "done" in r.text


# ── POST /api/sessions/{sid}/resume ──────────────────────────────────────────

def test_resume_404_for_unknown_session(client):
    """Returns 404 when the session does not exist."""
    with patch("app.server.routes.sessions.get_session", return_value=None):
        r = client.post("/api/sessions/unknown/resume")
    assert r.status_code == 404


def test_resume_400_when_status_not_interrupted(client):
    """Returns 400 when session is not in 'interrupted' status."""
    session = _stub_session("sess1", "building", last_phase="phase-2")
    with patch("app.server.routes.sessions.get_session", return_value=session):
        r = client.post("/api/sessions/sess1/resume")
    assert r.status_code == 400
    assert "interrupted" in r.json()["detail"]


def test_resume_400_when_no_phase_checkpoint(client):
    """Returns 400 when session has no last_completed_phase (cannot resume)."""
    session = _stub_session("sess1", "interrupted", last_phase="")
    with patch("app.server.routes.sessions.get_session", return_value=session):
        r = client.post("/api/sessions/sess1/resume")
    assert r.status_code == 400
    detail = r.json()["detail"].lower()
    assert "checkpoint" in detail or "resume" in detail


def test_resume_success_transitions_to_building(client):
    """Successful resume sets status='building' and returns session_id + resumed_from."""
    session = _stub_session("sess1", "interrupted", last_phase="phase-generate")

    with (
        patch("app.server.routes.sessions.get_session", return_value=session),
        patch("app.server.routes.sessions.persistence"),
        patch("app.server.routes.sessions.run_build", new=AsyncMock()),
    ):
        r = client.post("/api/sessions/sess1/resume")

    assert r.status_code == 200
    assert session.status == "building"
    body = r.json()
    assert body["session_id"] == "sess1"
    assert body["resumed_from"] == "phase-generate"


# ── kill_session: direct lifecycle tests ─────────────────────────────────────

async def test_kill_session_returns_false_for_unknown_sid():
    """kill_session returns False immediately when session ID is not in store."""
    from app.server.session_model import _sessions as store
    from app.server.sessions import kill_session

    saved = dict(store)
    store.clear()
    try:
        result = await kill_session("nonexistent-sid")
        assert result is False
    finally:
        store.clear()
        store.update(saved)


async def test_kill_session_returns_false_when_no_process():
    """kill_session returns False when the session has no running process (None)."""
    from app.server.session_model import BuildSession, _sessions as store
    from app.server.sessions import kill_session

    s = BuildSession(id="no-proc-id", repo_url="https://github.com/org/repo")
    assert s.process is None

    saved = dict(store)
    store["no-proc-id"] = s
    try:
        result = await kill_session("no-proc-id")
        assert result is False
    finally:
        store.pop("no-proc-id", None)
        store.update(saved)


async def test_kill_session_terminates_process_writes_disk():
    """kill_session terminates the process, sets status='killed', saves to disk."""
    from app.server.session_model import BuildSession, _sessions as store
    from app.server.sessions import kill_session

    mock_proc = MagicMock()
    mock_proc.returncode = None
    mock_proc.terminate = MagicMock()
    mock_proc.kill = MagicMock()

    s = BuildSession(id="kill-disk-id", repo_url="https://github.com/org/repo")
    s.process = mock_proc

    saved = dict(store)
    store["kill-disk-id"] = s
    try:
        with (
            patch("app.server.sessions.persistence") as mock_persistence,
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            result = await kill_session("kill-disk-id")

        assert result is True
        assert s.status == "killed"
        mock_persistence.save_session.assert_called_once_with(s)
    finally:
        store.pop("kill-disk-id", None)
        store.update(saved)


# ── restore_sessions: disk-to-memory reconciliation ──────────────────────────

def test_restore_marks_inflight_sessions_as_interrupted():
    """Sessions with 'building' status are marked 'interrupted' on restore."""
    from app.server.session_model import _sessions as store, restore_sessions

    saved = dict(store)
    store.clear()
    try:
        with patch("app.server.session_model.persistence") as mock_persistence:
            mock_persistence.load_all_sessions.return_value = [
                {
                    "id": "in-flight-1",
                    "repo_url": "https://github.com/org/repo",
                    "workspace": "",
                    "started_at": 0.0,
                    "status": "building",
                    "error": None,
                    "last_completed_phase": "",
                    "retry_count": 0,
                    "linear_issue_id": None,
                },
            ]
            restore_sessions()
        assert store["in-flight-1"].status == "interrupted"
    finally:
        store.clear()
        store.update(saved)


def test_restore_preserves_terminal_session_status():
    """Sessions in terminal states (done/failed) are loaded unchanged."""
    from app.server.session_model import _sessions as store, restore_sessions

    saved = dict(store)
    store.clear()
    try:
        with patch("app.server.session_model.persistence") as mock_persistence:
            mock_persistence.load_all_sessions.return_value = [
                {
                    "id": "done-sess",
                    "repo_url": "https://github.com/org/repo",
                    "workspace": "",
                    "started_at": 0.0,
                    "status": "done",
                    "error": None,
                    "last_completed_phase": "phase-evaluate",
                    "retry_count": 0,
                    "linear_issue_id": None,
                },
            ]
            restore_sessions()
        assert store["done-sess"].status == "done"
    finally:
        store.clear()
        store.update(saved)


def test_restore_skips_sessions_already_in_memory():
    """Sessions already in _sessions are not overwritten by restore."""
    from app.server.session_model import BuildSession, _sessions as store, restore_sessions

    saved = dict(store)
    existing = BuildSession(
        id="already-loaded",
        repo_url="https://github.com/org/repo",
        status="building",
    )
    store.clear()
    store["already-loaded"] = existing
    try:
        with patch("app.server.session_model.persistence") as mock_persistence:
            mock_persistence.load_all_sessions.return_value = [
                {
                    "id": "already-loaded",
                    "repo_url": "https://github.com/org/repo",
                    "workspace": "",
                    "started_at": 0.0,
                    "status": "done",
                    "error": None,
                    "last_completed_phase": "",
                    "retry_count": 0,
                    "linear_issue_id": None,
                },
            ]
            restore_sessions()
        # Must NOT be overwritten with the on-disk "done" status
        assert store["already-loaded"].status == "building"
    finally:
        store.clear()
        store.update(saved)
