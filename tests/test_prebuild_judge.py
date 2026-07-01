"""Tests for prebuild judge scoring."""
from __future__ import annotations

import pytest

from app.server.spec_pipeline.prebuild_judge import (
    EvidenceRow,
    JudgeReport,
    _decision_for_score,
    _parse_report,
)


def test_decision_for_score_buckets():
    assert _decision_for_score(50) == "REJECT"
    assert _decision_for_score(75) == "REDUCE_SCOPE"
    assert _decision_for_score(90) == "APPROVE_EXPERIMENT"
    assert _decision_for_score(100) == "APPROVE_BUILD"


def test_parse_report_caps_100_with_open_evidence():
    data = {
        "score": 100,
        "category_scores": {},
        "evidence": [{"claim": "x", "status": "NOT CHECKED"}],
        "gaps": [],
        "honest_ceiling": False,
        "ceiling_reason": "",
    }
    report = _parse_report("test proposal", data, 1)
    assert report.score == 99
    assert report.has_open_evidence_gaps()


def test_judge_report_to_dict():
    report = JudgeReport(proposal="p", score=85, decision="APPROVE_EXPERIMENT")
    d = report.to_dict()
    assert d["score"] == 85
    assert d["proposal"] == "p"


@pytest.mark.asyncio
async def test_iterate_to_100_stops_at_ceiling(monkeypatch):
    from app.server.spec_pipeline import prebuild_judge as pj

    async def fake_score(*_a, **_k):
        return JudgeReport(
            proposal="p",
            score=80,
            decision="REDUCE_SCOPE",
            honest_ceiling=True,
            ceiling_reason="cannot verify vendor SLA",
        )

    monkeypatch.setattr(pj, "score_proposal", fake_score)
    final, history = await pj.iterate_to_100("p", evidence=[], repo_context="ctx")
    assert final.honest_ceiling
    assert len(history) == 1
