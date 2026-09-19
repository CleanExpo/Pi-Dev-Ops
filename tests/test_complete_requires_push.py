"""UNI-2643 — a session cannot be complete if its push failed.

Each of the five bad outcomes the unfixed `run_build` tail produced is killed
by its own assertion. Mutation controls restore one bad value at a time and
prove the contract goes red. The live `run_build` call site is driven too —
a helper-only suite would stay green if production never called it.
"""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.server import session_phases
from app.server.session_finish import (
    IN_REVIEW,
    PUSH_FAILED_REASON,
    SESSION_COMPLETE_MARKER,
    PostPushEffects,
    decide_post_push,
    finish_after_push,
)
from app.server.session_model import BuildSession


class _Hooks:
    def __init__(self) -> None:
        self.emitted: list[dict] = []
        self.gate_rows: list[dict] = []
        self.linear_calls: list[tuple[str, str]] = []

    def emit(self, session, kind, text):
        self.emitted.append({"type": kind, "text": text})

    def persist(self, session):
        return None

    def log_ship_gate(self, session, shipped, push_ts):
        self.gate_rows.append({"shipped": shipped, "push_ts": push_ts})

    def update_linear_state(self, issue_id, state):
        self.linear_calls.append((issue_id, state))

    def sync_linear_on_completion(self, session):
        return None

    def record_outcome(self, session, push_ok, push_ts):
        return None

    def as_kwargs(self) -> dict:
        return {
            "emit": self.emit,
            "persist": self.persist,
            "log_ship_gate": self.log_ship_gate,
            "update_linear_state": self.update_linear_state,
            "sync_linear_on_completion": self.sync_linear_on_completion,
            "record_outcome": self.record_outcome,
        }


def _session(linear_issue_id="iss-1"):
    return SimpleNamespace(
        id="sess-test",
        status="building",
        error=None,
        last_completed_phase="adversary",
        linear_issue_id=linear_issue_id,
        started_at=1_000.0,
        completed_at=None,
        output_lines=[],
    )


def assert_push_failure_contract(session, hooks: _Hooks) -> None:
    """The five UNI-2643 outcomes. Each line is a mutation target."""
    if session.status == "complete":
        raise AssertionError("push failure persisted status=complete")
    if any(SESSION_COMPLETE_MARKER in row["text"] for row in hooks.emitted):
        raise AssertionError("push failure emitted the completion marker")
    if any(state == IN_REVIEW for _issue, state in hooks.linear_calls):
        raise AssertionError("push failure moved Linear to In Review")
    if not hooks.gate_rows or hooks.gate_rows[-1]["shipped"] is not False:
        raise AssertionError("push failure left gate row shipped!=false")
    if not session.error:
        raise AssertionError("push failure left no diagnosable reason on the session")


def _apply_effects(session, effects: PostPushEffects, hooks: _Hooks) -> None:
    session.error = effects.reason
    session.status = effects.status
    hooks.log_ship_gate(session, effects.shipped, 1.0)
    if effects.linear_state and session.linear_issue_id:
        hooks.update_linear_state(session.linear_issue_id, effects.linear_state)
    if effects.emit_completion_marker:
        hooks.emit(session, "success", f"  {SESSION_COMPLETE_MARKER}")


def test_push_ok_is_the_only_complete_path():
    ok = decide_post_push(True)
    assert ok.status == "complete"
    assert ok.emit_completion_marker is True
    assert ok.linear_state == IN_REVIEW
    assert ok.shipped is True
    assert ok.reason is None


def test_push_failure_is_not_complete():
    bad = decide_post_push(False)
    assert bad.status != "complete"
    assert bad.emit_completion_marker is False
    assert bad.linear_state is None
    assert bad.shipped is False
    assert bad.reason == PUSH_FAILED_REASON


def test_finish_push_ok_still_completes():
    session = _session()
    hooks = _Hooks()
    finish_after_push(session, True, 9.0, **hooks.as_kwargs())
    assert session.status == "complete"
    assert any(SESSION_COMPLETE_MARKER in row["text"] for row in hooks.emitted)
    assert hooks.linear_calls == [("iss-1", IN_REVIEW)]
    assert hooks.gate_rows[-1]["shipped"] is True
    assert session.error is None


def test_finish_push_failure_leaves_the_five_outcomes():
    session = _session()
    hooks = _Hooks()
    finish_after_push(session, False, 9.0, **hooks.as_kwargs())
    assert_push_failure_contract(session, hooks)
    assert session.status == "failed"
    assert session.error == PUSH_FAILED_REASON
    assert hooks.linear_calls == []


def test_mutation_status_complete_is_caught():
    session, hooks = _session(), _Hooks()
    _apply_effects(session, replace(decide_post_push(False), status="complete"), hooks)
    try:
        assert_push_failure_contract(session, hooks)
    except AssertionError as exc:
        assert "status=complete" in str(exc)
    else:
        raise AssertionError("mutation status=complete was not caught")


def test_mutation_completion_marker_is_caught():
    session, hooks = _session(), _Hooks()
    _apply_effects(session, replace(decide_post_push(False), emit_completion_marker=True), hooks)
    try:
        assert_push_failure_contract(session, hooks)
    except AssertionError as exc:
        assert "completion marker" in str(exc)
    else:
        raise AssertionError("mutation completion marker was not caught")


