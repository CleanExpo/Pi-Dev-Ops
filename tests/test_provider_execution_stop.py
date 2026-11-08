"""UNI-3306: an optional stop ends the model CLI and every child it started; no stop = unchanged."""
import asyncio
import os
import subprocess
import threading
import time

import pytest

from app.server import provider_execution as pe

pytestmark = pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX")

_FAKE_CLI = """#!/usr/bin/env python3
import os, subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
with open({pidfile!r}, "w") as f:
    f.write(f"{{os.getpid()}} {{child.pid}}")
time.sleep(120)
"""


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A killed child of a dead parent may linger as a zombie until reaped by init.
    state = subprocess.run(["/bin/ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout
    return bool(state.strip()) and not state.strip().startswith("Z")


@pytest.fixture
def fake_cli(tmp_path, monkeypatch):
    pidfile = tmp_path / "pids"
    cli = tmp_path / "fake-claude"
    cli.write_text(_FAKE_CLI.format(pidfile=str(pidfile)))
    cli.chmod(0o755)
    monkeypatch.setattr(pe, "CLAUDE_CLI", str(cli))
    return pidfile


def _wait_for(pidfile, limit=10.0):
    end = time.monotonic() + limit
    while time.monotonic() < end:
        if pidfile.exists() and pidfile.read_text().strip():
            return [int(x) for x in pidfile.read_text().split()]
        time.sleep(0.05)
    raise AssertionError("fake CLI never started")


def _gone(*pids, limit=2.0):
    end = time.monotonic() + limit
    while time.monotonic() < end and any(_alive(p) for p in pids):
        time.sleep(0.05)
    return [p for p in pids if _alive(p)]


def test_stop_ends_the_whole_process_group_within_five_seconds(fake_cli):
    stop = threading.Event()
    result = {}
    worker = threading.Thread(target=lambda: result.update(
        out=pe._claude_process("prompt", "claude-test", 120, stop)))
    worker.start()
    parent, child = _wait_for(fake_cli)
    started = time.monotonic()
    stop.set()
    worker.join(timeout=10)
    elapsed = time.monotonic() - started
    left = _gone(parent, child)
    assert not worker.is_alive()
    assert elapsed < 5.0, elapsed
    assert result["out"][0] == pe.STOPPED_RC
    assert left == [], f"processes left running: {left}"


def test_deadline_without_stop_signal_still_ends_the_group(fake_cli):
    stop = threading.Event()
    rc, _, err = pe._claude_process("prompt", "claude-test", 1, stop)
    parent, child = _wait_for(fake_cli)
    assert rc == 124 and "timed out" in err
    assert _gone(parent, child) == []


def test_callers_without_stop_use_the_unchanged_path(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(kwargs)
        return subprocess.CompletedProcess(argv, 0, '{"type":"result","is_error":false,"result":"ok"}', "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(pe, "_run_stoppable", lambda *a, **k: pytest.fail("stoppable path used without stop"))
    assert pe._claude_process("prompt", "claude-test", 7)[0] == 0
    assert calls[0]["timeout"] == 7 and calls[0]["capture_output"] is True


def test_dispatch_without_stop_passes_the_original_three_arguments(monkeypatch):
    seen = []

    def three_args(prompt, model_id, timeout_s):
        seen.append((prompt, model_id, timeout_s))
        return 0, '{"type":"result","is_error":false,"result":"ok"}', ""

    monkeypatch.setattr(pe, "_claude_process", three_args)
    out = asyncio.run(pe._run_via_claude_print("p", model_id="m", timeout_s=9))
    assert out.rc == 0 and seen == [("p", "m", 9)]


_ESCAPING_CLI = """#!/usr/bin/env python3
import os, subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], start_new_session=True)
with open({pidfile!r}, "w") as f:
    f.write(f"{{os.getpid()}} {{child.pid}}")
time.sleep(120)
"""


class _SetAfterFirstCheck:
    """A stop that is clear when the call starts and set by the time its result is read."""

    def __init__(self):
        self.calls = 0

    def is_set(self):
        self.calls += 1
        return self.calls > 1


def test_stop_set_before_the_call_never_starts_either_cli(fake_cli, monkeypatch):
    stop = threading.Event()
    stop.set()
    assert pe._claude_process("prompt", "claude-test", 120, stop)[0] == pe.STOPPED_RC
    monkeypatch.setenv("CODEX_CLI", pe.CLAUDE_CLI)
    assert pe._codex_process("prompt", "gpt-test", 120, stop).returncode == pe.STOPPED_RC
    time.sleep(0.5)
    assert not fake_cli.exists(), "a CLI was started although the stop was already set"


def test_result_that_arrives_after_the_stop_is_not_accepted():
    import sys
    rc, out, _ = pe._run_stoppable([sys.executable, "-c", "print('complete')"],
                                   stop=_SetAfterFirstCheck(), timeout_s=5)
    assert rc == pe.STOPPED_RC and out == ""


def test_descendant_that_left_the_group_cannot_hold_the_stop_open(tmp_path, monkeypatch):
    pidfile = tmp_path / "pids"
    cli = tmp_path / "fake-claude"
    cli.write_text(_ESCAPING_CLI.format(pidfile=str(pidfile)))
    cli.chmod(0o755)
    monkeypatch.setattr(pe, "CLAUDE_CLI", str(cli))
    stop, result = threading.Event(), {}
    worker = threading.Thread(target=lambda: result.update(
        out=pe._claude_process("prompt", "claude-test", 120, stop)))
    worker.start()
    parent, escaped = _wait_for(pidfile)
    try:
        started = time.monotonic()
        stop.set()
        worker.join(timeout=10)
        elapsed = time.monotonic() - started
        assert not worker.is_alive(), "stop blocked on a descendant outside the process group"
        assert elapsed < 5.0, elapsed
        assert result["out"][0] == pe.STOPPED_RC
        assert _gone(parent, escaped) == [], "a descendant that called setsid() was left running"
    finally:
        if _alive(escaped):
            os.kill(escaped, 9)


def test_descendant_that_cannot_be_stopped_is_logged_by_pid_and_command(tmp_path, monkeypatch, caplog):
    from app.server import provider_process_tree as tree
    pidfile = tmp_path / "pids"
    cli = tmp_path / "fake-claude"
    cli.write_text(_ESCAPING_CLI.format(pidfile=str(pidfile)))
    cli.chmod(0o755)
    monkeypatch.setattr(pe, "CLAUDE_CLI", str(cli))
    monkeypatch.setattr(tree, "kill_pid", lambda pid, sig: None)  # the escaped child cannot be stopped
    stop, result = threading.Event(), {}
    worker = threading.Thread(target=lambda: result.update(
        out=pe._claude_process("prompt", "claude-test", 120, stop)))
    worker.start()
    parent, escaped = _wait_for(pidfile)
    try:
        with caplog.at_level("WARNING", logger=tree.__name__):
            stop.set()
            worker.join(timeout=10)
        assert not worker.is_alive() and result["out"][0] == pe.STOPPED_RC
        warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert any(f"process {escaped} " in w and "time.sleep(120)" in w for w in warnings), warnings
    finally:
        if _alive(escaped):
            os.kill(escaped, 9)


_EXITING_PARENT = """#!/usr/bin/env python3
import os, subprocess, sys
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
with open({pidfile!r}, "w") as f:
    f.write(f"{{os.getpid()}} {{child.pid}}")
"""


class _SetOnceStarted:
    """A stop that becomes set once the CLI has written its pids, i.e. as the parent finishes."""

    def __init__(self, pidfile):
        self.pidfile = pidfile

    def is_set(self):
        return self.pidfile.exists() and bool(self.pidfile.read_text().strip())


def test_stop_as_the_parent_finishes_still_ends_its_children(tmp_path):
    pidfile = tmp_path / "pids"
    cli = tmp_path / "fake-cli"
    cli.write_text(_EXITING_PARENT.format(pidfile=str(pidfile)))
    cli.chmod(0o755)
    rc, out, _ = pe._run_stoppable([str(cli)], stop=_SetOnceStarted(pidfile), timeout_s=30)
    parent, child = _wait_for(pidfile)
    left = _gone(parent, child)
    if left:
        os.kill(child, 9)
    assert rc == pe.STOPPED_RC and out == ""
    assert left == [], f"processes left running: {left}"


def test_result_that_finishes_after_the_deadline_is_not_accepted():
    import sys
    rc, out, _ = pe._run_stoppable(
        [sys.executable, "-c", "import time; time.sleep(0.15); print('late')"],
        stop=threading.Event(), timeout_s=0.05)
    assert rc == 124 and "late" not in out


_DENIED_PS = "#!/bin/sh\necho 'ps: permission denied' >&2\nexit 1\n"
_HANGING_PS = "#!/bin/sh\nexec sleep 30\n"


@pytest.mark.parametrize("fake_ps", [_DENIED_PS, _HANGING_PS], ids=["ps-denied", "ps-hangs"])
def test_unreadable_process_list_is_warned_and_cannot_stretch_the_stop(fake_ps, tmp_path, monkeypatch, caplog):
    from app.server import provider_process_tree as tree
    ps = tmp_path / "ps"
    ps.write_text(fake_ps)
    ps.chmod(0o755)
    monkeypatch.setattr(tree, "PS", str(ps), raising=False)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")  # older code ran ps from PATH
    pidfile = tmp_path / "pids"
    cli = tmp_path / "fake-claude"
    cli.write_text(_ESCAPING_CLI.format(pidfile=str(pidfile)))
    cli.chmod(0o755)
    monkeypatch.setattr(pe, "CLAUDE_CLI", str(cli))
    stop, result = threading.Event(), {}
    worker = threading.Thread(target=lambda: result.update(
        out=pe._claude_process("prompt", "claude-test", 120, stop)))
    worker.start()
    parent, escaped = _wait_for(pidfile)
    try:
        with caplog.at_level("WARNING", logger=tree.__name__):
            started = time.monotonic()
            stop.set()
            worker.join(timeout=10)
            elapsed = time.monotonic() - started
        assert not worker.is_alive() and result["out"][0] == pe.STOPPED_RC
        assert elapsed < 5.0, elapsed
        assert _gone(parent) == []
        warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert any("process list could not be read" in w for w in warnings), warnings
    finally:
        if _alive(escaped):
            os.kill(escaped, 9)


_ESCAPE_THEN_EXIT_CLI = """#!/usr/bin/env python3
import os, subprocess, sys
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], start_new_session=True)
with open({pidfile!r}, "w") as f:
    f.write(f"{{os.getpid()}} {{child.pid}}")
"""


def test_escaped_child_of_a_cli_that_already_exited_is_still_stopped(tmp_path, monkeypatch, caplog):
    from app.server import provider_process_tree as tree
    pidfile = tmp_path / "pids"
    cli = tmp_path / "fake-claude"
    cli.write_text(_ESCAPE_THEN_EXIT_CLI.format(pidfile=str(pidfile)))
    cli.chmod(0o755)
    monkeypatch.setattr(pe, "CLAUDE_CLI", str(cli))
    stop, result = threading.Event(), {}
    worker = threading.Thread(target=lambda: result.update(
        out=pe._claude_process("prompt", "claude-test", 120, stop)))
    worker.start()
    parent, escaped = _wait_for(pidfile)
    try:
        assert _gone(parent) == []  # the CLI exited; its child was reparented before any scan
        with caplog.at_level("WARNING", logger=tree.__name__):
            started = time.monotonic()
            stop.set()
            worker.join(timeout=10)
            elapsed = time.monotonic() - started
        assert not worker.is_alive() and result["out"][0] == pe.STOPPED_RC
        assert elapsed < 5.0, elapsed
        warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert _gone(escaped) == [] or any(f"process {escaped}" in w for w in warnings), (
            "an escaped child was left running with no warning naming it")
        assert _gone(escaped) == [], f"escaped child left running: {warnings}"
    finally:
        if _alive(escaped):
            os.kill(escaped, 9)
