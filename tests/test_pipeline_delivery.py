"""Ship Chain must consume the same immutable delivery evidence as builds."""
import asyncio
import json
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.server import pipeline, session_model, session_phases
from app.server.session_model import BuildSession


@pytest.fixture
def delivery(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "_PIPELINE_ROOT", tmp_path / "pipeline")
    monkeypatch.setattr(session_phases.persistence, "save_session", Mock())
    monkeypatch.setattr(pipeline, "_append_ship_lesson", Mock())
    monkeypatch.setattr("app.server.supabase_log.log_gate_check", Mock())
    monkeypatch.setattr("app.server.agents.feedback_loop.append_shipped_feature", Mock())
    linear = Mock(return_value=True)
    monkeypatch.setattr(pipeline, "_update_linear_state_pipeline", linear)
    monkeypatch.setattr(pipeline, "_run_claude", Mock(side_effect=AssertionError("no model calls")))
    smoke = Mock(return_value=SimpleNamespace(returncode=0, stdout="Checks passed", stderr=""))
    monkeypatch.setattr(pipeline.subprocess, "run", smoke)
    candidate = "a" * 40
    session = BuildSession(
        id="delivered", repo_url="https://example.test/repo", workspace=str(tmp_path),
        status="complete", last_completed_phase="push", evaluator_status="passed",
        evaluator_score=9.0, candidate_sha=candidate, verified_sha=candidate,
        verification={"status": "passed", "candidate_sha": candidate},
        adversary_verdict={"verdict": "APPROVE", "candidate_sha": candidate},
        audit_evidence=[
            {"actual_model": model, "provider": provider, "model_verified": True,
             "auth_verified": True, "source": "transport_response", "rc": 0,
             "candidate_sha": candidate}
            for provider, model in (("claude_print", "model-a"), ("ollama", "model-b"))
        ],
    )
    monkeypatch.setitem(session_model._sessions, session.id, session)
    async def git(_workspace, *args, **kwargs):
        return (0, candidate if "rev-parse" in args else "", "")
    monkeypatch.setattr(session_phases, "run_cmd", AsyncMock(side_effect=git))
    state = pipeline.PipelineState("RA-999", "Test delivery", session.repo_url, "ship", session_id=session.id)
    pipeline.save_pipeline_state(state)
    for name in ("spec.md", "plan.md"):
        pipeline._write_artifact(state.pipeline_id, name, "Acceptance criterion " * 20)
    pipeline._write_artifact(state.pipeline_id, "session_id.txt", session.id)
    identity = {"pipeline_id": state.pipeline_id, "session_id": session.id, "candidate_sha": candidate}
    pipeline._write_artifact(state.pipeline_id, "test-results.json", json.dumps({**identity, "passed": True}))
    pipeline._write_artifact(state.pipeline_id, "review-score.json", json.dumps({**identity, "overall_score": 9, "pass": True}))
    return SimpleNamespace(state=state, session=session, linear=linear, smoke=smoke)


@pytest.mark.parametrize("status", ["missing", "blocked", "failed", "stalled", "building"])
def test_ship_rejects_missing_or_undelivered_session(delivery, monkeypatch, status):
    if status == "missing":
        monkeypatch.delitem(session_model._sessions, delivery.session.id)
    else:
        delivery.session.status = status
    result = pipeline.run_ship_phase(delivery.state.pipeline_id)
    assert result.ship_log["shipped"] is False
    delivery.linear.assert_not_called()


def test_ship_rejects_complete_without_successful_push(delivery):
    delivery.session.last_completed_phase = "evaluator"
    assert pipeline.run_ship_phase(delivery.state.pipeline_id).ship_log["shipped"] is False
    delivery.linear.assert_not_called()


@pytest.mark.parametrize("artifact,field", [("test-results.json", "candidate_sha"), ("review-score.json", "candidate_sha"), ("test-results.json", "session_id"), ("review-score.json", "pipeline_id")])
def test_ship_rejects_stale_or_foreign_evidence(delivery, artifact, field):
    evidence = pipeline._read_json_artifact(delivery.state.pipeline_id, artifact)
    evidence[field] = "other"
    pipeline._write_artifact(delivery.state.pipeline_id, artifact, json.dumps(evidence))
    assert pipeline.run_ship_phase(delivery.state.pipeline_id).ship_log["shipped"] is False
    delivery.linear.assert_not_called()


