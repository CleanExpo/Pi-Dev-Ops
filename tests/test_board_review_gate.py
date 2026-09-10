"""Unit 2 — the board-review push gate, proven red before it is trusted green.

PR #741 merged carrying two P1 defects because a FAIL verdict never reached the
merge decision. A commit status cannot block a merge on this repo's plan tier, so
the gate is placed in `_phase_push` instead, where a refusal actually stops a push.

Every test here asserts a REFUSAL first. A gate that has only ever been observed
passing is worth nothing (rules/truth-hacking.md, Law 1) — so the four scenarios
below are the four ways this gate must say no, plus the one way it may say yes.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from app.server import board_review


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True,
    ).stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A real git repo — the gate reads real shas, so a fake one would not exercise it."""
    r = tmp_path / "ws"
    r.mkdir()
    _git(r.parent, "init", "-q", str(r))
    _git(r, "config", "user.email", "t@example.invalid")
    _git(r, "config", "user.name", "T")
    (r / "a.txt").write_text("one\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "first")
    return r


def head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD")


# ── RED 1: no receipt at all ─────────────────────────────────────────────────

def test_refuses_when_no_receipt_exists(repo: Path):
    result = board_review.check(repo, head(repo))
    assert result.allowed is False
    assert "no board-review receipt" in result.reason


# ── RED 2: receipt binds to a different (stale) sha ──────────────────────────

def test_refuses_when_receipt_binds_to_a_stale_sha(repo: Path):
    stale = head(repo)
    board_review.write_receipt(repo, stale, "APPROVE", session_id="s1")

    # move HEAD on
    (repo / "b.txt").write_text("two\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "second")
    current = head(repo)
    assert current != stale, "control: the second commit must change HEAD"

    result = board_review.check(repo, current)
    assert result.allowed is False
    assert stale[:12] in result.reason and current[:12] in result.reason


# ── GREEN: receipt binds to HEAD and approves ────────────────────────────────

def test_allows_when_receipt_binds_to_head(repo: Path):
    sha = head(repo)
    board_review.write_receipt(repo, sha, "APPROVE", session_id="s1")

    result = board_review.check(repo, sha)
    assert result.allowed is True, result.reason
    assert sha[:12] in result.reason


# ── RED 3: amending after a receipt must refuse again ────────────────────────
# This is the ordinary shape of "one more small fix before pushing", and it is
# the case a receipt without a sha binding would silently wave through.

def test_refuses_again_after_the_reviewed_commit_is_amended(repo: Path):
    sha = head(repo)
    board_review.write_receipt(repo, sha, "APPROVE", session_id="s1")
    assert board_review.check(repo, sha).allowed is True, "control: green before the amend"

    (repo / "a.txt").write_text("one and a half\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--amend", "--no-edit")
    amended = head(repo)
    assert amended != sha, "control: --amend must change HEAD"

    result = board_review.check(repo, amended)
    assert result.allowed is False
    assert "changed after it was reviewed" in result.reason


# ── RED 4: fail-closed on every unusable receipt ─────────────────────────────

@pytest.mark.parametrize(
    "body,expect",
    [
        ("not json at all", "unreadable"),
        ("[1,2,3]", "unreadable"),
        (json.dumps({"verdict": "APPROVE"}), "binds to nothing"),
        (json.dumps({"head_sha": "SHA", "verdict": "BLOCK"}), "does not permit"),
        (json.dumps({"head_sha": "SHA", "verdict": ""}), "does not permit"),
        (json.dumps({"head_sha": "SHA", "verdict": "LGTM"}), "does not permit"),
    ],
)
def test_refuses_on_unusable_receipt(repo: Path, body: str, expect: str):
    sha = head(repo)
    path = board_review.receipt_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.replace("SHA", sha), encoding="utf-8")

    result = board_review.check(repo, sha)
    assert result.allowed is False
    assert expect in result.reason


def test_refuses_when_head_sha_is_unknown(repo: Path):
    board_review.write_receipt(repo, head(repo), "APPROVE")
    result = board_review.check(repo, "")
    assert result.allowed is False


# ── The negative control on the whole suite ──────────────────────────────────
# If `check` were replaced by `lambda *_: GateResult(True, "")`, every RED test
# above fails. If it were `GateResult(False, "")`, the GREEN test fails. So the
# suite cannot pass against a constant-verdict gate in either direction.

def test_gate_is_not_constant(repo: Path):
    sha = head(repo)
    denied = board_review.check(repo, sha)
    board_review.write_receipt(repo, sha, "APPROVE")
    allowed = board_review.check(repo, sha)
    assert denied.allowed is False and allowed.allowed is True, (
        "the gate returned the same verdict for a missing and a valid receipt — "
        "it is not discriminating and every other test here is vacuous"
    )
