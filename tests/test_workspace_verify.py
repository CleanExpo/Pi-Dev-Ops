"""Coverage for running the target repo's own checks before the evaluator grades.

The evaluator previously asked itself "any bugs ... or broken tests?" having run nothing,
so CORRECTNESS was inference over a diff. These tests pin the part that makes that honest:
a real pass and a real failure must be distinguishable from each other AND from "no check
was runnable" — collapsing those is precisely how the earlier scanner bugs stayed invisible.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.server import workspace_verify as wv


def _run(coro):
    return asyncio.run(coro)


def _py_repo(tmp_path: Path, test_body: str) -> Path:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='probe'\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_probe.py").write_text(test_body, encoding="utf-8")
    return tmp_path


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
