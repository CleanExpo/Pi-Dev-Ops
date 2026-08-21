"""Coverage for running the target repo's own checks before the evaluator grades.

The evaluator previously asked itself "any bugs ... or broken tests?" having run nothing,
so CORRECTNESS was inference over a diff. These tests pin the part that makes that honest:
a real pass and a real failure must be distinguishable from each other AND from "no check
was runnable" — collapsing those is precisely how the earlier scanner bugs stayed invisible.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import pytest

from app.server import workspace_verify as wv


def _run(coro):
    return asyncio.run(coro)


def _py_repo(tmp_path: Path, test_body: str) -> Path:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='probe'\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_probe.py").write_text(test_body, encoding="utf-8")
    return tmp_path


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


def test_a_passing_suite_is_reported_as_passed(tmp_path: Path) -> None:
    """Positive control: without this, the failure test below proves nothing."""
    repo = _py_repo(tmp_path, "def test_ok():\n    assert True\n")

    result = _run(wv.run_workspace_checks(str(repo), timeout_s=120))

    assert result.status == wv.PASSED
    assert result.ran is True
    assert "pytest" in result.command


def test_a_failing_suite_is_reported_as_failed(tmp_path: Path) -> None:
    repo = _py_repo(tmp_path, "def test_broken():\n    assert 1 == 2\n")

    result = _run(wv.run_workspace_checks(str(repo), timeout_s=120))

    assert result.status == wv.FAILED
    assert result.ran is True
    # The evaluator needs the actual failure, not just a verdict.
    assert "test_broken" in result.output_tail


def test_no_runnable_check_is_its_own_outcome(tmp_path: Path) -> None:
    """'Nothing to run' must never render as 'checks passed'."""
    (tmp_path / "README.md").write_text("no tests here", encoding="utf-8")

    result = _run(wv.run_workspace_checks(str(tmp_path), timeout_s=30))

    assert result.status == wv.NOT_RUN
    assert result.ran is False
    assert result.reason


def test_declared_npm_test_without_node_modules_does_not_run(tmp_path: Path) -> None:
    """Reporting NOT_RUN with a reason beats a spurious failure from a missing install."""
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8"
    )

    result = _run(wv.run_workspace_checks(str(tmp_path), timeout_s=30))

    assert result.status == wv.NOT_RUN
    assert "node_modules" in result.reason


def test_missing_workspace_is_survivable(tmp_path: Path) -> None:
    result = _run(wv.run_workspace_checks(str(tmp_path / "nope"), timeout_s=10))

    assert result.status == wv.NOT_RUN


def test_timeout_is_not_a_pass(tmp_path: Path) -> None:
    """A hung suite must not be gradeable as correct."""
    repo = _py_repo(tmp_path, "import time\n\n\ndef test_hangs():\n    time.sleep(30)\n")

    result = _run(wv.run_workspace_checks(str(repo), timeout_s=2))

    assert result.status == wv.TIMED_OUT
    assert result.status != wv.PASSED


def test_timeout_kills_descendant_after_process_group_leader_exits(
    tmp_path: Path, monkeypatch,
) -> None:
    """A vanished leader must not leave a pipe-owning descendant alive.

    The direct child exits immediately after spawning a sleeper. The sleeper
    inherits the process group and stdout pipe, so ``communicate()`` cannot
    finish until the whole known group is killed.
    """
    repo = _py_repo(tmp_path, "def test_ok():\n    assert True\n")
    leader = (
        "import subprocess,sys; "
        "subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(30)'], stdout=sys.stdout, stderr=sys.stderr)"
    )
    monkeypatch.setattr(
        wv,
        "detect_check",
        lambda ws: ([sys.executable, "-c", leader], "descendant timeout probe"),
    )
    original_create = asyncio.create_subprocess_exec
    observed: dict[str, asyncio.subprocess.Process] = {}

    async def tracked_create(*args, **kwargs):
        proc = await original_create(*args, **kwargs)
        observed["proc"] = proc
        return proc

    monkeypatch.setattr(wv.asyncio, "create_subprocess_exec", tracked_create)

    started = time.monotonic()
    result = _run(wv.run_workspace_checks(str(repo), timeout_s=0.25))
    elapsed = time.monotonic() - started

    assert result.status == wv.TIMED_OUT
    assert elapsed < 2, f"descendant kept the timeout path open for {elapsed:.2f}s"
    _assert_process_group_gone(observed["proc"].pid)


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
        lambda ws: ([sys.executable, "-c", leader], "cancellation probe"),
    )
    original_create = asyncio.create_subprocess_exec
    observed: dict[str, asyncio.subprocess.Process] = {}

    async def tracked_create(*args, **kwargs):
        proc = await original_create(*args, **kwargs)
        observed["proc"] = proc
        return proc

    monkeypatch.setattr(wv.asyncio, "create_subprocess_exec", tracked_create)

    async def scenario() -> None:
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

    _run(scenario())

    proc = observed["proc"]
    assert proc.returncode is not None
    _assert_process_group_gone(proc.pid)


def test_absent_runner_is_not_reported_as_a_test_failure(tmp_path: Path, monkeypatch) -> None:
    """A cloned repo need not have pytest installed.

    `python3 -m pytest` exits non-zero whether the tests failed or the runner is missing.
    Reporting FAILED there would hand the evaluator a fabricated test failure and pull
    CORRECTNESS down for a change that was never exercised.
    """
    repo = _py_repo(tmp_path, "def test_ok():\n    assert True\n")
    # Force the interpreter to one that cannot import pytest.
    monkeypatch.setattr(
        wv, "detect_check",
        lambda ws: (["python3", "-c", "raise SystemExit('No module named pytest')"], "pytest"),
    )

    result = _run(wv.run_workspace_checks(str(repo), timeout_s=30))

    assert result.status == wv.NOT_RUN
    assert result.status != wv.FAILED
    assert "not installed" in result.reason


def test_short_lived_runner_transport_is_closed_before_loop_shutdown(
    tmp_path: Path, monkeypatch
) -> None:
    """A completed child must not defer transport cleanup past ``asyncio.run``.

    Very short-lived children exposed this only during full-suite garbage collection as
    ``BaseSubprocessTransport.__del__: RuntimeError: Event loop is closed``. Observe the
    real subprocess transport so the regression test covers the lifecycle boundary.
    """
    repo = _py_repo(tmp_path, "def test_ok():\n    assert True\n")
    monkeypatch.setattr(
        wv,
        "detect_check",
        lambda ws: (["python3", "-c", "raise SystemExit('No module named pytest')"], "pytest"),
    )
    create = wv.asyncio.create_subprocess_exec
    observed: dict[str, bool] = {"closed": False}

    async def create_observed(*args, **kwargs):
        proc = await create(*args, **kwargs)
        close = proc._transport.close

        def close_observed() -> None:
            observed["closed"] = True
            close()

        proc._transport.close = close_observed
        return proc

    monkeypatch.setattr(wv.asyncio, "create_subprocess_exec", create_observed)

    result = _run(wv.run_workspace_checks(str(repo), timeout_s=30))

    assert result.status == wv.NOT_RUN
    assert observed["closed"] is True


def test_secrets_do_not_reach_the_cloned_repos_test_command(monkeypatch) -> None:
    """A cloned repo's test script must not be handed this process's credentials.

    Flagged as blocking by the gpt-oss-120b cross-model review. This process holds
    GITHUB_TOKEN, LINEAR_API_KEY, Stripe, Supabase service-role and session secrets, and
    the child used to receive dict(os.environ) in full.

    Asserted through the real allow-list rather than a hand-listed set of secret names —
    a deny-list test would keep passing the day someone adds a new credential.
    """
    for name in ("GITHUB_TOKEN", "LINEAR_API_KEY", "STRIPE_API_KEY",
                 "SUPABASE_SERVICE_ROLE_KEY", "TAO_SESSION_SECRET",
                 "ANTHROPIC_API_KEY", "OP_SERVICE_ACCOUNT_TOKEN"):
        monkeypatch.setenv(name, "sentinel-must-not-propagate")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    env = wv._child_env()

    assert "sentinel-must-not-propagate" not in env.values(), (
        f"a secret reached the child environment: {sorted(env)}"
    )
    # Positive control: the allow-list must still deliver what a test runner needs,
    # otherwise this passes trivially by handing the child nothing at all.
    assert env["PATH"] == "/usr/bin:/bin"
    assert env["CI"] == "1"


def test_evaluator_text_forbids_assuming_a_pass_when_nothing_ran() -> None:
    text = wv.format_for_evaluator(wv.VerifyResult(wv.NOT_RUN, "", "no tests", ""))

    assert "NOT seen this code execute" in text
    assert "do not score" in text


def test_evaluator_text_carries_a_real_failure() -> None:
    text = wv.format_for_evaluator(
        wv.VerifyResult(wv.FAILED, "pytest", "", "E   assert 1 == 2")
    )

    assert "FAILED" in text
    assert "assert 1 == 2" in text
