"""Parent failures must drain owned workers before recording terminal failure."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.server import kill_switch, orchestration_run, orchestrator, session_model, sessions
from app.server.session_model import BuildSession


@pytest.fixture
def group(monkeypatch):
    parent = BuildSession(id="parent", status="orchestrating")
    child = BuildSession(id="child", status="building", parent_session_id=parent.id)
    complete = BuildSession(id="complete", status="complete", parent_session_id=parent.id)
    unrelated = BuildSession(id="unrelated", status="building", parent_session_id="other")
    store = {s.id: s for s in (parent, child, complete, unrelated)}
    for module in (sessions, session_model, orchestrator):
        monkeypatch.setattr(module, "_sessions", store)
    monkeypatch.setattr(sessions, "_build_tasks", {})
    monkeypatch.setattr(orchestrator, "_fan_out_tasks", {})
    saved = Mock()
    monkeypatch.setattr(orchestration_run.persistence, "save_session", saved)
    return SimpleNamespace(parent=parent, child=child, complete=complete,
                           unrelated=unrelated, store=store, saved=saved)


async def _waiting_worker(child, started, stopped, release, effects):
    started.set()
    try:
        await release.wait()
        effects.append("pushed")
        child.status = "complete"
    finally:
        stopped.set()


@pytest.mark.parametrize("error", [RuntimeError("wave observation failed"),
                                     kill_switch.KillSwitchAbort("HARD_STOP", {"iters": 1})])
async def test_wave_failure_cancels_owned_worker_and_prevents_late_delivery(monkeypatch, group, error):
    started, stopped, release, effects = asyncio.Event(), asyncio.Event(), asyncio.Event(), []
    task = sessions.register_build_task(group.child, asyncio.create_task(
        _waiting_worker(group.child, started, stopped, release, effects)))
    await started.wait()
    launch = AsyncMock(return_value=([group.child.id], []))
    monkeypatch.setattr(kill_switch, "LoopCounter", lambda: SimpleNamespace(tick=Mock(side_effect=error)))
    async def fan_out(parent, *args):
        await orchestration_run.run_waves(parent, [["first"], ["dependent"]], "sonnet",
            True, "build", "/unused", launch, orchestrator._wait_for_wave)
    try:
        await orchestration_run.run_parent(group.parent, "brief", 1, "sonnet", "build",
                                           True, fan_out, group.store)
        assert task.cancelled() and stopped.is_set()
        assert group.child.status == "killed"
        assert group.parent.status == "failed" and str(error) == group.parent.error
        assert group.complete.status == "complete" and group.unrelated.status == "building"
        launch.assert_awaited_once()
        group.saved.assert_called_with(group.parent)
        assert group.child.id not in sessions._build_tasks
        release.set()
        await asyncio.sleep(0)
        assert effects == []
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("failure", [False, RuntimeError("worker stop failed")])
async def test_error_cleanup_retains_original_and_worker_stop_failure(monkeypatch, group, failure):
    stop = AsyncMock(return_value=failure)
    if isinstance(failure, Exception):
        stop.side_effect = failure
    monkeypatch.setattr(sessions, "kill_session", stop)
    fan_out = AsyncMock(side_effect=RuntimeError("wave observation failed"))
    await orchestration_run.run_parent(group.parent, "brief", 1, "sonnet", "build",
                                       True, fan_out, group.store)
    stop.assert_awaited_once_with(group.child.id)
    assert group.parent.status == "failed"
    assert "wave observation failed" in group.parent.error
    assert "workers could not be stopped" in group.parent.error
    group.saved.assert_called_with(group.parent)
