"""Tests for app/server/board_decision_index.py (RA-6907)."""
from __future__ import annotations

from pathlib import Path

from app.server.board_decision_index import (
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


def test_real_harness_has_activation_vote_decisions():
    index = build_decision_index()
    assert any("Rate limit" in d.title for d in index)
