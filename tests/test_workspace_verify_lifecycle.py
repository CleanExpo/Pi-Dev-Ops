"""Verifier lifecycle regressions retained when execution moved into isolation."""
import asyncio
import os
import shutil
import sys
import time
from pathlib import Path
import pytest
from app.server import workspace_verify as wv, verification_sandbox as sandbox
from test_workspace_verify import _py_repo, _run
requires_sandbox = pytest.mark.skipif(sys.platform != "linux" or shutil.which("bwrap") is None,
                                     reason="real process isolation needs Linux bubblewrap")

def _assert_process_group_gone(pgid: int, timeout_s: float = 2) -> None:
    """Poll boundedly because a killed descendant may be briefly unreaped."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.02)
    pytest.fail(f"process group {pgid} survived cleanup for {timeout_s:.1f}s")


def _leader_exits_after_child_starts() -> str:
    child = "from pathlib import Path; import time; Path('child-ready').write_text('ready'); time.sleep(30)"
    return "\n".join([
        "import subprocess,sys,time; from pathlib import Path",
        f"subprocess.Popen([sys.executable, '-c', {child!r}], stdout=sys.stdout, stderr=sys.stderr)",
        "deadline = time.monotonic() + 2",
        "while not Path('child-ready').exists() and time.monotonic() < deadline: time.sleep(.001)",
        "assert Path('child-ready').exists(), 'descendant never started'",
    ])


@requires_sandbox
def test_sandbox_reaps_descendant_when_command_leader_exits(tmp_path: Path, monkeypatch) -> None:
    """Namespace teardown must kill an already-running pipe-owning descendant.

    Bubblewrap destroys its PID namespace when the command leader exits. That
    closes the sleeper's inherited pipes immediately, before our timeout fires.
    The separate controlled-process test still exercises vanished-leader timeout.
    """
    repo = _py_repo(tmp_path, "def test_ok():\n    assert True\n")
    leader = _leader_exits_after_child_starts()
    monkeypatch.setattr(wv, "detect_check", lambda ws: (["python3", "-c", leader], "descendant probe"))
    original_create = asyncio.create_subprocess_exec
    observed = {}
    async def tracked_create(*args, **kwargs):
        proc = await original_create(*args, **kwargs)
        observed["proc"] = proc
        return proc
    monkeypatch.setattr(wv.asyncio, "create_subprocess_exec", tracked_create)
    started = time.monotonic()
    result = _run(wv.run_workspace_checks(str(repo), timeout_s=3))
    elapsed = time.monotonic() - started
    assert (repo / "child-ready").read_text() == "ready"
    assert result.status == wv.PASSED
    assert elapsed < 2, f"descendant kept stdout open for {elapsed:.2f}s"
    assert observed["proc"].returncode == 0
    _assert_process_group_gone(observed["proc"].pid)


@requires_sandbox
def test_cancellation_kills_and_reaps_process_group(
    tmp_path: Path, monkeypatch,
) -> None:
    """Cancelling the verifier must not orphan its subprocess tree."""
    repo = _py_repo(tmp_path, "def test_ok():\n    assert True\n")
    leader = (
        "import subprocess,sys,time; "
        "subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(30)'], stdout=sys.stdout, stderr=sys.stderr); "
        "time.sleep(30)"
    )
    monkeypatch.setattr(
        wv,
        "detect_check",
        lambda ws: (["python3", "-c", leader], "cancellation probe"),
    )
    original_create = asyncio.create_subprocess_exec
    observed: dict[str, asyncio.subprocess.Process] = {}

    async def tracked_create(*args, **kwargs):
        proc = await original_create(*args, **kwargs)
        observed["proc"] = proc
        return proc

    monkeypatch.setattr(wv.asyncio, "create_subprocess_exec", tracked_create)

    _run(_cancel_running_check(repo, observed))

    proc = observed["proc"]
    assert proc.returncode is not None
    _assert_process_group_gone(proc.pid)


def test_short_lived_runner_transport_is_closed_before_loop_shutdown(
    tmp_path: Path, monkeypatch
) -> None:
    """Close the owned subprocess transport before its event loop shuts down."""
    monkeypatch.setattr(sandbox, "build_command", lambda *a, **kw: (["synthetic"], {}))
    repo = _py_repo(tmp_path, "def test_ok():\n    assert True\n")
    monkeypatch.setattr(
        wv,
        "detect_check",
        lambda ws: (["python3", "-c", "raise SystemExit('No module named pytest')"], "pytest"),
    )

    class ControlledTransport:
        close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    class ControlledProcess:
        returncode = 1
        pid = 999_999_999
        _transport = ControlledTransport()

        async def communicate(self):
            return b"No module named pytest", None

    process = ControlledProcess()

    async def create_controlled(*_args, **_kwargs):
        return process

    monkeypatch.setattr(wv.asyncio, "create_subprocess_exec", create_controlled)

    result = _run(wv.run_workspace_checks(str(repo), timeout_s=30))

    assert result.status == wv.NOT_RUN
    assert process._transport.close_calls == 1



async def _cancel_running_check(repo, observed) -> None:
    task = asyncio.create_task(wv.run_workspace_checks(str(repo), timeout_s=30))
    deadline = asyncio.get_running_loop().time() + 2
    while "proc" not in observed and not task.done():
        if asyncio.get_running_loop().time() >= deadline:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            pytest.fail("subprocess creation did not finish within 2 seconds")
        await asyncio.sleep(0.001)
    if task.done():
        await task
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.parametrize("interruption", [asyncio.TimeoutError, asyncio.CancelledError])
def test_timeout_or_cancel_stops_group_even_when_leader_already_exited(monkeypatch, interruption):
    """An exited leader cannot prevent cleanup of a descendant holding a pipe."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock
    proc = SimpleNamespace(pid=999_999_999, returncode=0, kill=Mock(), _transport=Mock(),
                           communicate=AsyncMock(side_effect=[interruption(), (b"", b"")]))
    kill_group = Mock()
    monkeypatch.setattr(sandbox, "build_command", lambda *a, **kw: (["synthetic"], {}))
    monkeypatch.setattr(sandbox.asyncio, "create_subprocess_exec", AsyncMock(return_value=proc))
    monkeypatch.setattr(sandbox.os, "killpg", kill_group, raising=False)
    monkeypatch.setattr(sandbox.signal, "SIGKILL", 9, raising=False)
    with pytest.raises(interruption):
        _run(sandbox.run_isolated_async("workspace", ["probe"], timeout_s=1))
    kill_group.assert_called_once_with(proc.pid, sandbox.signal.SIGKILL)
    assert proc.communicate.await_count == 2
    proc.kill.assert_not_called()
    proc._transport.close.assert_called_once()
