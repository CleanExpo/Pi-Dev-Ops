"""tests/test_model_policy_evaluator.py — RA-1506 regression.

Locks the contract: the evaluator path NEVER calls _run_claude_via_sdk
with model=opus (or the long-form ID claude-opus-4-7).

Background (PR #131 / RA-1099):
    _run_parallel_eval previously escalated to Opus when |sonnet_score -
    haiku_score| > 2.  That violated model policy — "evaluator" is not in
    OPUS_ALLOWED_ROLES.  The fix averages sonnet + haiku regardless of delta.

Acceptance criterion:
    Re-introducing an `if delta > 2: _run_single_eval(..., "opus")` call in
    the escalation path would produce a third SDK invocation with model="opus"
    and the assertion at the bottom of this module would fail.
"""
from __future__ import annotations

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OPUS_NAMES = {"opus", "claude-opus-4-7"}


def _make_session(workspace: str = "/tmp/fake-ws") -> SimpleNamespace:
    """Minimal session stub — only the attributes _run_parallel_eval reads."""
    return SimpleNamespace(
        id="test-ra1506",
        workspace=workspace,
        output_lines=[],
    )


def _eval_text(score: float) -> str:
    """Build a parseable evaluator response with the given OVERALL score."""
    return (
        f"COMPLETENESS: {score}/10 — looks good\n"
        f"CORRECTNESS: {score}/10 — looks good\n"
        f"CONCISENESS: {score}/10 — looks good\n"
        f"FORMAT: {score}/10 — looks good\n"
        f"KARPATHY: {score}/10 — looks good\n"
        f"OVERALL: {score}/10 — PASS\n"
        "CONFIDENCE: 85%\n"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_parallel_eval_never_calls_opus_consensus():
    """Sonnet and haiku agree (delta == 0) — only 2 SDK calls, both non-opus."""
    from app.server.session_evaluator import _run_parallel_eval

    session = _make_session()
    sdk_mock = AsyncMock(return_value=(0, _eval_text(8.0), 0.01))

    with patch("app.server.session_evaluator._run_claude_via_sdk", sdk_mock):
        score, text, label, consensus = await _run_parallel_eval(session, "eval spec")

    assert score == pytest.approx(8.0)
    assert sdk_mock.call_count == 2, "expected exactly 2 SDK calls (sonnet + haiku)"

    for c in sdk_mock.call_args_list:
        model_used = c.args[1] if len(c.args) > 1 else c.kwargs.get("model", "")
        assert model_used not in _OPUS_NAMES, (
            f"evaluator called SDK with model={model_used!r} — opus is not allowed"
        )


@pytest.mark.asyncio
async def test_run_parallel_eval_never_calls_opus_large_delta():
    """Sonnet=9, haiku=5 → |delta|=4 > 2.  Even with a large disagreement the
    escalation to Opus must NOT happen.  The function must still return a
    score (average) and make exactly 2 SDK calls, both non-opus.

    This is the primary regression guard for RA-1506 / PR #131:
    re-introducing `if delta > 2: _run_single_eval(..., "opus")` would add a
    third call with model="opus" and the assertion below would catch it.
    """
    from app.server.session_evaluator import _run_parallel_eval

    session = _make_session()

    # Alternate: first call returns sonnet=9, second returns haiku=5 → delta=4
    sdk_mock = AsyncMock(
        side_effect=[
            (0, _eval_text(9.0), 0.02),   # sonnet
            (0, _eval_text(5.0), 0.01),   # haiku
        ]
    )

    with patch("app.server.session_evaluator._run_claude_via_sdk", sdk_mock):
        score, text, label, consensus = await _run_parallel_eval(session, "eval spec")

    # Score should be the average, not an opus-arbitrated value
    assert score == pytest.approx(7.0), (
        f"expected sonnet+haiku average (7.0) but got {score!r}; "
        "escalation path may have changed the score"
    )
    assert sdk_mock.call_count == 2, (
        f"expected exactly 2 SDK calls but got {sdk_mock.call_count}; "
        "opus escalation would produce a 3rd call"
    )

    for c in sdk_mock.call_args_list:
        model_used = c.args[1] if len(c.args) > 1 else c.kwargs.get("model", "")
        assert model_used not in _OPUS_NAMES, (
            f"evaluator called SDK with model={model_used!r} — "
            "opus is not in OPUS_ALLOWED_ROLES for the evaluator phase"
        )


@pytest.mark.asyncio
async def test_run_parallel_eval_models_are_sonnet_and_haiku():
    """Assert the two SDK calls use exactly 'sonnet' and 'haiku' (no other model)."""
    from app.server.session_evaluator import _run_parallel_eval

    session = _make_session()
    sdk_mock = AsyncMock(return_value=(0, _eval_text(7.5), 0.01))

    with patch("app.server.session_evaluator._run_claude_via_sdk", sdk_mock):
        await _run_parallel_eval(session, "eval spec")

    models_used = [
        c.args[1] if len(c.args) > 1 else c.kwargs.get("model", "")
        for c in sdk_mock.call_args_list
    ]
    assert set(models_used) == {"sonnet", "haiku"}, (
        f"expected only sonnet + haiku SDK calls but got {models_used!r}"
    )


@pytest.mark.asyncio
async def test_run_parallel_eval_phase_kwarg_is_evaluator():
    """SDK calls must carry phase='evaluator' so the model-policy gate in
    _run_claude_via_sdk can enforce OPUS_ALLOWED_ROLES at the wire boundary."""
    from app.server.session_evaluator import _run_parallel_eval

    session = _make_session()
    sdk_mock = AsyncMock(return_value=(0, _eval_text(8.0), 0.01))

    with patch("app.server.session_evaluator._run_claude_via_sdk", sdk_mock):
        await _run_parallel_eval(session, "eval spec")

    for c in sdk_mock.call_args_list:
        phase_used = c.kwargs.get("phase", c.args[5] if len(c.args) > 5 else "")
        assert phase_used == "evaluator", (
            f"expected phase='evaluator' but got {phase_used!r}; "
            "without the correct phase the model-policy gate is blind"
        )
