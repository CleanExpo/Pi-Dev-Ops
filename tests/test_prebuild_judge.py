"""Tests for prebuild judge scoring."""
from __future__ import annotations

import pytest

from app.server.spec_pipeline.prebuild_judge import (
    EvidenceRow,
    JudgeReport,
    NonBlockingGap,
    _decision_for_score,
    _build_prompt,
    _parse_report,
    is_build_approved,
)


def test_decision_for_score_buckets():
    assert _decision_for_score(50) == "REJECT"
    assert _decision_for_score(75) == "REDUCE_SCOPE"
    assert _decision_for_score(90) == "APPROVE_EXPERIMENT"
    assert _decision_for_score(94) == "APPROVE_EXPERIMENT"
    assert _decision_for_score(95) == "APPROVE_BUILD"
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


def deduction(**changes):
    return {
        "name": "Receipt presentation", "owner": "implementer",
        "closure_action": "Clarify the receipt", "required_evidence": "PLANNED: round-trip check",
        "category": "ux_clarity", **changes,
    }


def payload(score=95, **changes):
    return {
        "score": score, "evidence": [{"claim": "Existing offline gate", "status": "SUPPORTED"}],
        "gaps": [], "nonblocking_gaps": [deduction()] if score < 100 else [],
        "honest_ceiling": False, **changes,
    }


@pytest.mark.parametrize("score,approved", [(94, False), (95, True), (99, True), (100, True)])
def test_shared_floor_and_actual_round_trip(score, approved):
    report = _parse_report("proposal", payload(score), 1)
    assert report.score == score
    assert is_build_approved(report) is approved
    restored = _parse_report("proposal", report.to_dict(), 2)
    assert restored.score == score
    assert is_build_approved(restored) is approved
    assert restored.to_dict()["nonblocking_gaps"] == report.to_dict()["nonblocking_gaps"]


@pytest.mark.parametrize("category", ["clear_problem", "reuse_existing", "ux_clarity", "testability"])
def test_closed_noncritical_categories(category):
    assert is_build_approved(_parse_report("p", payload(nonblocking_gaps=[deduction(category=category)]), 1))


@pytest.mark.parametrize("category", [
    "first_source_evidence", "security_privacy", "cost_simplicity", "billing", "spend",
    "workspace", "authority", "isolation", "rollback", "irreversibility", "must_fix", "other",
])
def test_mandatory_and_unknown_deductions_cannot_be_reclassified(category):
    report = _parse_report("p", payload(nonblocking_gaps=[deduction(category=category)]), 1)
    assert not is_build_approved(report)
    assert report.gaps


@pytest.mark.parametrize("field", ["name", "owner", "closure_action", "required_evidence", "category"])
@pytest.mark.parametrize("bad", [None, "", "  ", 3, [], {}])
def test_nonblocking_records_require_all_nonblank_string_fields(field, bad):
    report = _parse_report("p", payload(nonblocking_gaps=[deduction(**{field: bad})]), 1)
    assert not is_build_approved(report)
    assert report.gaps


@pytest.mark.parametrize("records", [None, {}, "gap", ["gap"], [deduction(must_fix=True)]])
def test_nonblocking_malformed_or_extra_fields_block(records):
    report = _parse_report("p", payload(nonblocking_gaps=records), 1)
    assert not is_build_approved(report)
    assert report.gaps


@pytest.mark.parametrize("field", ["name", "owner", "closure_action", "required_evidence", "category"])
def test_missing_deduction_field_blocks(field):
    row = deduction()
    del row[field]
    assert not is_build_approved(_parse_report("p", payload(nonblocking_gaps=[row]), 1))


@pytest.mark.parametrize("score", [95, 99])
def test_deductions_cannot_be_omitted_below_target(score):
    assert not is_build_approved(_parse_report("p", payload(score, nonblocking_gaps=[]), 1))


