"""Parallel launch receipts and terminal lifecycle without external execution."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.server import gc, orchestrator, session_model, sessions
from app.server.models import ParallelBuildRequest
from app.server.routes import sessions as routes
from app.server.session_model import BuildSession


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator.config, "WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(orchestrator.persistence, "save_session", Mock())
    monkeypatch.setattr(orchestrator, "_sessions", {})
    monkeypatch.setattr(session_model, "_sessions", orchestrator._sessions)
    monkeypatch.setattr(sessions, "_sessions", orchestrator._sessions)
    monkeypatch.setattr(orchestrator, "git_auth_env", lambda *args: {})
    monkeypatch.setattr(orchestrator, "run_cmd", AsyncMock(return_value=(0, "", "")))
    monkeypatch.setattr(orchestrator, "_decompose_brief", AsyncMock(return_value=["task"]))
    monkeypatch.setattr(orchestrator, "_launch_wave", AsyncMock(return_value=(["child"], [])))


def test_receipt_returns_before_clone_and_worker_finish(monkeypatch):
    async def scenario():
        clone_started = asyncio.Event()
        allow_clone = asyncio.Event()
        worker_started = asyncio.Event()
        allow_worker = asyncio.Event()

        async def clone(*args, **kwargs):
            clone_started.set()
            await allow_clone.wait()
            return 0, "", ""

        async def wait(*args):
            worker_started.set()
            await allow_worker.wait()
            return True

        monkeypatch.setattr(orchestrator, "run_cmd", clone)
        monkeypatch.setattr(orchestrator, "_wait_for_wave", wait)
        body = ParallelBuildRequest(repo_url="https://github.com/example/repo", brief="build")
        receipt = await asyncio.wait_for(routes.build_parallel(body), timeout=0.1)
        parent = orchestrator._sessions[receipt["parent_id"]]
        task = orchestrator._fan_out_tasks[parent.id]
        try:
            assert receipt["status"] == "launched"
            assert parent.status == "orchestrating"
            await asyncio.wait_for(clone_started.wait(), timeout=0.1)
            assert not task.done()
            allow_clone.set()
            await asyncio.wait_for(worker_started.wait(), timeout=0.1)
            assert parent.status == "orchestrating"
            allow_worker.set()
            await asyncio.wait_for(task, timeout=0.1)
            assert parent.status == "complete"
            orchestrator.persistence.save_session.assert_called_with(parent)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


@pytest.mark.parametrize("status", ["complete", "blocked", "stalled", "failed", "killed", "interrupted", "error"])
def test_background_aggregates_terminal_children(monkeypatch, status):
    monkeypatch.setitem(orchestrator._sessions, "child", SimpleNamespace(status=status))

    async def scenario():
        receipt = await orchestrator.fan_out("https://example.test/repo", "brief")
        task = orchestrator._fan_out_tasks[receipt["parent_id"]]
        await asyncio.wait_for(task, timeout=0.1)
        parent = orchestrator._sessions[receipt["parent_id"]]
        assert parent.status == ("complete" if status == "complete" else "failed")
        orchestrator.persistence.save_session.assert_called_with(parent)

    asyncio.run(scenario())


def test_failed_wave_does_not_launch_dependents(monkeypatch):
    monkeypatch.setattr(orchestrator, "_decompose_brief", AsyncMock(return_value=[
        {"id": 1, "brief": "first", "depends_on": []},
        {"id": 2, "brief": "second", "depends_on": [1]},
    ]))
    monkeypatch.setitem(orchestrator._sessions, "child", SimpleNamespace(status="blocked"))

    async def scenario():
        receipt = await orchestrator.fan_out("https://example.test/repo", "brief")
        await orchestrator._fan_out_tasks[receipt["parent_id"]]
        assert orchestrator._sessions[receipt["parent_id"]].status == "failed"
        orchestrator._launch_wave.assert_awaited_once()

    asyncio.run(scenario())


def test_missing_launch_fails_even_if_started_workers_succeed(monkeypatch):
    monkeypatch.setattr(orchestrator, "_decompose_brief", AsyncMock(return_value=["first", "second"]))
    monkeypatch.setitem(orchestrator._sessions, "child", SimpleNamespace(status="complete"))

    async def scenario():
        receipt = await orchestrator.fan_out("https://example.test/repo", "brief")
        await orchestrator._fan_out_tasks[receipt["parent_id"]]
        assert orchestrator._sessions[receipt["parent_id"]].status == "failed"

    asyncio.run(scenario())


def test_cancellation_persists_interrupted_parent(monkeypatch):
    async def scenario():
        waiting = asyncio.Event()

        async def wait(*args):
            waiting.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(orchestrator, "_wait_for_wave", wait)
        receipt = await orchestrator.fan_out("https://example.test/repo", "brief")
        task = orchestrator._fan_out_tasks[receipt["parent_id"]]
        await asyncio.wait_for(waiting.wait(), timeout=0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        parent = orchestrator._sessions[receipt["parent_id"]]
        assert parent.status == "interrupted"
        orchestrator.persistence.save_session.assert_called_with(parent)
        assert parent.id not in orchestrator._fan_out_tasks

    asyncio.run(scenario())


def test_parent_can_be_killed_before_background_task_starts():
    async def scenario():
        receipt = await orchestrator.fan_out("https://example.test/repo", "brief")
        parent = orchestrator._sessions[receipt["parent_id"]]
        task = orchestrator._fan_out_tasks[parent.id]
        assert await sessions.kill_session(parent.id) is True
        assert task.cancelled()
        assert parent.status == "killed"
        orchestrator.persistence.save_session.assert_called_with(parent)
        orchestrator.run_cmd.assert_not_awaited()
        assert parent.id not in orchestrator._fan_out_tasks

    asyncio.run(scenario())


def _install_waiting_children(monkeypatch, child_started, child_stopped, launched):
    async def build(session, *args, **kwargs):
        launched.append(session)
        session.status = "building"
        child_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            child_stopped.set()

    async def launch(wave, wave_num, **kwargs):
        child = await sessions.create_session(
            "https://example.test/repo", parent_session_id=kwargs["parent_id"]
        )
        return [child.id], []

    monkeypatch.setattr(sessions, "run_build", build)
    monkeypatch.setattr(orchestrator, "_launch_wave", AsyncMock(side_effect=launch))
    monkeypatch.setattr(orchestrator, "_decompose_brief", AsyncMock(return_value=[
        {"id": 1, "brief": "first", "depends_on": []},
        {"id": 2, "brief": "dependent", "depends_on": [1]},
    ]))


@pytest.mark.parametrize("user_kill", [True, False])
def test_parent_cancellation_stops_sdk_children_and_dependent_waves(monkeypatch, user_kill):
    async def scenario():
        child_started = asyncio.Event()
        child_stopped = asyncio.Event()
        launched = []

        _install_waiting_children(monkeypatch, child_started, child_stopped, launched)
        receipt = await orchestrator.fan_out("https://example.test/repo", "brief")
        parent = orchestrator._sessions[receipt["parent_id"]]
        task = orchestrator._fan_out_tasks[parent.id]
        await asyncio.wait_for(child_started.wait(), timeout=1)
        completed = BuildSession(id="completed", status="complete", parent_session_id=parent.id)
        orchestrator._sessions[completed.id] = completed
        if user_kill:
            assert await sessions.kill_session(parent.id) is True
        else:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert child_stopped.is_set()
        assert launched[0].status == "killed"
        assert completed.status == "complete"
        assert parent.status == ("killed" if user_kill else "interrupted")
        orchestrator._launch_wave.assert_awaited_once()
        orchestrator.persistence.save_session.assert_any_call(launched[0])
        orchestrator.persistence.save_session.assert_called_with(parent)

    asyncio.run(scenario())


def test_shutdown_cancellation_persists_child_interruption(monkeypatch):
    async def scenario():
        started = asyncio.Event()

        async def build(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(sessions, "run_build", build)
        child = await sessions.create_session("https://example.test/repo", parent_session_id="parent")
        task = sessions._build_tasks[child.id]
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert child.status == "interrupted"
        sessions.persistence.save_session.assert_called_with(child)
        assert child.id not in sessions._build_tasks

    asyncio.run(scenario())


@pytest.mark.parametrize("clone_result", [(1, "", "clone failed"), RuntimeError("clone failed")])
def test_background_failure_is_persisted(monkeypatch, clone_result):
    clone = AsyncMock(side_effect=clone_result) if isinstance(clone_result, Exception) else AsyncMock(return_value=clone_result)
    monkeypatch.setattr(orchestrator, "run_cmd", clone)

    async def scenario():
        receipt = await orchestrator.fan_out("https://example.test/repo", "brief")
        await orchestrator._fan_out_tasks[receipt["parent_id"]]
        parent = orchestrator._sessions[receipt["parent_id"]]
        assert parent.status == "failed"
        orchestrator.persistence.save_session.assert_called_with(parent)
        orchestrator._launch_wave.assert_not_awaited()

    asyncio.run(scenario())


def test_restart_marks_orchestrating_parent_interrupted(monkeypatch):
    monkeypatch.setattr(session_model.persistence, "load_all_sessions", lambda: [
        {"id": "parent", "status": "orchestrating"},
    ])
    session_model.restore_sessions()
    assert session_model._sessions["parent"].status == "interrupted"
    session_model.persistence.save_session.assert_called_once()


@pytest.mark.parametrize("status", ["blocked", "stalled"])
@pytest.mark.parametrize("endpoint", [routes.stream_session_logs, routes.stream_session_logs_v2])
def test_terminal_stream_closes(monkeypatch, status, endpoint):
    monkeypatch.setattr(routes, "get_session", lambda sid: BuildSession(id=sid, status=status))

    async def scenario():
        response = await endpoint("terminal123")
        async def collect():
            return [chunk async for chunk in response.body_iterator]
        chunks = await asyncio.wait_for(collect(), timeout=0.1)
        events = [json.loads(chunk.removeprefix("data: ")) for chunk in chunks]
        assert events[-1]["type"] == "done"
        if endpoint == routes.stream_session_logs_v2:
            assert events[-1]["status"] == status

    asyncio.run(scenario())


@pytest.mark.parametrize("status", ["blocked", "stalled"])
def test_gc_applies_existing_ttl_to_terminal_failures(monkeypatch, tmp_path, status):
    monkeypatch.setattr(gc.time, "time", lambda: 1000)
    monkeypatch.setattr(gc.config, "GC_MAX_AGE", 100)
    delete = Mock()
    monkeypatch.setattr(gc.persistence, "delete_session_file", delete)
    old = tmp_path / "old"
    old.mkdir()
    recent = tmp_path / "recent"
    recent.mkdir()
    sessions = {
        "old": BuildSession(status=status, started_at=800, workspace=str(old)),
        "recent": BuildSession(status=status, started_at=950, workspace=str(recent)),
        "active": BuildSession(status="orchestrating", started_at=800),
    }
    assert gc.collect_garbage(sessions) == {"removed": 1, "skipped": 2, "errors": 0}
    assert not old.exists()
    assert recent.exists()
    assert set(sessions) == {"recent", "active"}
    delete.assert_called_once_with("old")
