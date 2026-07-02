"""Tests for judge ↔ board ↔ SPM liaison loop."""
from __future__ import annotations

import pytest

from app.server.spec_pipeline.liaison_loop import judge_with_liaison, merge_evidence
from app.server.spec_pipeline.prebuild_judge import EvidenceRow, JudgeReport
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
