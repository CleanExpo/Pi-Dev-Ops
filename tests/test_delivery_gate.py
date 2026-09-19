"""Failure injection for release evidence and orchestration; no provider calls."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.server import session_phases as phases
from app.server import orchestrator
from app.server.session_model import BuildSession
from app.server.workspace_verify import VerifyResult


@pytest.fixture(autouse=True)
def no_external_effects(monkeypatch):
    monkeypatch.setattr(phases.persistence, "save_session", Mock())
    monkeypatch.setattr(phases, "_run_persona_review", AsyncMock(return_value=[]))
    monkeypatch.setattr(phases, "_send_low_confidence_alert", Mock())
    monkeypatch.setattr(phases, "_emit_phase_metric", Mock())
    monkeypatch.setattr(phases, "run_cmd", AsyncMock(return_value=(0, "", "")))


@pytest.mark.parametrize("reason", [
    "subscription_only: SDK billing authorization is unknown",
    "execution_blocked: sandbox support is unavailable",
])
def test_generator_preserves_policy_block_without_retry(monkeypatch, tmp_path, reason):
    session = BuildSession(id="blocked-generator", workspace=str(tmp_path))
    sdk = AsyncMock(return_value=(1, reason, 0.0))
    monkeypatch.setattr(phases, "_run_claude_via_sdk", sdk)

    assert asyncio.run(phases._phase_generate(session, "spec", "sonnet", "")) is False
    assert session.status == "blocked"
    assert session.error == reason
    sdk.assert_awaited_once()
    phases.persistence.save_session.assert_called_with(session)


def test_workspace_exists_does_not_claim_sandbox_verification(monkeypatch, tmp_path):
    session = BuildSession(workspace=str(tmp_path))
    emit = Mock()
    monkeypatch.setattr(phases, "em", emit)

    assert asyncio.run(phases._phase_sandbox(session, "")) is True
    messages = " ".join(str(call.args[2]) for call in emit.call_args_list)
    assert "Workspace available" in messages
    assert "Sandbox verified" not in messages


@pytest.mark.parametrize("status", ["failed", "timed_out", "not_run"])
def test_inconclusive_checks_block_evaluation(monkeypatch, tmp_path, status):
    session = BuildSession(workspace=str(tmp_path), evaluator_enabled=True)
    monkeypatch.setattr(phases.config, "EVALUATOR_ENABLED", True)
    monkeypatch.setattr(phases.persistence, "save_session", Mock())
    monkeypatch.setattr(phases.workspace_verify, "run_workspace_checks", AsyncMock(
        return_value=VerifyResult(status, "pytest", "missing", "failed")))
    reviewer = AsyncMock(return_value=(10, "OVERALL: 10/10", "reviewer", "ok"))
    monkeypatch.setattr(phases, "_run_parallel_eval_cached", reviewer)
    asyncio.run(phases._phase_evaluate(session, "brief", "sonnet", "spec", "build"))
    assert session.evaluator_status == "verification_failed"
    reviewer.assert_not_awaited()


def test_disabled_required_review_blocks(monkeypatch, tmp_path):
    session = BuildSession(workspace=str(tmp_path), evaluator_enabled=False)
    monkeypatch.setattr(phases.persistence, "save_session", Mock())
    asyncio.run(phases._phase_evaluate(session, "brief", "sonnet", "spec", "build"))
    assert session.evaluator_status == "disabled"
    assert session.status == "blocked"


def test_verifier_exception_is_recorded_as_blocked(monkeypatch, tmp_path):
    session = BuildSession(workspace=str(tmp_path), evaluator_enabled=True)
    monkeypatch.setattr(phases.config, "EVALUATOR_ENABLED", True)
    monkeypatch.setattr(phases.workspace_verify, "run_workspace_checks", AsyncMock(side_effect=RuntimeError("check unavailable")))
    asyncio.run(phases._phase_evaluate(session, "brief", "sonnet", "spec", "build"))
    assert session.status == "blocked"
    assert session.verification["status"] == "not_run"


def test_gate_log_does_not_invent_test_success(monkeypatch, tmp_path):
    session = BuildSession(workspace=str(tmp_path))
    capture = Mock()
    monkeypatch.setattr(phases, "log_gate_check", capture)
    phases._log_ship_gate_check(session, False, 0)
    assert capture.call_args.kwargs["gate_checks"]["tests_passed"] is False


@pytest.mark.parametrize("status", ["stalled", "blocked", "failed"])
def test_wave_rejects_terminal_failure(monkeypatch, status):
    child = SimpleNamespace(status=status)
    monkeypatch.setitem(orchestrator._sessions, "child", child)
    parent = BuildSession()
    result = asyncio.run(asyncio.wait_for(
        orchestrator._wait_for_wave(["child"], parent, 1), timeout=0.05))
    assert result is False


def test_wave_rejects_missing_child():
    assert asyncio.run(orchestrator._wait_for_wave(["missing-child"], BuildSession(), 1)) is False


def test_fanout_waits_for_final_wave(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator.config, "WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(orchestrator, "run_cmd", AsyncMock(return_value=(0, "", "")))
    monkeypatch.setattr(orchestrator, "_decompose_brief", AsyncMock(return_value=["task"]))
    monkeypatch.setattr(orchestrator, "_launch_wave", AsyncMock(return_value=(["child"], [])))
    wait = AsyncMock(return_value=False)
    monkeypatch.setattr(orchestrator, "_wait_for_wave", wait)
    async def scenario():
        result = await orchestrator.fan_out("https://example.test/repo", "brief")
        await orchestrator._fan_out_tasks[result["parent_id"]]
        return result
    result = asyncio.run(scenario())
    wait.assert_awaited_once()
    assert result["status"] == "launched"
    assert orchestrator._sessions[result["parent_id"]].status == "failed"


@pytest.mark.parametrize("review_status", ["warned", "error", "timeout", "scope_violation", "disabled"])
def test_release_rejects_nonpassing_evaluator(monkeypatch, review_status):
    session = BuildSession(evaluator_status=review_status)
    session.candidate_sha = session.verified_sha = "a" * 40
    session.verification = {"status": "passed", "candidate_sha": session.candidate_sha}
    session.adversary_verdict = {"verdict": "APPROVE", "candidate_sha": session.candidate_sha}
    assert asyncio.run(phases._release_gate(session)) is False


def test_release_rejects_changed_candidate(monkeypatch):
    session = BuildSession(evaluator_status="passed")
    session.candidate_sha = session.verified_sha = "a" * 40
    session.verification = {"status": "passed", "candidate_sha": session.candidate_sha}
    session.adversary_verdict = {"verdict": "APPROVE", "candidate_sha": session.candidate_sha}
    session.audit_evidence = [
        {"actual_model": model, "provider": "ollama" if model == "model-b" else "claude_print", "model_verified": True,
         "auth_verified": True, "source": "transport_response", "rc": 0,
         "candidate_sha": session.candidate_sha}
        for model in ("model-a", "model-b")
    ]
    monkeypatch.setattr(phases, "run_cmd", AsyncMock(return_value=(0, "b" * 40, "")))
    assert asyncio.run(phases._release_gate(session)) is False
    assert "changed after verification" in session.error


def test_release_accepts_only_clean_verified_revision(monkeypatch):
    session = BuildSession(evaluator_status="passed")
    session.candidate_sha = session.verified_sha = "a" * 40
    session.verification = {"status": "passed", "candidate_sha": session.candidate_sha}
    session.adversary_verdict = {"verdict": "APPROVE", "candidate_sha": session.candidate_sha}
    session.audit_evidence = [
        {"actual_model": model, "provider": "ollama" if model == "model-b" else "claude_print", "model_verified": True,
         "auth_verified": True, "source": "transport_response", "rc": 0,
         "candidate_sha": session.candidate_sha}
        for model in ("model-a", "model-b")
    ]
    monkeypatch.setattr(phases, "run_cmd", AsyncMock(side_effect=[
        (0, session.candidate_sha, ""), (0, "", ""),
    ]))
    assert asyncio.run(phases._release_gate(session)) is True


@pytest.mark.parametrize("rc,text", [(1, "APPROVE"), (0, "Something went wrong"), (0, "BLOCK\nAPPROVE")])
def test_adversary_errors_fail_closed(monkeypatch, tmp_path, rc, text):
    session = BuildSession(workspace=str(tmp_path))
    session.base_sha = "a" * 40
    session.candidate_sha = "b" * 40
    monkeypatch.setattr(phases, "run_cmd", AsyncMock(side_effect=[
        (0, "diff --git a/app.py b/app.py\n+danger()", ""),
        (0, "app.py | 1 +", ""),
    ]))
    monkeypatch.setattr(phases, "_run_claude_via_sdk", AsyncMock(return_value=(rc, text, 0)))
    result, _ = asyncio.run(phases._phase_adversary(session, 6))
    assert result is False


@pytest.mark.parametrize("review,push_ok,expected", [("warned", True, "blocked"), ("passed", False, "failed"), ("passed", True, "complete")])
def test_build_completion_requires_review_and_delivery(monkeypatch, tmp_path, review, push_ok, expected):
    session = BuildSession(workspace=str(tmp_path), linear_issue_id="issue", complexity_tier="basic")
    session.base_sha = "a" * 40
    monkeypatch.setattr(phases, "_TAO_AVAILABLE", False)
    for name in ("_phase_clone", "_phase_claude_check", "_phase_sandbox", "_phase_generate", "_prepare_candidate"):
        monkeypatch.setattr(phases, name, AsyncMock(return_value=True))
    for name in ("_phase_analyze", "_notify_linear_session_started", "_sync_linear_on_completion", "_log_ship_gate_check", "_record_session_outcome"):
        monkeypatch.setattr(phases, name, Mock())
    monkeypatch.setattr(phases, "retrieve_similar_episodes", Mock(return_value=[]))
    for name in ("_write_task_memory", "_phase_plan", "record_episode"):
        monkeypatch.setattr(phases, name, AsyncMock())
    monkeypatch.setattr(phases, "build_structured_brief", Mock(return_value="spec"))
    async def evaluate(*args):
        session.evaluator_status = review
        return 6
    monkeypatch.setattr(phases, "_phase_evaluate", evaluate)
    monkeypatch.setattr(phases, "_phase_adversary", AsyncMock(return_value=(True, {"verdict": "APPROVE"})))
    push = AsyncMock(return_value=([], push_ok))
    monkeypatch.setattr(phases, "_phase_push", push)
    linear = Mock()
    monkeypatch.setattr(phases, "_update_linear_state", linear)
    asyncio.run(phases.run_build(session, "brief", "sonnet", "build"))
    assert session.status == expected
    if review != "passed":
        push.assert_not_awaited()
    if expected != "complete":
        linear.assert_not_called()
    else:
        linear.assert_called_once_with("issue", "In Review")
