"""UNI-3306: a stop leaves nothing running, even when the process list is unreadable or the CLI already exited."""
import os
import subprocess
import threading
import time

import pytest

from app.server import provider_execution as pe
from test_provider_execution_stop import _ESCAPING_CLI, _alive, _gone, _wait_for

pytestmark = pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX")


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


class _Proc:
    pid = 2 ** 22 + 12345  # no such process group; killpg is a no-op

    def wait(self, timeout=None):
        return 0


def test_unidentified_pipe_holder_is_named_but_never_signalled(monkeypatch, caplog):
    from app.server import provider_process_tree as tree
    monkeypatch.setattr(tree, "_holder_pids", lambda fds, t, me: {4242})
    monkeypatch.setattr(tree, "ps_table", lambda t: None)
    killed = []
    monkeypatch.setattr(tree, "kill_pid", lambda pid, sig: killed.append(pid))
    with caplog.at_level("WARNING", logger=tree.__name__):
        tree.stop_tree(_Proc(), {}, budget_s=0.5, grace_s=0.1, fds=[1])
    warnings = " ".join(r.getMessage() for r in caplog.records if r.levelname == "WARNING")
    assert 4242 not in killed, "a pid that may have been reused was signalled without its identity"
    assert "4242" in warnings, f"the pipe holder was not named in a warning: {warnings!r}"


def test_lsof_path_finds_the_holder_of_our_pipe_by_its_address(monkeypatch):
    from app.server import provider_process_tree as tree
    me = os.getpid()
    own = [(me, "d", "0xabc")]
    users = own + [(4242, "n->", "0xabc"), (777, "n->", "0xdef")]
    monkeypatch.setattr(tree, "_lsof", lambda args, t: own if "-p" in args else users)
    assert tree._lsof_holders([1], 0.5, me) == {4242}
    monkeypatch.setattr(tree, "_lsof", lambda args, t: None)
    assert tree._lsof_holders([1], 0.5, me) is None, "an lsof failure must read as unreadable, not empty"


def test_reused_pid_running_the_same_command_is_not_signalled(monkeypatch):
    from app.server import provider_process_tree as tree
    started = {"now": "Sun Nov  8 14:00:01 2026"}

    def fake_run(argv, **kw):
        fmt = argv[argv.index("-o") + 1]
        start = f" {started['now']}" if "lstart" in fmt else ""
        rows = [f"{os.getpid()} 1 S{start} python", f"500 {os.getpid()} S{start} /usr/bin/worker --x"]
        return subprocess.CompletedProcess(argv, 0, "\n".join(rows) + "\n", "")

    monkeypatch.setattr(tree.subprocess, "run", fake_run)
    known = tree.descendants(os.getpid(), 0.5)
    assert 500 in known
    started["now"] = "Sun Nov  8 14:09:59 2026"  # pid 500 ended and was reused by the same command
    assert tree.live(known, 0.5) == {}, "a reused pid with the same command would be signalled"
