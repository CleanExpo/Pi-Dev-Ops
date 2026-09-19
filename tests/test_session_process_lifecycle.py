"""Command cancellation only terminates the process tree owned by that command."""

import asyncio
import signal
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.server import session_phases as phases


@pytest.fixture
def process(monkeypatch):
    monkeypatch.setattr(signal, "SIGKILL", 9, raising=False)
    proc = SimpleNamespace(
        pid=43210,
        returncode=None,
        communicate=AsyncMock(return_value=(b"output", b"warning")),
        kill=Mock(),
    )
    monkeypatch.setattr(phases.asyncio, "create_subprocess_exec", AsyncMock(return_value=proc))
    return proc


@pytest.mark.parametrize("platform", ["nt", "posix"])
async def test_success_uses_isolated_group_and_preserves_output(monkeypatch, process, platform):
    monkeypatch.setattr(phases, "os", SimpleNamespace(name=platform))
    monkeypatch.setattr(phases, "subprocess", SimpleNamespace(
        CREATE_NO_WINDOW=0x08000000, CREATE_NEW_PROCESS_GROUP=0x00000200,
    ))
    process.returncode = 0
    assert await phases.run_cmd("workspace", "git", "status", env={"SAFE": "yes"}) == (
        0, "output", "warning"
    )
    call = phases.asyncio.create_subprocess_exec.call_args
    assert Path(call.args[0]).is_absolute()
    assert call.args[-1] == "status"
    assert "core.hooksPath=/dev/null" in call.args
    assert call.kwargs["cwd"] == "workspace"
    assert call.kwargs["env"]["SAFE"] == "yes"
    assert call.kwargs["env"]["GIT_CONFIG_NOSYSTEM"] == "1"
    if platform == "nt":
        assert call.kwargs["creationflags"] == 0x08000200
    else:
        assert call.kwargs["start_new_session"] is True
    process.kill.assert_not_called()


@pytest.mark.parametrize("failure", [asyncio.TimeoutError, asyncio.CancelledError])
async def test_posix_failure_kills_only_owned_group_and_drains(monkeypatch, process, failure):
    killpg = Mock()
    monkeypatch.setattr(phases, "os", SimpleNamespace(name="posix", killpg=killpg))
    process.communicate.side_effect = [failure(), (b"", b"")]
    with pytest.raises(failure):
        await phases.run_cmd("workspace", "git", "clone")
    killpg.assert_called_once_with(process.pid, signal.SIGKILL)
    process.kill.assert_called_once()
    assert process.communicate.await_count == 2


@pytest.mark.parametrize("failure", [asyncio.TimeoutError, asyncio.CancelledError])
@pytest.mark.parametrize("killer_failure", [None, OSError, asyncio.TimeoutError])
async def test_windows_failure_hides_tree_killer_and_reaps(monkeypatch, process, failure, killer_failure):
    monkeypatch.setattr(phases, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(phases, "subprocess", SimpleNamespace(
        CREATE_NO_WINDOW=0x08000000, CREATE_NEW_PROCESS_GROUP=0x00000200,
    ))
    killer = SimpleNamespace(
        returncode=None, wait=AsyncMock(), kill=Mock(),
    )
    if killer_failure:
        killer.wait.side_effect = [killer_failure(), None]
    phases.asyncio.create_subprocess_exec.side_effect = [process, killer]
    process.communicate.side_effect = [failure(), (b"", b"")]
    with pytest.raises(failure):
        await phases.run_cmd("workspace", "git", "clone")
    call = phases.asyncio.create_subprocess_exec.call_args_list[1]
    assert call.args == ("taskkill", "/PID", str(process.pid), "/T", "/F")
    assert call.kwargs["creationflags"] & 0x08000000
    process.kill.assert_called_once()
    assert process.communicate.await_count == 2
    if killer_failure:
        killer.kill.assert_called_once()


async def test_cleanup_failure_does_not_replace_cancellation(monkeypatch, process):
    monkeypatch.setattr(phases, "os", SimpleNamespace(name="posix", killpg=Mock(side_effect=ProcessLookupError)))
    process.communicate.side_effect = [asyncio.CancelledError(), asyncio.TimeoutError()]
    process.kill.side_effect = ProcessLookupError
    with pytest.raises(asyncio.CancelledError):
        await phases.run_cmd("workspace", "git", "clone")
    assert process.communicate.await_count == 2


@pytest.mark.parametrize("cancel", [False, True])
async def test_real_isolated_sleeping_child_is_reaped(monkeypatch, tmp_path, cancel):
    """Only a newly launched, hidden test child is ever terminated here."""
    create = asyncio.create_subprocess_exec
    children = []
    started = asyncio.Event()

    async def capture(*args, **kwargs):
        child = await create(*args, **kwargs)
        children.append(child)
        started.set()
        return child

    monkeypatch.setattr(phases.asyncio, "create_subprocess_exec", capture)
    task = asyncio.create_task(phases.run_cmd(
        str(tmp_path), sys.executable, "-c", "import time; time.sleep(60)",
        timeout=60 if cancel else 0.1,
    ))
    await asyncio.wait_for(started.wait(), timeout=5)
    if cancel:
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else asyncio.TimeoutError):
        await asyncio.wait_for(task, timeout=20)
    assert children[0].returncode is not None
    assert all(child.returncode is not None for child in children)
