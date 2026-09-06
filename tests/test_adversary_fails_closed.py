"""The last gate before a push must not read a broken reviewer as approval.

RA-7433 audit finding P05. `_phase_adversary` sets `verdict = "UNKNOWN"` and
only replaces it when `rc == 0 and output_text`. Downstream, only
`verdict == "BLOCK"` returns False. So a reviewer that crashed, timed out, or
returned nothing produced UNKNOWN, and UNKNOWN proceeded to push - identical
behaviour to APPROVE.

This is the last gate before code leaves the machine. Global doctrine in
~/.claude/CLAUDE.md is explicit: "Missing, stale, failed or unavailable review
evidence means STOP and queue the work; never self-certify."

The existing tests/test_adversary_phase.py parametrises only APPROVE,
APPROVE WITH NOTES and BLOCK - the three paths where the reviewer worked. No
case covered the reviewer failing, which is why this survived.
"""
import asyncio
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.server import session_phases


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """A git workspace with an uncommitted CODE change, so the phase runs.

    A docs-only or empty diff short-circuits before the verdict logic and would
    make every assertion below vacuous.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "app.py").write_text("def hello():\n    return 'hi'\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True)
    (repo / "app.py").write_text(
        "def hello():\n    return 'hi'\n\n\ndef goodbye():\n    return 'bye'\n",
    )

    runs_root = tmp_path / "harness_root"
    (runs_root / ".harness").mkdir(parents=True)
    monkeypatch.setenv("TAO_TEST_HARNESS_ROOT", str(runs_root))

    return SimpleNamespace(
        id="test-failclosed-001",
        workspace=str(repo),
        brief="Add a goodbye function",
        evaluator_enabled=True,
        output_lines=[],
    )


def _run(session, sdk_return):
    with patch(
        "app.server.session_phases._run_claude_via_sdk",
        new=AsyncMock(return_value=sdk_return),
    ), patch("app.server.session_phases._emit_phase_metric"):
        return asyncio.run(session_phases._phase_adversary(session, 6))


def test_the_gate_is_actually_reached(sandbox):
    """Positive control.

    If the diff were empty or docs-only the phase returns True before any
    verdict logic, and every assertion below would pass for the wrong reason.
    A clean APPROVE must proceed AND report APPROVE, which proves the verdict
    path ran.
    """
    ok, data = _run(sandbox, (0, "1. minor nit\n\nAPPROVE - looks fine.\n", 0.01))
    assert ok is True
    assert data["verdict"] == "APPROVE", (
        "verdict path was not reached; the phase short-circuited and these "
        "tests would be measuring nothing"
    )


def test_reviewer_crash_does_not_proceed(sandbox):
    """Non-zero exit means the review did not happen. That is not approval."""
    ok, data = _run(sandbox, (1, "Traceback: model unavailable", 0.0))
    assert ok is False, "a crashed reviewer let the push proceed"
    assert data["verdict"] != "APPROVE"


def test_empty_review_does_not_proceed(sandbox):
    """Exit 0 with no output is not a review either.

    An exit code is not a verdict: the estate has already been bitten by a
    reviewer that exits 0 on a usage limit and writes nothing.
    """
    ok, data = _run(sandbox, (0, "", 0.0))
    assert ok is False, "an empty review let the push proceed"


def test_unparseable_review_does_not_proceed(sandbox):
    """Output that names no verdict is undetermined, and undetermined blocks."""
    ok, data = _run(sandbox, (0, "I looked at the diff and had some thoughts.\n", 0.02))
    assert ok is False, "a review with no verdict let the push proceed"


def test_block_still_blocks(sandbox):
    ok, data = _run(sandbox, (0, "1. real problem\n\nBLOCK\n", 0.02))
    assert ok is False
    assert data["verdict"] == "BLOCK"


def test_approve_with_notes_still_proceeds(sandbox):
    """The fix must not turn the gate into 'always block'.

    A control that can only say no is as useless as one that can only say yes.
    """
    ok, data = _run(sandbox, (0, "1. nit\n\nAPPROVE WITH NOTES\n", 0.02))
    assert ok is True
    assert data["verdict"] == "APPROVE_WITH_NOTES"
