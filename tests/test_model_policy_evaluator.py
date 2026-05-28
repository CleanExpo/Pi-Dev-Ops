"""Regression tests for evaluator provider routing.

Evaluator work must go through provider_router so Railway env overrides such as
OpenRouter/Kimi are honoured. These tests intentionally do not assert specific
Anthropic model IDs; doing so would reintroduce the Anthropic-first coupling.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


def _make_session(workspace: str = "/tmp/fake-ws") -> SimpleNamespace:
    """Minimal session stub — only attributes evaluator helpers read."""
    return SimpleNamespace(
        id="test-provider-router-evaluator",
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


@pytest.mark.asyncio
async def test_run_single_eval_uses_provider_router_evaluator_role():
    from app.server.session_evaluator import _run_single_eval

    router_mock = AsyncMock(return_value=(0, _eval_text(8.0), 0.01, None))

    with patch("app.server.session_evaluator.run_via_provider", router_mock):
        score, text = await _run_single_eval(
            "/tmp/ws", "eval spec", "sonnet", timeout=33, session_id="sid-1"
        )

    assert score == pytest.approx(8.0)
    assert "OVERALL: 8.0/10" in text
    router_mock.assert_awaited_once()
    assert router_mock.await_args is not None
    args, kwargs = router_mock.await_args
    assert args[0] == "eval spec"
    assert kwargs["role"] == "evaluator"
    assert kwargs["task_class"] == "single-sonnet"
    assert kwargs["timeout_s"] == 33
    assert kwargs["workspace"] == "/tmp/ws"
    assert kwargs["session_id"] == "sid-1"


@pytest.mark.asyncio
async def test_run_parallel_eval_uses_provider_router_twice_no_sdk_or_opus():
    from app.server.session_evaluator import _run_parallel_eval

    session = _make_session()
    router_mock = AsyncMock(
        side_effect=[
            (0, _eval_text(9.0), 0.02, None),
            (0, _eval_text(5.0), 0.01, None),
        ]
    )

    with patch("app.server.session_evaluator.run_via_provider", router_mock), patch(
        "app.server.session_evaluator._run_claude_via_sdk", create=True
    ) as sdk_mock:
        score, text, label, consensus = await _run_parallel_eval(session, "eval spec")

    assert score == pytest.approx(7.0)
    assert label == "sonnet+haiku"
    assert consensus == "sonnet=9.0 haiku=5.0 delta=4.0"
    assert "OVERALL: 9.0/10" in text
    assert router_mock.await_count == 2
    assert not sdk_mock.called, "evaluator must not call Anthropic SDK directly"
    task_classes = [c.kwargs["task_class"] for c in router_mock.await_args_list]
    assert task_classes == ["single-sonnet", "single-haiku"]
    assert {c.kwargs["role"] for c in router_mock.await_args_list} == {"evaluator"}


@pytest.mark.asyncio
async def test_run_parallel_eval_cached_uses_provider_router_not_anthropic_cache():
    from app.server.session_evaluator import _run_parallel_eval_cached

    session = _make_session()
    router_mock = AsyncMock(return_value=(0, _eval_text(8.0), 0.01, None))

    with patch("app.server.session_evaluator.run_via_provider", router_mock), patch(
        "app.server.session_evaluator._write_sdk_metric"
    ):
        score, text, label, consensus = await _run_parallel_eval_cached(
            session,
            brief_context="brief",
            diff_out="stat",
            diff_context="diff",
            threshold=8,
            sid="sid-cache",
        )

    assert score == pytest.approx(8.0)
    assert label == "sonnet+haiku(cached)"
    assert consensus == "sonnet=8.0 haiku=8.0 delta=0.0"
    assert "OVERALL: 8.0/10" in text
    assert router_mock.await_count == 2
    assert [c.kwargs["task_class"] for c in router_mock.await_args_list] == [
        "cached-sonnet",
        "cached-haiku",
    ]
    assert {c.kwargs["role"] for c in router_mock.await_args_list} == {"evaluator"}


@pytest.mark.asyncio
async def test_persona_review_uses_provider_router_for_each_persona(tmp_path):
    from app.server.session_evaluator import _run_persona_review

    workspace = tmp_path
    (workspace / "file.py").write_text("print('hello')\n")
    session = _make_session(str(workspace))
    session._brief_context_for_persona = "brief"
    router_mock = AsyncMock(return_value=(0, "[]", 0.01, None))

    with patch("app.server.session_evaluator.run_via_provider", router_mock):
        findings = await _run_persona_review(session, str(workspace))

    assert findings == []
    assert router_mock.await_count == 4
    assert {c.kwargs["role"] for c in router_mock.await_args_list} == {"evaluator"}
    assert [c.kwargs["task_class"] for c in router_mock.await_args_list] == [
        "persona-correctness",
        "persona-testing",
        "persona-scope",
        "persona-standards",
    ]
