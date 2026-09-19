"""Recovered and manually resumed builds retain cancellation ownership."""
import asyncio
from unittest.mock import AsyncMock, Mock
import pytest
from app.server import session_model, sessions, session_phases, supabase_log, orchestrator
from app.server.routes import sessions as routes


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    rows = {}
    for module in (session_model, sessions, orchestrator):
        monkeypatch.setattr(module, "_sessions", rows)
    monkeypatch.setattr(sessions, "_build_tasks", {})
    monkeypatch.setattr(orchestrator, "_fan_out_tasks", {})
    monkeypatch.setattr(sessions.persistence, "save_session", Mock())
    monkeypatch.setattr(supabase_log, "claim_interrupted_session", lambda *args: True)
    monkeypatch.setattr(supabase_log, "fetch_interrupted_sessions", lambda **kw: [
        {"id": "recovered", "checkpoint": {"last_completed_phase": "generator", "workspace": "/old"}}
    ])


@pytest.mark.parametrize("manual", [False, True])
async def test_resumed_build_is_cancelled_before_late_completion(monkeypatch, manual):
    started, stopped = asyncio.Event(), asyncio.Event()
    async def build(session, *, resume_from):
        assert resume_from == "generator"
        started.set()
        try:
            await asyncio.Event().wait()
            session.status = "complete"
        finally:
            stopped.set()
    monkeypatch.setattr(session_phases, "run_build", build)
    monkeypatch.setattr(routes, "run_build", build)
    if manual:
        session = session_model.BuildSession(id="recovered", status="interrupted", last_completed_phase="generator")
        session_model._sessions[session.id] = session
        await routes.resume_session(session.id)
    else:
        assert session_model.recover_interrupted_sessions_from_supabase() == 1
        session = session_model._sessions["recovered"]
    await asyncio.wait_for(started.wait(), 1)
    assert await sessions.kill_session(session.id) is True
    assert stopped.is_set()
    assert session.status == "killed"
    assert session.id not in sessions._build_tasks


async def test_parent_kill_failure_stays_failed(monkeypatch):
    parent = session_model.BuildSession(id="parent", status="orchestrating")
    session_model._sessions[parent.id] = parent
    async def cancel(_sid):
        parent.status = "failed"
        parent.error = "some workers could not be stopped"
        return False
    monkeypatch.setattr(orchestrator, "cancel_fan_out", cancel)
    assert await sessions.kill_session(parent.id) is False
    assert parent.status == "failed"
    assert "could not be stopped" in parent.error


async def test_reclone_uses_owned_guarded_command_and_propagates_cancellation(monkeypatch, tmp_path):
    monkeypatch.setattr(session_phases.config, "WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(session_phases, "git_auth_env", lambda _: {"approved": "header"})
    monkeypatch.setattr(session_phases.asyncio, "create_subprocess_exec", AsyncMock(side_effect=AssertionError("direct git spawn")))
    command = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(session_phases, "run_cmd", command)
    session = session_model.BuildSession(id="reclone", repo_url="https://example.test/repo")
    with pytest.raises(asyncio.CancelledError):
        await session_phases._reclone_sandbox(session)
    assert command.call_args.args[1:3] == ("git", "clone")
    assert command.call_args.kwargs == {"timeout": 60, "env": {"approved": "header"}}


async def test_real_parent_cancellation_reports_unstopped_child(monkeypatch):
    started = asyncio.Event()
    async def run_parent(parent, *args):
        started.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(orchestrator, "_run_fan_out", run_parent)
    receipt = await orchestrator.fan_out("https://example.test/repo", "brief")
    parent = session_model._sessions[receipt["parent_id"]]
    await asyncio.wait_for(started.wait(), 1)
    child = session_model.BuildSession(id="child", status="building", parent_session_id=parent.id)
    session_model._sessions[child.id] = child
    public_kill = sessions.kill_session
    async def kill(sid):
        return False if sid == child.id else await public_kill(sid)
    monkeypatch.setattr(sessions, "kill_session", kill)
    assert await sessions.kill_session(parent.id) is False
    assert parent.status == "failed"
    assert child.status == "building"
    assert "could not be stopped" in parent.error
