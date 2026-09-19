"""Enabled machine pipeline failure injection; all external execution is mocked."""
import asyncio
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.server import spec_pipeline as pipeline
from app.server.spec_pipeline.review_runner import ReviewPacket

_REAL_RUN = subprocess.run


def _plain_git(command):
    index = 1
    while command[index] == "-c":
        index += 2
    return ["git", *command[index:]]


def _fake_git(state, cmd, **kwargs):
    cmd = _plain_git(cmd)
    state.commands.append(cmd)
    if state.fail and state.fail(cmd):
        return subprocess.CompletedProcess(cmd, 1, "", "operation failed")
    if cmd[1] == "clone":
        Path(cmd[-1]).mkdir(parents=True)
    if cmd[1] == "commit":
        state.committed = True
    if cmd[1:3] == ["reset", "--soft"]:
        state.committed = False
    stdout = ""
    if cmd[1] == "write-tree" or cmd[1:] == ["rev-parse", "HEAD^{tree}"]:
        stdout = state.tree
    elif cmd[1:3] == ["rev-parse", "HEAD"]:
        stdout = state.candidate if state.committed else state.base
    elif cmd[1] == "status":
        stdout = " M changed.py" if state.dirty else ""
    return subprocess.CompletedProcess(cmd, 0, stdout, "")


@pytest.fixture
def pipeline_reports(monkeypatch):
    reporter = Mock()
    monkeypatch.setattr(pipeline.linear_reporter, "report", reporter)
    return reporter


@pytest.fixture
def enabled_pipeline(monkeypatch, tmp_path, pipeline_reports):
    root = tmp_path / "source"
    root.mkdir()
    workspace_root = tmp_path / "workspaces"
    monkeypatch.setattr("app.server.session_phases._git_clone_env", lambda remote: {})
    monkeypatch.setattr(pipeline, "REPO_ROOT", root)
    monkeypatch.setenv("TAO_WORKSPACE", str(workspace_root))
    monkeypatch.setattr(pipeline.persist, "PIPELINES_ROOT", tmp_path / "artifacts")
    monkeypatch.setattr(pipeline, "_repo_context", Mock(return_value="repository context"))
    monkeypatch.setattr(pipeline, "machine_ship_enabled", Mock(return_value=True))
    monkeypatch.setattr(pipeline, "resolve_planner_loop_kwargs", lambda: {})
    monkeypatch.setattr(pipeline, "gather_evidence", AsyncMock(return_value=[]))
    judge = SimpleNamespace(score=100, honest_ceiling=False, ceiling_reason="", has_open_evidence_gaps=lambda: False)
    proposal = "Implement candidate-bound delivery evidence for Mission Control"
    monkeypatch.setattr(pipeline, "judge_with_liaison", AsyncMock(return_value=(proposal, judge, [], [])))
    monkeypatch.setattr(pipeline, "run_spm", AsyncMock(return_value=SimpleNamespace(markdown="# spec", goal_command="deliver candidate")))
    board = SimpleNamespace(decision="APPROVE_BUILD", escalated=False, min_pairwise_similarity=0.9, to_dict=lambda: {"decision": "APPROVE_BUILD"})
    monkeypatch.setattr(pipeline, "boardroom_query", AsyncMock(return_value=board))
    loop = AsyncMock(return_value=SimpleNamespace(done=True, reason="done", iters=1, cost_usd=0))
    monkeypatch.setattr(pipeline, "run_until_done", loop)
    boundary = Mock(return_value=SimpleNamespace(tier="ok", blocked_paths=[]))
    monkeypatch.setattr(pipeline, "scan_diff_boundary", boundary)
    oracles = Mock(return_value={"pytest_ok": True, "import_ok": True, "tsc_ok": True})
    monkeypatch.setattr(pipeline, "run_oracles", oracles)
    review = Mock(return_value=ReviewPacket("PASS"))
    monkeypatch.setattr(pipeline, "run_review", review)
    ship = Mock(return_value={"status": "merged", "pr_url": "https://example.test/pull/1", "candidate_sha": "b" * 40, "merge_sha": "c" * 40})
    monkeypatch.setattr(pipeline, "open_pr_and_merge", ship)
    gates = Mock()
    monkeypatch.setattr(pipeline, "_log_machine_gate", gates)
    state = SimpleNamespace(
        proposal=proposal, pipeline_id="spec-test", loop=loop, boundary=boundary,
        oracles=oracles, review=review, ship=ship, gates=gates, reports=pipeline_reports,
        commands=[], fail=None, committed=False, candidate="b" * 40,
        tree="d" * 40, base="a" * 40, dirty=False, workspace_root=workspace_root,
    )

    monkeypatch.setattr(pipeline.subprocess, "run", lambda cmd, **kw: _fake_git(state, cmd, **kw))
    return state


