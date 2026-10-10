"""Dry-run spec pipeline integration tests."""
from __future__ import annotations

import pytest
from types import SimpleNamespace
from pathlib import Path

from app.server.spec_pipeline.prebuild_judge import EvidenceRow, JudgeReport, NonBlockingGap
from app.server.spec_pipeline import _repo_context as actual_repo_context


@pytest.fixture(autouse=True)
def isolated_metadata(monkeypatch, tmp_path):
    from app.server import spec_pipeline as pipeline
    from app.server.spec_pipeline import persistence as persist

    monkeypatch.setattr(persist, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(persist, "PIPELINES_ROOT", tmp_path / ".harness" / "spec-pipelines")
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "_repo_context", lambda **_k: "offline test context")
    monkeypatch.setattr(pipeline, "_log_machine_gate", lambda *_a: None)


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
    assert meta["judge_score"] == 0
    assert meta["judge_status"] == "NOT CHECKED"
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


@pytest.fixture
def pipeline_case(monkeypatch, tmp_path):
    from app.server import spec_pipeline as pipeline
    from app.server.spec_pipeline import persistence as persist
    from app.server.spec_pipeline.spm_runner import SpmSpec

    monkeypatch.setattr(persist, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(persist, "PIPELINES_ROOT", tmp_path / ".harness" / "spec-pipelines")
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)

    report = JudgeReport(
        "Add an offline receipt panel", 95, "APPROVE_BUILD",
        evidence=[EvidenceRow("existing gate", status="SUPPORTED")],
        nonblocking_gaps=[NonBlockingGap("receipt clarity", "implementer", "clarify", "PLANNED: check", "ux_clarity")],
    )
    state = {"report": report, "board": "APPROVE_BUILD", "diff": "allowed",
             "review": "PASS", "ship": "merged", "actions": [], "gate_logs": []}

    async def evidence(*_a, **_k):
        return report.evidence

    async def liaison(*_a, stages, **_k):
        stages.append({"stage": "judge", "score": report.score})
        return report.proposal, report, [report], report.evidence

    async def spm(*_a, **_k):
        state["actions"].append("spm")
        return SpmSpec("# offline spec", "/goal verify offline receipt")

    async def board(**_k):
        return SimpleNamespace(decision=state["board"], min_pairwise_similarity=0.8,
                               escalated=False, to_dict=lambda: {"decision": state["board"]})

    async def build(**_k):
        state["actions"].append("build")
        return SimpleNamespace(done=True, reason="mocked", iters=1, cost_usd=0.0)

    def review(*_a, **_k):
        state["actions"].append("review")
        return SimpleNamespace(verdict=state["review"], blockers=["mocked oracle failure"],
                               to_dict=lambda: {"verdict": state["review"]})

    def ship(**_k):
        state["actions"].append("ship")
        return {"status": state["ship"], "pr_url": "https://example.invalid/offline-fixture"}

    def fake_git(argv, **_kwargs):
        state["actions"].append(tuple(argv))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(pipeline, "gather_evidence", evidence)
    monkeypatch.setattr(pipeline, "judge_with_liaison", liaison)
    monkeypatch.setattr(pipeline, "run_spm", spm)
    monkeypatch.setattr(pipeline, "boardroom_query", board)
    monkeypatch.setattr(pipeline, "run_until_done", build)
    monkeypatch.setattr(pipeline, "scan_diff_boundary", lambda _p: SimpleNamespace(
        tier=state["diff"], blocked_paths=["app/server/config.py"]))
    monkeypatch.setattr(pipeline, "run_oracles", lambda _p: {"pytest_ok": state["review"] == "PASS"})
    monkeypatch.setattr(pipeline, "run_review", review)
    monkeypatch.setattr(pipeline, "open_pr_and_merge", ship)
    monkeypatch.setattr(pipeline, "machine_ship_enabled", lambda: True)
    monkeypatch.setattr(pipeline, "resolve_planner_loop_kwargs", lambda: {})
    monkeypatch.setattr(pipeline.subprocess, "run", fake_git)
    monkeypatch.setattr(pipeline.shutil, "copytree", lambda _src, dest, **_k: Path(dest).mkdir(parents=True))
    monkeypatch.setattr(pipeline, "_log_machine_gate", lambda _pid, gates, score: state["gate_logs"].append((gates, score)))
    monkeypatch.setenv("TAO_WORKSPACE", str(tmp_path / "workspaces"))
    monkeypatch.setenv("GITHUB_TOKEN", "")
    return pipeline, persist, state, tmp_path