@pytest.mark.parametrize("score", [95, 100])
@pytest.mark.parametrize("status", ["PARTIAL", "CONFLICTING", "UNSUPPORTED", "NOT CHECKED", "unknown", None])
def test_all_unproven_evidence_statuses_block_at_every_approval_score(score, status):
    report = _parse_report("p", payload(score, evidence=[{"claim": "gate", "status": status}]), 1)
    assert not is_build_approved(report)
    assert report.decision != "APPROVE_BUILD"


@pytest.mark.parametrize("score", [95, 100])
@pytest.mark.parametrize("rows", [
    [], None, {}, "evidence", [None], ["claim"], [{"claim": "gate"}],
    [{"claim": "", "status": "SUPPORTED"}], [{"claim": 5, "status": "SUPPORTED"}],
    [{"claim": "gate", "status": "SUPPORTED", "source_url": None}],
    [{"claim": "gate", "status": "SUPPORTED"}, {"claim": "bad", "status": "SUPPORTED", "unknown": True}],
])
def test_empty_malformed_and_mixed_evidence_never_disappears_into_approval(score, rows):
    report = _parse_report("p", payload(score, evidence=rows), 1)
    assert not is_build_approved(report)
    assert report.gaps


@pytest.mark.parametrize("score", [95, 100])
@pytest.mark.parametrize("changes", [{"gaps": ["must_fix"]}, {"honest_ceiling": True}, {"gaps": {}}])
def test_legacy_gaps_and_explicit_ceiling_block(score, changes):
    assert not is_build_approved(_parse_report("p", payload(score, **changes), 1))


def test_inconsistent_hundred_is_capped_and_blocked():
    report = _parse_report("p", payload(100, nonblocking_gaps=[deduction()]), 1)
    assert report.score == 99
    assert report.gaps
    assert not is_build_approved(report)


@pytest.mark.parametrize("score", [True, None, "95", 95.0, -1, 101])
def test_invalid_score_is_not_coerced_into_approval(score):
    data = payload()
    data["score"] = score
    report = _parse_report("p", data, 1)
    assert report.score == 0
    assert not is_build_approved(report)
    assert report.gaps


def test_gap_dataclass_round_trip_and_unknown_top_level_hard_record():
    assert NonBlockingGap(**deduction()).to_dict() == deduction()
    report = _parse_report("p", payload(must_fix=["privacy"]), 1)
    assert report.gaps
    assert not is_build_approved(report)


def test_prompt_preserves_floor_target_and_planned_evidence_boundary():
    prompt = _build_prompt("Add an offline receipt", [], "ctx", 1)
    assert "Approval floor 95; quality target 100" in prompt
    assert "planned tests are never passed evidence" in prompt
    assert "must_fix gaps block at every score" in prompt
    assert "nonblocking_gaps" in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("scores", [[95, 95, 95], [95, 99, 100]])
async def test_iterations_pursue_target_without_inventing_ceiling(monkeypatch, scores):
    from app.server.spec_pipeline import prebuild_judge as pj
    calls = []

    async def fake_score(*_a, **kwargs):
        calls.append(kwargs["iteration"])
        return _parse_report("p", payload(scores[len(calls) - 1]), len(calls))

    monkeypatch.setattr(pj, "score_proposal", fake_score)
    final, history = await pj.iterate_to_100("p", evidence=[], repo_context="ctx", max_iters=3)
    assert calls == [1, 2, 3]
    assert len(history) == 3
    assert final.score == scores[-1]
    assert final.decision == "APPROVE_BUILD"
    assert not final.honest_ceiling


@pytest.mark.asyncio
async def test_explicit_ceiling_remains_blocking_at_qualified_numeric_score(monkeypatch):
    from app.server.spec_pipeline import prebuild_judge as pj

    async def fake_score(*_a, **_k):
        return _parse_report("p", payload(honest_ceiling=True), 1)

    monkeypatch.setattr(pj, "score_proposal", fake_score)
    final, history = await pj.iterate_to_100("p", evidence=[], repo_context="ctx", max_iters=3)
    assert len(history) == 1
    assert final.honest_ceiling
    assert not is_build_approved(final)