def test_ship_reuses_required_review_provenance(delivery):
    delivery.session.audit_evidence = []
    assert pipeline.run_ship_phase(delivery.state.pipeline_id).ship_log["shipped"] is False
    delivery.linear.assert_not_called()


def test_ship_rejects_candidate_changed_after_review(delivery, monkeypatch):
    monkeypatch.setattr(session_phases, "run_cmd", AsyncMock(return_value=(0, "b" * 40, "")))
    assert pipeline.run_ship_phase(delivery.state.pipeline_id).ship_log["shipped"] is False
    delivery.linear.assert_not_called()


@pytest.mark.parametrize("async_context", [False, True])
def test_ship_records_exact_delivered_candidate(delivery, async_context):
    async def run():
        return await asyncio.to_thread(pipeline.run_ship_phase, delivery.state.pipeline_id)
    result = asyncio.run(run()) if async_context else pipeline.run_ship_phase(delivery.state.pipeline_id)
    assert result.ship_log["shipped"] is True
    assert result.ship_log["candidate_sha"] == delivery.session.candidate_sha
    assert delivery.session.candidate_sha in result.ship_log["rollback_ref"]
    # Delivery opens a review branch; it does not prove a deployment or merge.
    delivery.linear.assert_called_once_with("RA-999", "In Review")
    assert "deployed_at" not in result.ship_log


def test_missing_smoke_test_fails_closed(delivery, monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "__file__", str(tmp_path / "app" / "server" / "pipeline.py"))
    result = pipeline.run_test_phase(delivery.state.pipeline_id, delivery.session.id)
    assert result.test_results["passed"] is False
    assert "missing" in result.test_results["error"].lower() or "not found" in result.test_results["error"].lower()
    delivery.smoke.assert_not_called()


@pytest.mark.parametrize("rc,output", [(1, '{"passed": true}'), (0, '{"passed": "true"}'), (0, '{"passed": false}'), (0, '[]')])
def test_smoke_requires_exit_success_and_valid_result(delivery, rc, output):
    delivery.smoke.return_value = SimpleNamespace(returncode=rc, stdout=output, stderr="error")
    result = pipeline.run_test_phase(delivery.state.pipeline_id, delivery.session.id)
    assert result.test_results["passed"] is False


def test_smoke_evidence_cannot_override_candidate_identity(delivery):
    delivery.smoke.return_value = SimpleNamespace(returncode=0, stdout='{"passed": true, "candidate_sha": "spoof", "session_id": "spoof"}', stderr="")
    result = pipeline.run_test_phase(delivery.state.pipeline_id, delivery.session.id)
    assert result.test_results["candidate_sha"] == delivery.session.candidate_sha
    assert result.test_results["session_id"] == delivery.session.id
    assert "--expected-sha" in delivery.smoke.call_args.args[0]
    assert delivery.session.candidate_sha in delivery.smoke.call_args.args[0]


@pytest.mark.parametrize("error", [OSError("cannot start"), subprocess.TimeoutExpired("smoke", 120)])
def test_smoke_runner_errors_are_recorded(delivery, error):
    delivery.smoke.side_effect = error
    result = pipeline.run_test_phase(delivery.state.pipeline_id, delivery.session.id)
    assert result.test_results["passed"] is False
    assert result.test_results["error"]


def test_review_uses_actual_build_evidence_without_model_rescoring(delivery):
    result = pipeline.run_review_phase(delivery.state.pipeline_id, delivery.session.id)
    assert result.review_score["pass"] is True
    assert result.review_score["candidate_sha"] == delivery.session.candidate_sha
    assert result.review_score["audit_evidence"] == delivery.session.audit_evidence
    pipeline._run_claude.assert_not_called()


def test_review_rejects_old_test_evidence(delivery):
    delivery.session.candidate_sha = "b" * 40
    with pytest.raises(ValueError, match="candidate|Tests"):
        pipeline.run_review_phase(delivery.state.pipeline_id, delivery.session.id)
    pipeline._run_claude.assert_not_called()


