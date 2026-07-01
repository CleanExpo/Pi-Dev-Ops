"""Dry-run spec pipeline integration tests."""
from __future__ import annotations

import pytest

from app.server.spec_pipeline.prebuild_judge import EvidenceRow, JudgeReport


@pytest.mark.asyncio
async def test_pipeline_dry_run_blocked_on_boundary(monkeypatch):
    from app.server.spec_pipeline import run_pipeline

    result = await run_pipeline(
        "Modify app/server/config.py password hash rotation",
        dry_run=True,
    )
    assert result.status == "blocked"
    assert "boundary" in result.reason


@pytest.mark.asyncio
async def test_pipeline_blocked_persists_stages_in_meta(monkeypatch):
    from app.server.spec_pipeline import run_pipeline
    from app.server.spec_pipeline import persistence as persist

    result = await run_pipeline("str", dry_run=True)
    assert result.status == "blocked"
    meta = persist.read_json(result.pipeline_id, "meta.json")
    assert meta is not None
    assert meta.get("reason", "").startswith("proposal validation")
    stages = meta.get("stages") or []
    assert any(s.get("stage") == "proposal_validator" for s in stages)


@pytest.mark.asyncio
async def test_pipeline_dry_run_happy_path(monkeypatch):
    from app.server.spec_pipeline import run_pipeline

    async def fake_evidence(proposal):
        return [EvidenceRow(claim="skill exists", status="SUPPORTED", source_title="skills/judge/SKILL.md")]

    async def fake_liaison(pipeline_id, proposal, evidence, *, repo_context, stages):
        report = JudgeReport(
            proposal=proposal, score=100, decision="APPROVE_BUILD",
            evidence=evidence,
        )
        stages.append({"stage": "judge", "status": "ok", "score": 100})
        return proposal, report, [report], evidence

    async def fake_spm(proposal, judge_report):
        from app.server.spec_pipeline.spm_runner import SpmSpec
        return SpmSpec(markdown="# spec\n", goal_command="/goal ship panel")

    async def fake_boardroom(**_kwargs):
        from app.server.spec_pipeline.boardroom import BoardroomResponse
        return BoardroomResponse(
            answer='yes\n{"decision":"APPROVE_BUILD","confidence":0.95}',
            decision="APPROVE_BUILD",
            confidence=0.95,
            min_pairwise_similarity=0.8,
        )

    monkeypatch.setattr("app.server.spec_pipeline.gather_evidence", fake_evidence)
    monkeypatch.setattr("app.server.spec_pipeline.judge_with_liaison", fake_liaison)
    monkeypatch.setattr("app.server.spec_pipeline.run_spm", fake_spm)
    monkeypatch.setattr("app.server.spec_pipeline.boardroom_query", fake_boardroom)

    result = await run_pipeline("Add Mission Control dry-run spec panel", dry_run=True)
    assert result.status == "dry_complete"
    assert result.judge_score == 100
    assert result.boardroom_decision == "APPROVE_BUILD"