def run(state):
    return asyncio.run(pipeline.run_pipeline(state.proposal, pipeline_id=state.pipeline_id))


def assert_blocked(state, result):
    assert result.status in {"blocked", "ship_blocked"}
    assert result.reason
    state.ship.assert_not_called()
    assert not any(call.args[1].get("shipped") is True for call in state.gates.call_args_list)
    meta = pipeline.persist.read_json(state.pipeline_id, "meta.json")
    assert meta["status"] == result.status


def test_incomplete_loop_stops_before_review_or_ship(enabled_pipeline):
    state = enabled_pipeline
    state.loop.return_value.done = False
    state.loop.return_value.reason = "budget exhausted"
    result = run(state)
    assert_blocked(state, result)
    state.boundary.assert_not_called()
    state.oracles.assert_not_called()
    assert not any(cmd[1] == "push" for cmd in state.commands)


@pytest.mark.parametrize("step", ["clone", "checkout", "add", "write-tree", "commit", "remote", "push"])
def test_git_failure_cannot_report_delivery(enabled_pipeline, step):
    state = enabled_pipeline
    state.fail = lambda cmd: cmd[1] == step
    result = run(state)
    assert_blocked(state, result)


@pytest.mark.parametrize("verdict", ["UNKNOWN", "ERROR", "", "BLOCKED"])
def test_unapproved_review_blocks_shipping(enabled_pipeline, verdict):
    state = enabled_pipeline
    state.review.return_value = ReviewPacket(verdict)
    assert_blocked(state, run(state))


@pytest.mark.parametrize("oracles", [{}, {"pytest_ok": True}, {"pytest_ok": False, "import_ok": True, "tsc_ok": True}])
def test_missing_or_failed_oracles_cannot_be_overridden_by_review(enabled_pipeline, oracles):
    state = enabled_pipeline
    state.oracles.return_value = oracles
    assert_blocked(state, run(state))


def test_reviewed_tree_cannot_change_before_commit(enabled_pipeline):
    state = enabled_pipeline
    def review(*args, **kwargs):
        state.tree = "e" * 40
        return ReviewPacket("PASS")
    state.review.side_effect = review
    assert_blocked(state, run(state))
    assert not any(cmd[1] == "push" for cmd in state.commands)


def test_dirty_candidate_cannot_be_pushed(enabled_pipeline):
    state = enabled_pipeline
    state.dirty = True
    assert_blocked(state, run(state))
    assert not any(cmd[1] == "push" for cmd in state.commands)


def test_completion_requires_immutable_push_and_actual_merge_receipt(enabled_pipeline):
    state = enabled_pipeline
    result = run(state)
    assert result.status == "complete"
    assert result.to_dict()["candidate_sha"] == state.candidate
    pushed = next(cmd for cmd in state.commands if cmd[1] == "push")
    assert f"{state.candidate}:refs/heads/pidev/auto-{state.pipeline_id[:8]}" in pushed
    assert state.ship.call_args.kwargs["candidate_sha"] == state.candidate
    packet = pipeline.persist.read_json(state.pipeline_id, "06-review-packet.json")
    assert packet["candidate_tree"] == state.tree
    receipt = pipeline.persist.read_json(state.pipeline_id, "07-ship-result.json")
    assert receipt["candidate_sha"] == state.candidate


@pytest.mark.parametrize("receipt", [
    {"status": "merged"},
    {"status": "merged", "merge_sha": "c" * 40, "pr_url": "https://example.test/pr", "candidate_sha": "x" * 40},
    {"status": "merge_failed"},
])
def test_missing_merge_evidence_does_not_report_complete(enabled_pipeline, receipt):
    state = enabled_pipeline
    state.ship.return_value = receipt
    result = run(state)
    assert result.status == "ship_blocked"
    assert not any(call.args[1].get("shipped") is True for call in state.gates.call_args_list)


def test_existing_workspace_is_preserved_and_blocks_reuse(enabled_pipeline):
    state = enabled_pipeline
    workspace = state.workspace_root / state.pipeline_id
    workspace.mkdir(parents=True)
    marker = workspace / "valuable.txt"
    marker.write_text("keep", encoding="utf-8")
    assert_blocked(state, run(state))
    assert marker.read_text(encoding="utf-8") == "keep"
    state.loop.assert_not_awaited()


