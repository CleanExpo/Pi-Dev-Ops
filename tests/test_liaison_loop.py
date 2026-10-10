"""Tests for judge ↔ board ↔ SPM liaison loop."""
from __future__ import annotations

import pytest

from app.server.spec_pipeline.liaison_loop import judge_with_liaison, merge_evidence
from app.server.spec_pipeline.prebuild_judge import EvidenceRow, JudgeReport, NonBlockingGap
from app.server.spec_pipeline.spm_runner import SpmSpec


def test_merge_evidence_overrides_claim():
    a = EvidenceRow(claim="auth gated", status="NOT CHECKED")
    b = EvidenceRow(claim="auth gated", status="SUPPORTED", source_title="test.py")
    merged = merge_evidence([a], [b])
    assert len(merged) == 1
    assert merged[0].status == "SUPPORTED"


@pytest.mark.asyncio
async def test_liaison_loop_reaches_100_after_one_round(monkeypatch, tmp_path):
    from app.server.spec_pipeline import liaison_loop as ll
    from app.server.spec_pipeline import persistence as persist

    monkeypatch.setattr(persist, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(persist, "PIPELINES_ROOT", tmp_path / ".harness" / "spec-pipelines")
    (tmp_path / ".harness" / "spec-pipelines").mkdir(parents=True)

    calls = {"judge": 0}

    async def fake_iterate(proposal, *, evidence, repo_context, max_iters=5):
        calls["judge"] += 1
        if calls["judge"] == 1:
            report = JudgeReport(
                proposal=proposal, score=80, decision="REDUCE_SCOPE",
                gaps=["scope too wide"],
            )
            return report, [report]
        report = JudgeReport(
            proposal=proposal, score=100, decision="APPROVE_BUILD",
            evidence=[EvidenceRow(claim="scoped", status="SUPPORTED")],
        )
        return report, [report]

    async def fake_board(*_a, **_k):
        from app.server.spec_pipeline.ceo_board_liaison import BoardLiaisonResult, GapResolution
        return BoardLiaisonResult(
            memo="memo",
            decision="REDUCE_SCOPE",
            proceed=True,
            refined_proposal="Narrow scope to status chip",
            gap_resolutions=[GapResolution("scope too wide", "poll only")],
            new_evidence=[EvidenceRow(claim="scoped", status="SUPPORTED")],
        )

    async def fake_spm(*_a, **_k):
        return SpmSpec(
            markdown="REFINED_PROPOSAL: Narrow scope to status chip\n",
            goal_command="/goal chip ships",
        )

    monkeypatch.setattr(ll, "iterate_to_100", fake_iterate)
    monkeypatch.setattr(ll, "run_ceo_board_liaison", fake_board)
    monkeypatch.setattr(ll, "run_spm_gap_resolution", fake_spm)

    stages: list = []
    proposal, final, _hist, _ev = await judge_with_liaison(
        "spec-test123",
        "Add big panel",
        [],
        repo_context="ctx",
        stages=stages,
    )
    assert final.score == 100
    assert "Narrow" in proposal
    assert any(s.get("stage") == "ceo_board_liaison" for s in stages)


@pytest.mark.asyncio
@pytest.mark.parametrize("score", [95, 99])
async def test_qualified_floor_preserves_score_and_persisted_deductions(monkeypatch, tmp_path, score):
    from app.server.spec_pipeline import liaison_loop as ll
    from app.server.spec_pipeline import persistence as persist

    monkeypatch.setattr(persist, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(persist, "PIPELINES_ROOT", tmp_path / ".harness" / "spec-pipelines")
    report = JudgeReport(
        "proposal", score, "APPROVE_BUILD",
        evidence=[EvidenceRow("existing gate", status="SUPPORTED")],
        nonblocking_gaps=[NonBlockingGap("receipt clarity", "implementer", "clarify", "PLANNED: check", "ux_clarity")],
    )

    async def fake_iterate(*_a, **_k):
        return report, [report]

    async def forbidden_board(*_a, **_k):
        raise AssertionError("qualified bounded judge needs no extra board liaison")

    monkeypatch.setattr(ll, "iterate_to_100", fake_iterate)
    monkeypatch.setattr(ll, "run_ceo_board_liaison", forbidden_board)
    stages = []
    _, final, _, _ = await ll.judge_with_liaison("floor", "proposal", [], repo_context="ctx", stages=stages)
    assert final.score == score
    assert stages[-1]["score"] == score
    assert stages[-1]["status"] == "ok"
    stored = persist.read_json("floor", "02-judge-iter-1.json")
    assert stored["score"] == score
    assert stored["nonblocking_gaps"] == report.to_dict()["nonblocking_gaps"]


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"score": 94}, {"honest_ceiling": True}, {"gaps": ["must_fix"]},
    {"evidence": []}, {"nonblocking_gaps": []},
])
async def test_liaison_does_not_bypass_shared_blockers(monkeypatch, tmp_path, changes):
    from app.server.spec_pipeline import liaison_loop as ll
    from app.server.spec_pipeline import persistence as persist

    monkeypatch.setattr(persist, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(persist, "PIPELINES_ROOT", tmp_path / ".harness" / "spec-pipelines")
    monkeypatch.setenv("TAO_SPEC_LIAISON_ROUNDS", "0")
    fields = dict(
        proposal="proposal", score=95, decision="APPROVE_BUILD",
        evidence=[EvidenceRow("existing gate", status="SUPPORTED")],
        nonblocking_gaps=[NonBlockingGap("receipt", "implementer", "clarify", "PLANNED: check", "ux_clarity")],
    )
    fields.update(changes)
    report = JudgeReport(**fields)

    async def fake_iterate(*_a, **_k):
        return report, [report]

    monkeypatch.setattr(ll, "iterate_to_100", fake_iterate)
    stages = []
    _, final, _, _ = await ll.judge_with_liaison("blocked", "proposal", [], repo_context="ctx", stages=stages)
    assert stages[-1]["status"] == "ceiling"
    assert stages[-1]["score"] == report.score == final.score


@pytest.mark.asyncio
async def test_board_rejection_still_blocks_before_spm(monkeypatch, tmp_path):
    from app.server.spec_pipeline import liaison_loop as ll
    from app.server.spec_pipeline import persistence as persist
    from app.server.spec_pipeline.ceo_board_liaison import BoardLiaisonResult

    monkeypatch.setattr(persist, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(persist, "PIPELINES_ROOT", tmp_path / ".harness" / "spec-pipelines")
    report = JudgeReport("proposal", 94, "APPROVE_EXPERIMENT", gaps=["scope"],
                         evidence=[EvidenceRow("gate", status="SUPPORTED")])

    async def fake_iterate(*_a, **_k):
        return report, [report]

    async def reject(*_a, **_k):
        return BoardLiaisonResult("reject", "REJECT", False, "proposal")

    async def forbidden_spm(*_a, **_k):
        raise AssertionError("rejected board must not reach SPM")

    monkeypatch.setattr(ll, "iterate_to_100", fake_iterate)
    monkeypatch.setattr(ll, "run_ceo_board_liaison", reject)
    monkeypatch.setattr(ll, "run_spm_gap_resolution", forbidden_spm)
    stages = []
    _, final, _, _ = await ll.judge_with_liaison("rejected", "proposal", [], repo_context="ctx", stages=stages)
    assert final.honest_ceiling
    assert final.score == 94
    assert stages[-1]["status"] == "rejected"
