"""Tests for app/server/board_decision_index.py (RA-6907)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.server.board_decision_index import (
    BoardCorpusMissingError,
    BoardDecision,
    build_decision_index,
    check_mandate_consistency,
)


SAMPLE_VOTE = """\
# Activation Vote

## Conditions Locked

### 1. OB-4 — CARSI ADMIN_PASSWORD (OPS veto gate)
- **Status:** OPEN
- Full swarm activation blocked until closed.

### 2. Rate limit — 3 autonomous PRs/day (CONTRARIAN)
- **Status:** IMPLEMENTED — `MAX_AUTONOMOUS_PRS_PER_DAY=3`
- **Lift condition:** 20 consecutive green supervised merges
"""


def test_build_decision_index_from_locked_section(tmp_path: Path):
    meetings = tmp_path / "board-meetings"
    meetings.mkdir()
    (meetings / "2026-04-15-activation-vote.md").write_text(SAMPLE_VOTE, encoding="utf-8")

    index = build_decision_index(meetings)
    assert len(index) == 2
    assert any("Rate limit" in d.title for d in index)


def test_contradictory_mandate_rejected(tmp_path: Path):
    meetings = tmp_path / "board-meetings"
    meetings.mkdir()
    (meetings / "vote.md").write_text(SAMPLE_VOTE, encoding="utf-8")

    result = check_mandate_consistency(
        "Remove the 3 autonomous PR per day rate limit and allow unlimited merges.",
        meetings_dir=meetings,
    )
    assert result.allowed is False
    assert result.contradictions
    assert "Rate limit" in result.contradictions[0]["title"]


def test_consistent_mandate_allowed():
    decision = BoardDecision(
        decision_id="test:rate",
        title="Rate limit — 3 autonomous PRs/day",
        body="MAX_AUTONOMOUS_PRS_PER_DAY=3",
        source_file="vote.md",
        keywords=["rate", "limit", "autonomous", "prs", "day", "max_autonomous_prs_per_day"],
    )
    result = check_mandate_consistency(
        "Fix the evaluator threshold for autonomous PRs to improve quality.",
        index=[decision],
    )
    assert result.allowed is True


def test_missing_meetings_dir_raises(tmp_path: Path):
    """An absent corpus directory must refuse, not return an empty index.

    Replaces test_missing_meetings_dir_returns_empty, which pinned the defect:
    it asserted the fail-OPEN branch was working as designed. Returning [] from
    an absent corpus is indistinguishable, at every call site, from a corpus that
    genuinely locks nothing — and the only consumer treats an empty index as
    "no contradictions found", i.e. approval.
    """
    with pytest.raises(BoardCorpusMissingError, match="does-not-exist"):
        build_decision_index(tmp_path / "does-not-exist")


def test_present_but_empty_corpus_raises(tmp_path: Path):
    """Existence is not enough — a corpus yielding zero decisions is still absent.

    Same lesson as config_loader.validate_startup, which parses the NotebookLM
    registry rather than settling for is_file(). A directory of markdown with no
    `## Conditions Locked` section produces the identical empty index, and so the
    identical silent approval.
    """
    meetings = tmp_path / "board-meetings"
    meetings.mkdir()
    (meetings / "notes.md").write_text("# Board notes\n\nNothing locked.\n", encoding="utf-8")

    with pytest.raises(BoardCorpusMissingError, match="no locked decisions"):
        build_decision_index(meetings)


def test_mandate_not_approved_when_corpus_absent(tmp_path: Path):
    """The defect itself, stated behaviourally.

    Before the fix this returned allowed=True: a mandate explicitly overturning a
    locked condition sailed through because the corpus directory was not in the
    image. The gate must refuse to answer rather than answer "yes".
    """
    overturning = "Remove the 3 autonomous PR per day rate limit and allow unlimited merges."
    with pytest.raises(BoardCorpusMissingError):
        check_mandate_consistency(overturning, meetings_dir=tmp_path / "absent")


def test_explicit_empty_index_refuses():
    """The same hole one call away: an explicitly-passed empty index.

    check_mandate_consistency's caller builds the index separately and passes it
    in, so a [] that never went through build_decision_index would bypass the
    guard above and approve everything.
    """
    with pytest.raises(BoardCorpusMissingError):
        check_mandate_consistency("Remove the rate limit entirely.", index=[])