@pytest.mark.parametrize("phase", ["loop", "oracles", "review", "ship"])
def test_execution_exceptions_persist_failure(enabled_pipeline, phase):
    state = enabled_pipeline
    getattr(state, phase).side_effect = RuntimeError("transport failed")
    result = run(state)
    assert result.status in {"blocked", "ship_blocked"}
    assert "failed" in result.reason.lower()
    assert pipeline.persist.read_json(state.pipeline_id, "meta.json")["status"] == result.status
    if phase != "ship":
        state.ship.assert_not_called()


@pytest.mark.parametrize("receipt", [None, [], {"status": "merged", "candidate_sha": "b" * 40, "pr_url": "url", "merge_sha": ["invalid"]}])
def test_malformed_merge_receipt_is_blocked(enabled_pipeline, receipt):
    state = enabled_pipeline
    state.ship.return_value = receipt
    result = run(state)
    assert result.status == "ship_blocked"
    assert pipeline.persist.read_json(state.pipeline_id, "meta.json")["status"] == "ship_blocked"


def _local_git(workspace, *args):
    return _REAL_RUN(
        ["git", *args], cwd=workspace, check=True, capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    ).stdout.strip()


def _seed_local_git(monkeypatch):
    for key, value in {
        "GIT_AUTHOR_NAME": "Pipeline Test", "GIT_AUTHOR_EMAIL": "pipeline@example.test",
        "GIT_COMMITTER_NAME": "Pipeline Test", "GIT_COMMITTER_EMAIL": "pipeline@example.test",
    }.items():
        monkeypatch.setenv(key, value)
    _local_git(pipeline.REPO_ROOT, "init")
    (pipeline.REPO_ROOT / "README.md").write_text("base\n", encoding="utf-8")
    _local_git(pipeline.REPO_ROOT, "add", "-A")
    _local_git(pipeline.REPO_ROOT, "commit", "-m", "Seed isolated fixture")
    base = _local_git(pipeline.REPO_ROOT, "rev-parse", "HEAD")
    pushed = []

    def checked_git(cmd, **kwargs):
        assert Path(cmd[0]).name.lower() in {"git", "git.exe"}
        plain = _plain_git(cmd)
        if plain[1] == "push":
            pushed.append(plain)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return _REAL_RUN(cmd, **kwargs)

    monkeypatch.setattr(pipeline.subprocess, "run", checked_git)
    return base, pushed


def test_local_git_preserves_ancestry_and_reviews_loop_commits(enabled_pipeline, monkeypatch):
    state = enabled_pipeline
    base, pushed = _seed_local_git(monkeypatch)

    async def build(**kwargs):
        workspace = Path(kwargs["workspace"])
        (workspace / "README.md").write_text("candidate work\n", encoding="utf-8")
        _local_git(workspace, "add", "-A")
        _local_git(workspace, "commit", "-m", "Intermediate agent commit")
        return SimpleNamespace(done=True, reason="done", iters=1, cost_usd=0)

    def review(workspace, **kwargs):
        assert "+candidate work" in _local_git(workspace, "diff", "HEAD")
        return ReviewPacket("PASS")

    def merge(**kwargs):
        return {"status": "merged", "candidate_sha": kwargs["candidate_sha"],
                "pr_url": "https://example.test/pr/1", "merge_sha": "c" * 40}

    state.loop.side_effect = build
    state.review.side_effect = review
    state.ship.side_effect = merge
    result = run(state)
    assert result.status == "complete"
    workspace = state.workspace_root / state.pipeline_id
    assert _local_git(workspace, "rev-parse", "HEAD^") == base
    assert _local_git(workspace, "show", f"{result.candidate_sha}:README.md") == "candidate work"
    assert len(pushed) == 1
    assert f"{result.candidate_sha}:refs/heads/pidev/auto-{state.pipeline_id[:8]}" in pushed[0]


@pytest.mark.parametrize("failure, expected", [("boundary", "blocked — diff boundary"),
                                               ("review", "blocked — review"),
                                               (None, "PR opened")])
def test_execution_preserves_main_stage_reporting(enabled_pipeline, failure, expected):
    state = enabled_pipeline
    if failure == "boundary":
        state.boundary.return_value.tier = "blocked"
    elif failure == "review":
        state.review.return_value = ReviewPacket("BLOCKED", blockers=["unsafe change"])
    result = run(state)
    labels = [call.args[1] for call in state.reports.call_args_list]
    assert "build started" in labels
    assert expected in labels
    assert result.status == ("blocked" if failure else "complete")