@pytest.mark.parametrize("score", [None, True, "9", float("nan"), 7])
def test_ship_rejects_invalid_or_insufficient_build_score(delivery, score):
    delivery.session.evaluator_score = score
    assert pipeline.run_ship_phase(delivery.state.pipeline_id).ship_log["shipped"] is False
    delivery.linear.assert_not_called()


def test_repeat_ship_does_not_repeat_external_effects(delivery):
    first = pipeline.run_ship_phase(delivery.state.pipeline_id)
    second = pipeline.run_ship_phase(delivery.state.pipeline_id)
    assert first.ship_log == second.ship_log
    delivery.linear.assert_called_once()
    pipeline._append_ship_lesson.assert_called_once()


def test_failed_retest_invalidates_prior_delivery(delivery):
    pipeline.run_ship_phase(delivery.state.pipeline_id)
    delivery.smoke.side_effect = OSError("cannot start")
    result = pipeline.run_test_phase(delivery.state.pipeline_id, delivery.session.id)
    assert result.ship_log is None
    assert "ship" not in result.phases_completed
    assert pipeline.run_ship_phase(delivery.state.pipeline_id).ship_log["shipped"] is False
    delivery.linear.assert_called_once()


def test_failed_linear_update_is_not_reported_as_success(delivery):
    delivery.linear.return_value = False
    result = pipeline.run_ship_phase(delivery.state.pipeline_id)
    assert result.ship_log["shipped"] is True
    assert result.ship_log["linear_ticket_updated"] is False


def test_pipeline_route_runs_real_gate_outside_event_loop(delivery):
    from app.server.models import ShipRequest
    from app.server.routes.pipeline import run_ship
    result = asyncio.run(run_ship(ShipRequest(pipeline_id=delivery.state.pipeline_id)))
    assert result["ok"] is True
    assert result["ship_log"]["candidate_sha"] == delivery.session.candidate_sha


def test_telegram_route_runs_real_gate_outside_event_loop(delivery, monkeypatch):
    from app.server.routes.telegram_proxy import ShipBody, ship
    monkeypatch.setattr(pipeline, "list_pipelines", lambda: [
        {"pipeline_id": delivery.state.pipeline_id, "linear_issue_id": "RA-999"}
    ])
    result = asyncio.run(ship(ShipBody(issue_id="RA-999")))
    assert result["status"] == "shipped"



def test_concurrent_ship_runs_external_actions_once(delivery):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Event, Lock

    start = Barrier(2)
    duplicate = Event()
    count_lock = Lock()
    actions = 0

    def linear(*args):
        nonlocal actions
        with count_lock:
            actions += 1
            if actions > 1:
                duplicate.set()
        duplicate.wait(timeout=0.2)
        return True

    def ship():
        start.wait(timeout=2)
        return pipeline.run_ship_phase(delivery.state.pipeline_id)

    delivery.linear.side_effect = linear
    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.submit(ship), executor.submit(ship)
        results = [first.result(timeout=5), second.result(timeout=5)]
    assert actions == 1
    assert results[0].ship_log == results[1].ship_log
    pipeline._append_ship_lesson.assert_called_once()



def test_ship_waits_for_inflight_failed_retest(delivery):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    testing = Event()
    ship_started = Event()

    def failed_smoke(*args, **kwargs):
        testing.set()
        assert ship_started.wait(timeout=2)
        return SimpleNamespace(returncode=1, stdout="failed", stderr="")

    def ship():
        assert testing.wait(timeout=2)
        ship_started.set()
        return pipeline.run_ship_phase(delivery.state.pipeline_id)

    delivery.smoke.side_effect = failed_smoke
    with ThreadPoolExecutor(max_workers=2) as executor:
        retest = executor.submit(pipeline.run_test_phase, delivery.state.pipeline_id, delivery.session.id)
        receipt = executor.submit(ship)
        assert retest.result(timeout=5).test_results["passed"] is False
        assert receipt.result(timeout=5).ship_log["shipped"] is False
    delivery.linear.assert_not_called()
    pipeline._append_ship_lesson.assert_not_called()
