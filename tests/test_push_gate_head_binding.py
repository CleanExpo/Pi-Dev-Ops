"""Unit 2 P0 — the receipt must bind to the sha the push phase actually gates on.

THE DEFECT THIS PINS. `_phase_adversary` wrote a receipt bound to HEAD. `_phase_push`
then ran `git add -A && git commit`, which MOVED HEAD, and only then read the receipt.
So the receipt bound to the pre-commit sha and the gate compared it against the
post-commit sha. They can never match when the session produced work — which is every
session that did anything. A session with nothing to commit passed, because HEAD did
not move. The gate refused exactly the builds it exists to let through, and waved
through the empty ones.

Neither test below is satisfied by a gate that always allows: `test_refuses_when_code_
changes_after_the_review` is the negative control, and it is the same code path. The
end-to-end test drives the real phases against a real git repo, because the whole
defect lives in the ORDER two real git commands run in, and a mocked git cannot have
an order.
"""
from __future__ import annotations

import subprocess
import types
from pathlib import Path

import pytest

from app.server import board_review, session_phases


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True,
    ).stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "ws"
    r.mkdir()
    _git(r.parent, "init", "-q", "-b", "main", str(r))
    _git(r, "config", "user.email", "t@example.invalid")
    _git(r, "config", "user.name", "T")
    (r / "seed.py").write_text("print('seed')\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "seed")
    return r


def _run_cmd_over(repo: Path):
    """Real git, except the two calls that would reach a network or a branch we do not want.

    Everything the defect depends on — status, add, commit, rev-parse, diff — runs for
    real, so the shas are real shas and the ordering is the real ordering.
    """

    async def run(cwd, *args, timeout=60, env=None):
        if args[:2] == ("git", "push"):
            return 0, "", ""
        if args[:2] == ("git", "checkout"):
            return 0, "", ""
        proc = subprocess.run(list(args), cwd=str(cwd), capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    return run


def _install(monkeypatch, repo: Path, messages: list[str], verdict_text: str = "APPROVE"):
    monkeypatch.setattr(session_phases, "run_cmd", _run_cmd_over(repo))
    monkeypatch.setattr(session_phases, "em",
                        lambda s, kind, msg="": messages.append(f"{kind}:{msg}"))
    monkeypatch.setattr(session_phases, "_emit_phase_metric", lambda *a, **k: None)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    async def fake_sdk(**kwargs):
        return 0, f"1. nothing material\n\n{verdict_text}\nreads fine", 0.0

    monkeypatch.setattr(session_phases, "_run_claude_via_sdk", fake_sdk)


def _session(repo: Path):
    return types.SimpleNamespace(id="0f1e2d3c4b5a6978", workspace=str(repo))


# ── The P0 itself: a session that produced work must reach the push ───────────

@pytest.mark.asyncio
async def test_session_that_produced_work_is_allowed_to_push(monkeypatch, repo: Path):
    (repo / "feature.py").write_text("def added():\n    return 1\n")

    messages: list[str] = []
    _install(monkeypatch, repo, messages)
    session = _session(repo)

    ok, verdict = await session_phases._phase_adversary(session, 6)
    assert ok is True, "APPROVE must not halt the push"
    # A brand-new file is the whole of this build. `git diff HEAD` never showed
    # untracked files, so this used to skip as SKIP_NO_DIFF — reviewed by nobody.
    assert verdict["verdict"] == "APPROVE", verdict

    _, push_ok = await session_phases._phase_push(session, 6)

    refusals = [m for m in messages if "PUSH REFUSED" in m]
    assert not refusals, f"the gate refused a reviewed build: {refusals}"
    assert push_ok is True

    # The work reached a commit, and the receipt binds to that same commit.
    assert not _git(repo, "status", "--porcelain"), "build output was left uncommitted"
    assert board_review.check(repo, _git(repo, "rev-parse", "HEAD")).allowed is True


# ── Negative control: the same path must still refuse a post-review change ────

@pytest.mark.asyncio
async def test_refuses_when_code_changes_after_the_review(monkeypatch, repo: Path):
    (repo / "feature.py").write_text("def added():\n    return 1\n")

    messages: list[str] = []
    _install(monkeypatch, repo, messages)
    session = _session(repo)

    ok, _ = await session_phases._phase_adversary(session, 6)
    assert ok is True

    # Someone slips one more small fix in after the reviewer has signed off.
    (repo / "feature.py").write_text("def added():\n    return 2\n")
    _git(repo, "commit", "-qam", "one more small fix")

    _, push_ok = await session_phases._phase_push(session, 6)

    assert push_ok is False
    assert any("PUSH REFUSED" in m for m in messages), messages


# ── A BLOCK verdict still leaves no receipt, so the push has nothing to match ─

@pytest.mark.asyncio
async def test_block_verdict_leaves_no_receipt(monkeypatch, repo: Path):
    (repo / "feature.py").write_text("def added():\n    return 1\n")

    messages: list[str] = []
    _install(monkeypatch, repo, messages, verdict_text="BLOCK")
    session = _session(repo)

    ok, _ = await session_phases._phase_adversary(session, 6)
    assert ok is False
    assert board_review.receipt_path(repo).exists() is False
