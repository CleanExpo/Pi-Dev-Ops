"""tests/test_cron_fire_script.py — the script-trigger subprocess contract.

Two defects CodeRabbit found on PR #693, both pre-existing in the code this
module was extracted from:

  * the trigger launched bare `python3`, which on a machine whose default is
    3.9 cannot import this repo at all — the trigger dies on an import error
    that reads like a broken script;
  * `asyncio.wait_for(proc.communicate(), ...)` cancels the *coroutine* and
    leaves the child running. A hung script therefore outlived the trigger that
    gave up on it, and every later fire added another orphan.

Both are asserted here against a real subprocess, not a mock: a killed process
is the only proof that the kill happened.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server import cron_fire_script as cfs  # noqa: E402


class _Log:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def _rec(self, msg, *args, **kw):
        self.lines.append(str(msg) % args if args else str(msg))

    info = warning = error = _rec


def test_interpreter_is_never_bare_python3():
    """The resolved interpreter must be a real path, not a PATH lookup."""
    chosen = cfs._python()
    assert chosen != "python3"
    assert Path(chosen).is_absolute(), chosen
    assert Path(chosen).exists(), chosen


def test_command_strips_a_leading_interpreter():
    """Both `script` spellings run under the resolved interpreter."""
    bare = cfs._command_for("scripts/foo.py --flag x")
    explicit = cfs._command_for("python scripts/foo.py --flag x")
    py3 = cfs._command_for("python3 scripts/foo.py --flag x")

    assert bare[0] == explicit[0] == py3[0] == cfs._python()
    assert bare[1:] == explicit[1:] == py3[1:] == ["scripts/foo.py", "--flag", "x"]
    # A non-python leading token is an argument, not an interpreter to strip.
    assert cfs._command_for("bash scripts/foo.sh")[1:] == ["bash", "scripts/foo.sh"]


def _script(tmp_path: Path, body: str) -> str:
    """Write a real script and return it as a trigger's `script` value.

    A file, not `python -c`: the trigger splits `script` on whitespace, so an
    inline program would be shredded into separate argv entries.
    """
    path = tmp_path / "trigger_script.py"
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_timeout_kills_and_reaps_the_child(monkeypatch, tmp_path):
    """A script that outlives the timeout must be dead when the trigger returns.

    The real defect: without the kill, `proc.returncode` stays None and the
    process keeps running. Asserting on returncode is what makes this a proof
    rather than a claim about intent.
    """
    monkeypatch.setattr(cfs, "SCRIPT_TIMEOUT_SECONDS", 1)
    seen: dict = {}

    async def run() -> None:
        real_exec = asyncio.create_subprocess_exec

        async def capture(*cmd, **kw):
            proc = await real_exec(*cmd, **kw)
            seen["proc"] = proc
            return proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", capture)
        trigger = {"id": "slow", "script": _script(tmp_path, "import time\ntime.sleep(30)\n")}
        log = _Log()
        with pytest.raises(asyncio.TimeoutError):
            await cfs._fire_script_trigger(trigger, log)
        assert any("timed out" in line and "child killed" in line for line in log.lines)

    asyncio.run(run())
    proc = seen["proc"]
    assert proc.returncode is not None, "child survived the timeout — not reaped"


def test_missing_script_field_is_skipped_not_launched(monkeypatch):
    launched: list = []
    monkeypatch.setattr(
        asyncio, "create_subprocess_exec",
        lambda *a, **k: launched.append(a))  # noqa: ARG005

    log = _Log()
    asyncio.run(cfs._fire_script_trigger({"id": "empty"}, log))

    assert launched == []
    assert any("no 'script' field" in line for line in log.lines)


def test_successful_script_logs_rc0(tmp_path):
    log = _Log()
    asyncio.run(cfs._fire_script_trigger(
        {"id": "ok", "script": _script(tmp_path, "print('hi')\n")}, log))
    assert any("complete (rc=0)" in line for line in log.lines)


def test_failing_script_logs_the_exit_code_and_stderr(tmp_path):
    body = "import sys\nsys.stderr.write('boom')\nsys.exit(3)\n"
    log = _Log()
    asyncio.run(cfs._fire_script_trigger(
        {"id": "bad", "script": _script(tmp_path, body)}, log))
    assert any("exited 3" in line and "boom" in line for line in log.lines)
