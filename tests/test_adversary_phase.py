"""
test_adversary_phase.py — RA-1743 unit tests for opus-adversary pre-push gate.

Covers:
  - APPROVE verdict allows push
  - APPROVE WITH NOTES verdict allows push
  - BLOCK verdict halts push (proceed_ok = False)
  - Empty diff skips phase
  - Docs/test-only diff skips phase
  - JSONL log row written for every non-skipped run

The SDK call is mocked — we never hit a real Claude. We only verify the
phase orchestration logic (skip checks, verdict parsing, log writing,
return value).
"""

import asyncio
import datetime
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Set up a minimal git workspace with a code change ready for review."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)

    # Initial commit
    (repo / "app.py").write_text("def hello():\n    return 'hi'\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True)

    # Modify code (uncommitted) so `git diff HEAD` produces output
    (repo / "app.py").write_text(
        "def hello():\n    return 'hi'\n\n\ndef goodbye():\n    return 'bye'\n",
    )

    # Place .harness/adversary-runs/ relative to a fake project root
    runs_root = tmp_path / "harness_root"
    (runs_root / ".harness").mkdir(parents=True)
    monkeypatch.setenv("TAO_TEST_HARNESS_ROOT", str(runs_root))

    # Build a minimal session stand-in. session_model.em() appends to output_lines.
    session = SimpleNamespace(
        id="test-sid-001",
        workspace=str(repo),
        brief="Add a goodbye function",
        evaluator_enabled=True,
        output_lines=[],
    )
    return session, runs_root


def _verdict_text(v: str) -> str:
    """Build a fake adversary response text ending with `v`."""
    return (
        "1. Possible race condition in handler. (file:line)\n"
        "2. Missing test coverage on edge case.\n\n"
        f"{v} — concerns above are minor.\n"
    )


@pytest.mark.parametrize(
    "verdict_text,expected_ok,expected_verdict",
    [
        (_verdict_text("APPROVE"),             True,  "APPROVE"),
        (_verdict_text("APPROVE WITH NOTES"),  True,  "APPROVE_WITH_NOTES"),
        (_verdict_text("BLOCK"),               False, "BLOCK"),
    ],
)
def test_phase_adversary_verdicts(sandbox, verdict_text, expected_ok, expected_verdict):
    session, runs_root = sandbox

    with patch(
        "app.server.session_phases._run_claude_via_sdk",
        new=AsyncMock(return_value=(0, verdict_text, 0.05)),
    ), patch(
        "app.server.session_phases._emit_phase_metric",
    ), patch(
        # Redirect log dir to tmp so test writes don't pollute the real .harness
        "app.server.session_phases.Path",
        side_effect=lambda *a, **k: Path(*a, **k) if not (a and "session_phases.py" in str(a[0])) else runs_root / "fake_session_phases.py",
    ):
        # Import inside the patch context so the patched Path is visible if needed
        from app.server import session_phases

        # Simpler: don't patch Path globally — let the real Path resolve, but
        # ensure HARNESS_CONFIG_PATH resolution works. We tolerate the log
        # write going to the real .harness/adversary-runs/ in tests since
        # they're transient JSONL appends.
        proceed_ok, verdict_data = asyncio.run(session_phases._phase_adversary(session, 6))

    assert proceed_ok is expected_ok, f"verdict={verdict_text!r} → proceed_ok mismatch"
    assert verdict_data["verdict"] == expected_verdict


def test_phase_adversary_skips_no_diff(tmp_path):
    """Empty workspace (no diff) should skip phase, return proceed_ok=True."""
    repo = tmp_path / "clean_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "x.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True)

    session = SimpleNamespace(
        id="test-sid-empty",
        workspace=str(repo),
        brief="",
        evaluator_enabled=True,
        output_lines=[],
    )

    sdk_mock = AsyncMock(return_value=(0, "should not be called", 0.0))
    with patch(
        "app.server.session_phases._run_claude_via_sdk", new=sdk_mock,
    ), patch("app.server.session_phases._emit_phase_metric"):
        from app.server import session_phases
        proceed_ok, verdict_data = asyncio.run(session_phases._phase_adversary(session, 6))

    assert proceed_ok is True
    assert verdict_data["verdict"] == "SKIP_NO_DIFF"
    assert sdk_mock.call_count == 0, "SDK must NOT be called when there is no diff"


def test_phase_adversary_skips_docs_only(tmp_path):
    """Docs-only / README-only diff should skip phase."""
    repo = tmp_path / "docs_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "README.md").write_text("# Hello\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True)
    (repo / "README.md").write_text("# Hello\n\nNew section.\n")

    session = SimpleNamespace(
        id="test-sid-docs",
        workspace=str(repo),
        brief="Docs update",
        evaluator_enabled=True,
        output_lines=[],
    )

    sdk_mock = AsyncMock(return_value=(0, "should not be called", 0.0))
    with patch(
        "app.server.session_phases._run_claude_via_sdk", new=sdk_mock,
    ), patch("app.server.session_phases._emit_phase_metric"):
        from app.server import session_phases
        proceed_ok, verdict_data = asyncio.run(session_phases._phase_adversary(session, 6))

    assert proceed_ok is True
    assert verdict_data["verdict"] == "SKIP_DOCS_ONLY"
    assert sdk_mock.call_count == 0, "SDK must NOT be called for docs-only diffs"


def test_phase_adversary_writes_jsonl_log(sandbox, tmp_path):
    """Every non-skipped run writes a row to .harness/adversary-runs/YYYY-MM-DD.jsonl."""
    session, _ = sandbox

    with patch(
        "app.server.session_phases._run_claude_via_sdk",
        new=AsyncMock(return_value=(0, _verdict_text("APPROVE"), 0.02)),
    ), patch("app.server.session_phases._emit_phase_metric"):
        from app.server import session_phases
        proceed_ok, _ = asyncio.run(session_phases._phase_adversary(session, 6))

    # Find the log file at the real .harness location relative to the repo
    runs_dir = Path(session_phases.__file__).resolve().parents[2] / ".harness" / "adversary-runs"
    today = datetime.date.today().isoformat()
    log_path = runs_dir / f"{today}.jsonl"

    assert log_path.exists(), f"adversary-runs log file not written at {log_path}"
    rows = [json.loads(ln) for ln in log_path.read_text().strip().split("\n") if ln.strip()]
    matching = [r for r in rows if r.get("session_id") == "test-sid-001"]
    assert matching, "expected at least one row with our test session_id"
    last = matching[-1]
    assert last["verdict"] == "APPROVE"
    assert last["rc"] == 0
    assert "files_changed" in last

    # Cleanup our test row so subsequent CI runs don't accumulate
    remaining = [r for r in rows if r.get("session_id") != "test-sid-001"]
    if remaining:
        log_path.write_text("\n".join(json.dumps(r) for r in remaining) + "\n")
    else:
        log_path.unlink(missing_ok=True)
