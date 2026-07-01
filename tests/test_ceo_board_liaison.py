"""Tests for CEO-board liaison adapter."""
from __future__ import annotations

import pytest

from app.server.spec_pipeline.ceo_board_liaison import run_ceo_board_liaison
from app.server.spec_pipeline.prebuild_judge import EvidenceRow, JudgeReport


@pytest.mark.asyncio
async def test_liaison_parses_memo_and_json(monkeypatch):
    from app.server.spec_pipeline import ceo_board_liaison as mod

    async def fake_complete(**_kwargs):
        return (
            "## THE MEMO\nDECISION: REDUCE_SCOPE\n"
            '{"decision":"REDUCE_SCOPE","proceed":true,'
            '"refined_proposal":"Add polling status chip only",'
            '"gap_resolutions":[{"gap":"auth unclear","resolution":"reuse require_auth",'
            '"owner":"Architect"}],'
            '"new_evidence":[{"claim":"auth route gated","source_title":"routes/spec_pipeline.py",'
            '"status":"SUPPORTED"}],"research_gaps":[]}',
            0.01,
        )

    monkeypatch.setattr(mod, "complete", fake_complete)
    report = JudgeReport(
        proposal="Add panel",
        score=71,
        decision="REDUCE_SCOPE",
        gaps=["auth unclear"],
        evidence=[EvidenceRow(claim="auth unclear", status="NOT CHECKED")],
    )
    result = await run_ceo_board_liaison(
        "Add panel", report, evidence=[], repo_context="ctx", round_n=1,
    )
    assert result.proceed is True
    assert result.decision == "REDUCE_SCOPE"
    assert "polling" in result.refined_proposal
    assert len(result.gap_resolutions) == 1
    assert result.new_evidence[0].status == "SUPPORTED"