def test_mutation_linear_in_review_is_caught():
    session, hooks = _session(), _Hooks()
    _apply_effects(session, replace(decide_post_push(False), linear_state=IN_REVIEW), hooks)
    try:
        assert_push_failure_contract(session, hooks)
    except AssertionError as exc:
        assert "In Review" in str(exc)
    else:
        raise AssertionError("mutation Linear In Review was not caught")


def test_mutation_shipped_true_is_caught():
    session, hooks = _session(), _Hooks()
    _apply_effects(session, replace(decide_post_push(False), shipped=True), hooks)
    try:
        assert_push_failure_contract(session, hooks)
    except AssertionError as exc:
        assert "shipped" in str(exc)
    else:
        raise AssertionError("mutation shipped=true was not caught")


def test_mutation_missing_reason_is_caught():
    session, hooks = _session(), _Hooks()
    _apply_effects(session, replace(decide_post_push(False), reason=None), hooks)
    try:
        assert_push_failure_contract(session, hooks)
    except AssertionError as exc:
        assert "diagnosable reason" in str(exc)
    else:
        raise AssertionError("mutation missing reason was not caught")


def test_run_build_tail_consults_finish_after_push():
    """Call-site audit: the unfixed tail must not return after `_phase_push`."""
    source = Path(session_phases.__file__).read_text()
    after = source.split("af, push_ok = await _phase_push", 1)[1]
    assert "finish_after_push(" in after
    assert "mark_complete(session)" not in after
    assert SESSION_COMPLETE_MARKER not in after


def _run_build_patches(push_ok: bool, linear, capture_gate) -> list:
    return [
        patch.object(session_phases, "_TAO_AVAILABLE", False),
        patch.object(session_phases, "_notify_linear_session_started"),
        patch.object(session_phases, "_record_base", new=AsyncMock(return_value=True)),
        patch.object(session_phases, "_prepare_candidate", new=AsyncMock(return_value=True)),
        patch.object(session_phases, "_phase_clone", new=AsyncMock(return_value=True)),
        patch.object(session_phases, "_phase_analyze"),
        patch.object(session_phases, "_phase_claude_check", new=AsyncMock(return_value=True)),
        patch.object(session_phases, "_phase_sandbox", new=AsyncMock(return_value=True)),
        patch.object(session_phases, "classify_intent", return_value="build"),
        patch.object(session_phases, "retrieve_similar_episodes", new=AsyncMock(return_value=[])),
        patch.object(session_phases, "build_structured_brief", return_value="spec"),
        patch.object(session_phases, "_write_task_memory", new=AsyncMock()),
        patch.object(session_phases, "_phase_plan", new=AsyncMock(return_value=True)),
        patch.object(session_phases, "_phase_generate", new=AsyncMock(return_value=True)),
        patch.object(session_phases, "_phase_evaluate", new=AsyncMock(return_value=6)),
        patch.object(session_phases, "_phase_adversary", new=AsyncMock(return_value=(True, {}))),
        patch.object(session_phases, "_phase_push", new=AsyncMock(return_value=(["a.py"], push_ok))),
        patch.object(session_phases.persistence, "save_session"),
        patch.object(session_phases, "_log_ship_gate_check", side_effect=capture_gate),
        patch.object(session_phases, "_update_linear_state", new=linear),
        patch.object(session_phases, "_sync_linear_on_completion"),
        patch.object(session_phases, "_record_session_outcome"),
        patch.object(session_phases, "record_episode", new=AsyncMock()),
    ]


async def _drive_run_build(session, *, push_ok: bool):
    session.evaluator_status = "passed"
    linear = MagicMock()
    gate = {}

    def _capture_gate(_session, shipped, push_ts):
        gate.update(shipped=shipped, push_ts=push_ts)

    with ExitStack() as stack:
        for ctx in _run_build_patches(push_ok, linear, _capture_gate):
            stack.enter_context(ctx)
        await session_phases.run_build(session, brief="ship it")
    return linear, gate


async def test_run_build_push_failure_is_not_complete():
    session = BuildSession(
        repo_url="https://example.test/repo",
        linear_issue_id="iss-live",
        complexity_tier="basic",
        started_at=1_000.0,
    )
    linear, gate = await _drive_run_build(session, push_ok=False)
    texts = [str(row.get("text") or "") for row in session.output_lines]
    assert session.status != "complete"
    assert not any(SESSION_COMPLETE_MARKER in text for text in texts)
    assert all(call.args[1] != IN_REVIEW for call in linear.call_args_list)
    assert gate.get("shipped") is False
    assert session.error == PUSH_FAILED_REASON


async def test_run_build_push_ok_still_completes():
    session = BuildSession(
        repo_url="https://example.test/repo",
        linear_issue_id="iss-live",
        complexity_tier="basic",
        started_at=1_000.0,
    )
    linear, gate = await _drive_run_build(session, push_ok=True)
    texts = [str(row.get("text") or "") for row in session.output_lines]
    assert session.status == "complete"
    assert any(SESSION_COMPLETE_MARKER in text for text in texts)
    linear.assert_called_with("iss-live", IN_REVIEW)
    assert gate.get("shipped") is True
    assert session.error is None
