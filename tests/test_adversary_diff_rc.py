"""A failed `git diff` must never be read as "no diff exists".

Found 2026-09-11 by reading `board_review.review_diff`, then confirmed here.
`review_diff` discarded the `git diff` exit code:

    _, diff_out, _ = await run_cmd(workspace, "git", "diff", base, "HEAD", "--")

`session_phases._phase_adversary` then did `if not diff_out.strip(): SKIP_NO_DIFF`.
A crashed `git diff` (bad ref, git binary missing, corrupted object, timeout) also
produces empty stdout — so it was indistinguishable from "nothing changed", and
SKIP_NO_DIFF is an ALLOWING verdict (`board_review._ALLOWING_VERDICTS`). The push
gate would let code through a review that never ran, with no evidence anything
went wrong. Law 3: absence is never a pass (rules/truth-hacking.md).

The helper retains its exit-code contract. The phase now reads a frozen
base/candidate diff directly, and refuses without a receipt when that command
fails. Its integration tests patch the actual command boundary.
"""
import asyncio
import subprocess
from unittest.mock import AsyncMock, patch

import pytest

from app.server import board_review, session_phases
from app.server.session_model import BuildSession


# ── Unit level: board_review.review_diff must surface the rc, never eat it ──

async def _fake_run_cmd_diff_fails(workspace, *args, timeout=60, env=None):
    if args[:2] == ("git", "status"):
        return 0, "", ""  # tree clean — commit_build_output takes no action
    if args[:2] == ("git", "rev-parse"):
        return 0, "deadbeefcafe", ""
    if args[:2] == ("git", "diff") and "--stat" in args:
        return 0, "", ""  # --stat still "succeeds" with nothing to show
    if args[:2] == ("git", "diff"):
        return 128, "", "fatal: bad revision 'deadbeefcafe'"  # the failure
    raise AssertionError(f"unexpected run_cmd call: {args}")


def test_review_diff_surfaces_a_failed_diff_rc():
    """Positive control for the root cause: rc must reach the caller."""
    diff_out, stat_out, diff_rc = asyncio.run(
        board_review.review_diff("/tmp/does-not-need-to-exist", _fake_run_cmd_diff_fails),
    )
    assert diff_rc == 128, "the failed git diff's exit code was discarded again"
    assert diff_out == ""


async def _fake_run_cmd_diff_succeeds_empty(workspace, *args, timeout=60, env=None):
    if args[:2] == ("git", "status"):
        return 0, "", ""
    if args[:2] == ("git", "rev-parse"):
        return 0, "deadbeefcafe", ""
    if args[:2] == ("git", "diff"):
        return 0, "", ""  # genuinely nothing changed
    raise AssertionError(f"unexpected run_cmd call: {args}")


def test_review_diff_reports_rc_zero_when_genuinely_empty():
    """Negative control: a real empty diff must still read as rc 0."""
    diff_out, stat_out, diff_rc = asyncio.run(
        board_review.review_diff("/tmp/does-not-need-to-exist", _fake_run_cmd_diff_succeeds_empty),
    )
    assert diff_rc == 0
    assert diff_out == ""


# ── Integration level: _phase_adversary must refuse, not skip, on diff_rc != 0 ──

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _git_head(repo):
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
        capture_output=True, text=True, creationflags=_NO_WINDOW,
    ).stdout.strip()


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, creationflags=_NO_WINDOW)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, creationflags=_NO_WINDOW)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, creationflags=_NO_WINDOW)
    (repo / "app.py").write_text("def hello():\n    return 'hi'\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, creationflags=_NO_WINDOW)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True, creationflags=_NO_WINDOW)

    runs_root = tmp_path / "harness_root"
    (runs_root / ".harness").mkdir(parents=True)
    monkeypatch.setenv("TAO_TEST_HARNESS_ROOT", str(runs_root))

    monkeypatch.setattr(session_phases.persistence, "save_session", lambda _session: None)
    monkeypatch.setattr(session_phases.session_delivery, "record_adversary", lambda *args: None)
    session = BuildSession(
        id="test-diffrc-001",
        workspace=str(repo),
        base_sha=_git_head(repo),
        output_lines=[],
    )
    assert asyncio.run(session_phases._prepare_candidate(session))
    return session


def test_phase_adversary_refuses_when_diff_fails(sandbox):
    """The behavioural fix: a diff_rc != 0 must halt the push, receipt-free."""
    with patch(
        "app.server.session_phases.run_cmd",
        new=AsyncMock(return_value=(128, "", "fatal: bad revision")),
    ), patch("app.server.session_phases._run_claude_via_sdk") as mock_sdk, patch(
        "app.server.session_phases._write_board_review_receipt", new=AsyncMock(),
    ) as mock_receipt:
        ok, data = asyncio.run(session_phases._phase_adversary(sandbox, 6))

    assert ok is False, "a failed git diff let the push proceed"
    assert data["verdict"] == "DIFF_ERROR"
    assert data["verdict"] != "SKIP_NO_DIFF", (
        "a diff failure was read as 'nothing to review' — exactly the bypass this test guards"
    )
    mock_sdk.assert_not_called(), "the reviewer must never run on an unknown diff"
    mock_receipt.assert_not_called(), "no receipt may be written on the refusal path"


def test_phase_adversary_still_skips_a_genuinely_empty_diff(sandbox):
    """Negative control: rc 0 with empty output is still a legitimate skip."""
    with patch(
        "app.server.session_phases.run_cmd",
        new=AsyncMock(return_value=(0, "", "")),
    ), patch("app.server.session_phases._write_board_review_receipt", new=AsyncMock()) as mock_receipt:
        ok, data = asyncio.run(session_phases._phase_adversary(sandbox, 6))

    assert ok is True
    assert data["verdict"] == "SKIP_NO_DIFF"
    mock_receipt.assert_called_once()
