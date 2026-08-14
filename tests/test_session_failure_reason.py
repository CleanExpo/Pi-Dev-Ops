"""The persisted reason a session failed (durable rule 5).

`BuildSession.error` has existed and been serialised by `persistence.save_session`
since forever, but until this change NOTHING in the codebase ever assigned it —
every terminal path set `status = "failed"` and called `em(session, "error", ...)`,
which reaches only the live in-memory event stream.

The consequence was not theoretical. Over 7 days, 51 sessions failed in
`_phase_clone` and every persisted record said `last_completed_phase: ""` and
`error: ""` — that a session failed, never why. Diagnosis required having watched
the SSE stream at the moment of failure.

These tests pin the reason into the PERSISTED record, which is the only artefact
that outlives the session. The existing suite could not have caught the gap:
tests/test_session_clone_auth.py exercises only the SUCCESS path.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.server import persistence, session_phases, supabase_log
from app.server.session_model import BuildSession


@pytest.fixture
def _no_backoff(monkeypatch):
    """Skip the clone retry backoff (2s + 4s) so failure tests stay fast."""
    async def _instant(_seconds):
        return None
    monkeypatch.setattr(session_phases.asyncio, "sleep", _instant)


def _stub_phase(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(session_phases.config, "WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(session_phases.persistence, "save_session", lambda _s: None)
    monkeypatch.setattr(session_phases, "_emit_phase_metric", lambda *_a, **_k: None)


# ── the reason is recorded, not just emitted ─────────────────────────────────

@pytest.mark.asyncio
async def test_clone_failure_records_the_git_stderr(monkeypatch, tmp_path, _no_backoff):
    """The stderr naming the cause must reach session.error, not just the stream."""
    async def failing_clone(cwd, *args, **kwargs):
        return 128, "", "remote: Repository not found.\nfatal: repository not found"

    _stub_phase(monkeypatch, tmp_path)
    monkeypatch.setattr(session_phases, "run_cmd", failing_clone)

    session = BuildSession(repo_url="https://github.com/CleanExpo/Pi-Dev-Ops")
    assert await session_phases._phase_clone(session, "") is False

    assert session.status == "failed"
    # The specific failure, not a generic "it failed after 3 attempts".
    assert session.error, "session.error is empty — the failure reason was lost"
    assert "Repository not found" in session.error


@pytest.mark.asyncio
async def test_clone_failure_reason_survives_to_disk(monkeypatch, tmp_path, _no_backoff):
    """End-to-end: the reason is readable from the persisted record alone.

    This is the property that actually matters. An in-memory attribute nobody
    can read after the process moves on is no better than the event stream.
    """
    async def failing_clone(cwd, *args, **kwargs):
        return 128, "", "fatal: could not read Username: No such device or address"

    monkeypatch.setattr(session_phases.config, "WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(session_phases, "_emit_phase_metric", lambda *_a, **_k: None)
    monkeypatch.setattr(session_phases, "run_cmd", failing_clone)
    # Redirect the real persistence path (LOG_DIR, not _sessions_dir — the latter
    # is what creates the directory) and silence the Supabase dual-write.
    monkeypatch.setattr(persistence.config, "LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(supabase_log, "save_session_checkpoint", lambda _s: None)

    session = BuildSession(repo_url="https://github.com/CleanExpo/Pi-Dev-Ops")
    await session_phases._phase_clone(session, "")

    written = json.loads(Path(persistence._path(session.id)).read_text())
    assert written["status"] == "failed"
    assert written["error"], "persisted checkpoint has error='' — the RA-7216 blind spot"
    assert "could not read Username" in written["error"]


@pytest.mark.asyncio
async def test_clone_contamination_records_both_urls(monkeypatch, tmp_path, _no_backoff):
    """The RA-1173 guard's reason must name what it saw vs what it expected."""
    async def wrong_origin(cwd, *args, **kwargs):
        if args[1:3] == ("remote", "get-url"):
            return 0, "https://github.com/SomeoneElse/other-repo.git\n", ""
        return 0, "", ""

    _stub_phase(monkeypatch, tmp_path)
    monkeypatch.setattr(session_phases, "run_cmd", wrong_origin)

    session = BuildSession(repo_url="https://github.com/CleanExpo/Pi-Dev-Ops")
    assert await session_phases._phase_clone(session, "") is False
    assert "SomeoneElse/other-repo" in session.error
    assert "TAO_WORKSPACE" in session.error


@pytest.mark.asyncio
async def test_git_missing_records_the_reason(monkeypatch, tmp_path, _no_backoff):
    async def no_git(cwd, *args, **kwargs):
        raise FileNotFoundError("git")

    _stub_phase(monkeypatch, tmp_path)
    monkeypatch.setattr(session_phases, "run_cmd", no_git)

    session = BuildSession(repo_url="https://github.com/CleanExpo/Pi-Dev-Ops")
    assert await session_phases._phase_clone(session, "") is False
    assert "Git not in PATH" in session.error


# ── MUTATION CONTROL ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_every_terminal_failure_records_a_reason(monkeypatch, tmp_path, _no_backoff):
    """MUTATION CONTROL: drop the `session.error = ...` line in `_fail_phase`
    and this fails, while every other test in the repo still passes.

    Pinning the invariant at the helper rather than per-call-site means a NEW
    terminal path added later cannot silently reintroduce the blind spot — it
    either goes through _fail_phase and is covered, or it bypasses it and is
    caught by the audit below.
    """
    session = BuildSession(repo_url="https://github.com/CleanExpo/Pi-Dev-Ops")
    monkeypatch.setattr(session_phases.persistence, "save_session", lambda _s: None)

    session_phases._fail_phase(session, "some specific cause")

    assert session.status == "failed"
    assert session.error == "some specific cause"


def test_no_terminal_path_bypasses_the_helper():
    """Every `status = "failed"` in the phase module must go through _fail_phase.

    A direct assignment is exactly the shape of the original defect: it sets the
    terminal state without recording why. Guarding the pattern is what stops this
    regressing the next time a phase grows a new failure branch.
    """
    source = Path(session_phases.__file__).read_text()
    # Match the ASSIGNMENT STATEMENT only — prose inside a docstring that quotes
    # the pattern (and the helper's own explanatory comment) is not an offender.
    assignment = re.compile(r'^\s*session\.status\s*=\s*"failed"\s*$')
    offenders = [
        (n, line.strip())
        for n, line in enumerate(source.splitlines(), 1)
        if assignment.match(line)
    ]
    # The only permitted assignment is the one inside _fail_phase itself.
    assert len(offenders) == 1, (
        f"terminal failure(s) bypassing _fail_phase (error would persist as ''): {offenders}"
    )


def test_missing_github_token_is_logged_not_silent(monkeypatch, caplog):
    """A missing token must name itself, or a private repo 404 misleads.

    `_git_clone_env` returning None is correct behaviour; doing it silently is
    what turns a config error into an unexplained "repository not found".
    """
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with caplog.at_level("WARNING"):
        env = session_phases._git_clone_env("https://github.com/CleanExpo/Pi-Dev-Ops")
    assert env is None
    assert "GITHUB_TOKEN" in caplog.text


def test_non_github_url_does_not_warn(monkeypatch, caplog):
    """Negative control: a non-github remote legitimately needs no token."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with caplog.at_level("WARNING"):
        env = session_phases._git_clone_env("https://gitlab.com/some/repo")
    assert env is None
    assert "GITHUB_TOKEN" not in caplog.text
