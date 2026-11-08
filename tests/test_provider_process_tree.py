"""UNI-3306: a stop leaves nothing running, even when the process list is unreadable or the CLI already exited."""
import os
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