@pytest.mark.asyncio
@pytest.mark.parametrize("score", [95, 99])
@pytest.mark.parametrize("outcome", ["dry", "ship_mode_off", "board", "diff", "review", "ship_blocked", "complete"])
async def test_actual_score_and_deductions_survive_all_downstream_paths(pipeline_case, monkeypatch, score, outcome):
    pipeline, persist, state, root = pipeline_case
    state["report"].score = score
    if outcome == "ship_mode_off":
        monkeypatch.setattr(pipeline, "machine_ship_enabled", lambda: False)
    elif outcome == "board":
        state["board"] = "REJECT"
    elif outcome == "diff":
        state["diff"] = "blocked"
    elif outcome == "review":
        state["review"] = "BLOCKED"
    elif outcome == "ship_blocked":
        state["ship"] = "blocked"
    result = await pipeline.run_pipeline(state["report"].proposal, pipeline_id="case", dry_run=outcome == "dry")
    expected = {"dry": "dry_complete", "ship_mode_off": "dry_complete", "board": "blocked",
                "diff": "blocked", "review": "blocked", "ship_blocked": "ship_blocked", "complete": "complete"}
    assert result.status == expected[outcome]
    assert result.judge_score == result.to_dict()["judge_score"] == score
    records = state["report"].to_dict()["nonblocking_gaps"]
    assert result.to_dict()["nonblocking_gaps"] == records
    meta = persist.read_json("case", "meta.json")
    assert meta["judge_score"] == score
    assert meta["nonblocking_gaps"] == records
    handoff = (root / ".harness/spec-pipelines/case/08-handoff.md").read_text()
    assert f"**Judge score:** {score}" in handoff
    for gap in records:
        assert all(value in handoff for value in gap.values())
    assert state["gate_logs"][0][0]["machine_judge_approved"] is True
    assert "machine_judge_100" not in state["gate_logs"][0][0]
    assert all(log_score == float(score) for _checks, log_score in state["gate_logs"])
    if outcome in ("dry", "ship_mode_off", "board"):
        assert "build" not in state["actions"]
    if outcome not in ("complete", "ship_blocked"):
        assert "ship" not in state["actions"]


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"score": 94}, {"honest_ceiling": True}, {"gaps": ["must_fix"]},
    {"evidence": []}, {"nonblocking_gaps": []},
])
async def test_pipeline_uses_same_blocking_predicate_before_spm_or_board(pipeline_case, changes):
    pipeline, persist, state, root = pipeline_case
    for key, value in changes.items():
        setattr(state["report"], key, value)
    result = await pipeline.run_pipeline(state["report"].proposal, pipeline_id="blocked", dry_run=True)
    assert result.status == "blocked"
    assert result.judge_score == state["report"].score
    assert persist.read_json("blocked", "meta.json")["judge_score"] == result.judge_score
    assert f"**Judge score:** {result.judge_score}" in (root / ".harness/spec-pipelines/blocked/08-handoff.md").read_text()
    assert state["actions"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("score", [85, 94, 95, 100])
@pytest.mark.parametrize("dry_run", [True, False])
async def test_development_packet_never_enters_builder_or_shipping(pipeline_case, monkeypatch, score, dry_run):
    pipeline, persist, state, root = pipeline_case
    state["report"].score = score
    state["report"].decision = "APPROVE_EXPERIMENT"
    if score == 100:
        state["report"].nonblocking_gaps = []
    monkeypatch.setenv("TAO_MACHINE_SHIP_MODE", "1")

    def forbidden(*_a, **_k):
        raise AssertionError("development preparation must not reach execution")

    for name in ("machine_ship_enabled", "run_until_done", "run_oracles", "run_review",
                 "scan_diff_boundary", "open_pr_and_merge", "resolve_planner_loop_kwargs"):
        monkeypatch.setattr(pipeline, name, forbidden)
    monkeypatch.setattr(pipeline.subprocess, "run", forbidden)
    monkeypatch.setattr(pipeline.shutil, "copytree", forbidden)
    monkeypatch.setattr(pipeline.shutil, "rmtree", forbidden)
    result = await pipeline.run_pipeline(state["report"].proposal, pipeline_id="dev",
                                         stage="development", dry_run=dry_run)
    assert result.status == "development_ready"
    assert result.stage == "development" and result.approval_floor == 85
    assert result.judge_score == score
    assert result.nonblocking_gaps == state["report"].to_dict()["nonblocking_gaps"]
    assert state["actions"] == ["spm"]
    assert state["gate_logs"][0][0]["machine_judge_approved"] is (score >= 95)
    meta = persist.read_json("dev", "meta.json")
    assert meta["stage"] == "development" and meta["approval_floor"] == 85
    assert meta["judge_score"] == score and meta["nonblocking_gaps"] == result.nonblocking_gaps
    assert meta["implementation_executed"] is False and meta["promotion_performed"] is False
    handoff = (root / ".harness/spec-pipelines/dev/08-handoff.md").read_text()
    assert "**Requested stage:** development" in handoff
    assert "**Stage floor / quality target:** 85 / 100" in handoff
    assert "no SDK implementation executed" in handoff
    assert f"**Judge score:** {score}" in handoff


@pytest.mark.asyncio
@pytest.mark.parametrize("score", [84, 85, 94])
async def test_default_promotion_keeps_95_floor(pipeline_case, score):
    pipeline, persist, state, _root = pipeline_case
    state["report"].score = score
    result = await pipeline.run_pipeline(state["report"].proposal, pipeline_id="promotion")
    assert result.status == "blocked"
    assert result.stage == "promotion" and result.approval_floor == 95
    assert persist.read_json("promotion", "meta.json")["approval_floor"] == 95
    assert state["actions"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["unknown", None, True, 85])
async def test_unknown_stage_has_no_persistence_or_external_effect(pipeline_case, monkeypatch, stage):
    pipeline, persist, state, root = pipeline_case

    def forbidden(*_a, **_k):
        raise AssertionError("invalid stage must fail before persistence")

    monkeypatch.setattr(persist, "new_pipeline_id", forbidden)
    monkeypatch.setattr(persist, "write_text", forbidden)
    monkeypatch.setattr(persist, "write_json", forbidden)
    with pytest.raises(ValueError):
        await pipeline.run_pipeline("Add an offline packet", stage=stage)
    assert state["actions"] == []
    assert not (root / ".harness").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"score": 84}, {"gaps": ["must_fix"]},
                                    {"honest_ceiling": True}, {"evidence": []},
                                    {"nonblocking_gaps": []}])
async def test_development_blocked_paths_preserve_stage_and_score(pipeline_case, changes):
    pipeline, persist, state, root = pipeline_case
    state["report"].score = 85
    for name, value in changes.items():
        setattr(state["report"], name, value)
    result = await pipeline.run_pipeline(state["report"].proposal, pipeline_id="dev-blocked",
                                         stage="development")
    assert result.status == "blocked" and state["actions"] == []
    assert result.stage == "development" and result.approval_floor == 85
    meta = persist.read_json("dev-blocked", "meta.json")
    assert meta["stage"] == result.stage and meta["judge_score"] == result.judge_score
    assert "**Requested stage:** development" in (root / ".harness/spec-pipelines/dev-blocked/08-handoff.md").read_text()


def test_development_context_does_not_invoke_git(monkeypatch, tmp_path):
    from app.server import spec_pipeline as pipeline
    (tmp_path / "README.md").write_text("offline context")
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)

    def forbidden(*_a, **_k):
        raise AssertionError("development context must not invoke Git")

    monkeypatch.setattr(pipeline.subprocess, "run", forbidden)
    assert "offline context" in actual_repo_context(include_git=False)
