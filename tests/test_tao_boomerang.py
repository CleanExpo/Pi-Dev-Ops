"""tests/test_tao_boomerang.py — RA-1994 regression coverage.

Mocks `_run_claude_via_sdk` so every test is deterministic and runs
in milliseconds. The summary-stripping logic + parallel dispatch +
error-as-data contract are exercised independently of the SDK.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server import tao_boomerang as tb  # noqa: E402


# ── Summary stripping ───────────────────────────────────────────────────────


def test_strip_leading_sure_prefix():
    assert tb._strip_summary_artifacts("Sure, the answer is 42.") == "the answer is 42."
    assert tb._strip_summary_artifacts("Sure! 42") == "42"


def test_strip_here_is_the_answer_prefix():
    assert tb._strip_summary_artifacts("Here is the answer: 42") == "42"


def test_strip_the_answer_is_prefix():
    assert tb._strip_summary_artifacts("The answer is: 42") == "42"


def test_strip_unwraps_full_markdown_block():
    body = "```python\nprint('hi')\n```"
    assert tb._strip_summary_artifacts(body) == "print('hi')"


def test_strip_does_not_unwrap_partial_markdown():
    """Only unwraps when the WHOLE response is wrapped, not when only
    part of the answer is fenced."""
    body = "Yes:\n```\nfoo\n```\nDetails follow."
    out = tb._strip_summary_artifacts(body)
    assert "```" in out  # preserved


def test_strip_trailing_let_me_know_footer():
    body = "The answer is 42.\n\nLet me know if you need anything else."
    assert "Let me know" not in tb._strip_summary_artifacts(body)


def test_strip_idempotent():
    once = tb._strip_summary_artifacts("Sure, 42.")
    twice = tb._strip_summary_artifacts(once)
    assert once == twice == "42."


def test_strip_preserves_legitimate_content():
    """A reply that incidentally contains 'Sure' in the middle stays intact."""
    body = "It depends. Sure, in some cases yes."
    assert tb._strip_summary_artifacts(body) == body


# ── Build prompt ─────────────────────────────────────────────────────────────


def test_build_prompt_wraps_question():
    out = tb._build_prompt("What is 2+2?")
    assert "Respond with ONLY the answer" in out
    assert "What is 2+2?" in out


def test_build_prompt_strips_whitespace():
    out = tb._build_prompt("   What is X?   ")
    # The question portion should be trimmed
    assert "What is X?" in out
    assert "   What is X?   " not in out


# ── BoomerangResult ──────────────────────────────────────────────────────────


def test_result_is_unknown_true_on_sentinel():
    r = tb.BoomerangResult(question="q", summary="UNKNOWN: not enough context")
    assert r.is_unknown is True


def test_result_is_unknown_false_on_real_answer():
    r = tb.BoomerangResult(question="q", summary="42")
    assert r.is_unknown is False


def test_result_defaults():
    r = tb.BoomerangResult(question="q")
    assert r.summary == ""
    assert r.error is None
    assert r.cost_usd == 0.0


# ── BoomerangBatch ───────────────────────────────────────────────────────────


def test_batch_total_cost_aggregates():
    b = tb.BoomerangBatch(results=[
        tb.BoomerangResult(question="a", cost_usd=0.001),
        tb.BoomerangResult(question="b", cost_usd=0.002),
    ])
    assert b.total_cost_usd == 0.003


def test_batch_all_succeeded_true_when_no_errors():
    b = tb.BoomerangBatch(results=[
        tb.BoomerangResult(question="a", summary="x"),
        tb.BoomerangResult(question="b", summary="y"),
    ])
    assert b.all_succeeded is True


def test_batch_all_succeeded_false_when_any_error():
    b = tb.BoomerangBatch(results=[
        tb.BoomerangResult(question="a", summary="x"),
        tb.BoomerangResult(question="b", error="timeout"),
    ])
    assert b.all_succeeded is False


def test_batch_empty():
    b = tb.BoomerangBatch()
    assert b.total_cost_usd == 0.0
    assert b.all_succeeded is True


# ── dispatch_one integration ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_one_happy_path():
    with patch.object(
        tb, "_run_claude_via_sdk",
        new=AsyncMock(return_value=(0, "Sure, the answer is 42.", 0.0012)),
    ) as mock_sdk:
        r = await tb.dispatch_one("What is 6*7?")
    assert r.error is None
    assert r.summary == "the answer is 42."
    assert r.cost_usd == 0.0012
    assert r.rc == 0
    # Verify the wrapped prompt was sent
    mock_sdk.assert_called_once()
    sent_prompt = mock_sdk.call_args.kwargs["prompt"]
    assert "What is 6*7?" in sent_prompt
    assert "Respond with ONLY the answer" in sent_prompt
    # Cost-control flags
    assert mock_sdk.call_args.kwargs["thinking"] == "disabled"


@pytest.mark.asyncio
async def test_dispatch_one_timeout_returns_error():
    import asyncio
    async def _slow(**_):
        await asyncio.sleep(10)
        return (0, "x", 0.0)
    with patch.object(tb, "_run_claude_via_sdk", new=_slow):
        r = await tb.dispatch_one("q", timeout_s=0)
    assert r.error == "timeout"
    assert r.summary == ""


@pytest.mark.asyncio
async def test_dispatch_one_sdk_exception_returns_error_as_data():
    with patch.object(
        tb, "_run_claude_via_sdk",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        r = await tb.dispatch_one("q")
    assert r.error is not None
    assert "sdk_error" in r.error
    assert r.summary == ""


@pytest.mark.asyncio
async def test_dispatch_one_nonzero_rc_recorded():
    with patch.object(
        tb, "_run_claude_via_sdk",
        new=AsyncMock(return_value=(1, "partial", 0.0)),
    ):
        r = await tb.dispatch_one("q")
    assert r.error == "rc=1"


@pytest.mark.asyncio
async def test_dispatch_one_unknown_response_passes_through():
    with patch.object(
        tb, "_run_claude_via_sdk",
        new=AsyncMock(return_value=(
            0, "UNKNOWN: needs Q4 financials I don't have", 0.0,
        )),
    ):
        r = await tb.dispatch_one("Q4 revenue?")
    assert r.error is None
    assert r.is_unknown is True


# ── boomerang (parallel) ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_boomerang_empty_questions_returns_empty_batch():
    batch = await tb.boomerang([])
    assert batch.results == []
    assert batch.total_cost_usd == 0.0


@pytest.mark.asyncio
async def test_boomerang_dispatches_all_questions():
    """Three questions → three SDK calls → three results, in order."""
    responses = [
        (0, "answer 1", 0.001),
        (0, "answer 2", 0.002),
        (0, "answer 3", 0.003),
    ]
    call_count = {"n": 0}
    async def _seq(**_kwargs):
        i = call_count["n"]
        call_count["n"] += 1
        return responses[i]
    with patch.object(tb, "_run_claude_via_sdk", new=_seq):
        batch = await tb.boomerang(["q1", "q2", "q3"])
    assert len(batch.results) == 3
    summaries = [r.summary for r in batch.results]
    assert sorted(summaries) == ["answer 1", "answer 2", "answer 3"]
    assert batch.total_cost_usd == 0.006
    assert batch.all_succeeded is True


@pytest.mark.asyncio
async def test_boomerang_partial_failure_marks_batch_not_succeeded():
    async def _mixed(**kwargs):
        if "q2" in kwargs["prompt"]:
            return (1, "", 0.0)
        return (0, "ok", 0.001)
    with patch.object(tb, "_run_claude_via_sdk", new=_mixed):
        batch = await tb.boomerang(["q1", "q2", "q3"])
    assert batch.all_succeeded is False
    errors = [r.error for r in batch.results]
    assert errors.count(None) == 2
    assert "rc=1" in [e for e in errors if e][0]


@pytest.mark.asyncio
async def test_boomerang_max_parallel_caps_concurrency():
    """Hand 10 questions with max_parallel=2 — at most 2 concurrent."""
    import asyncio
    in_flight = {"now": 0, "max": 0}
    async def _track(**_kwargs):
        in_flight["now"] += 1
        in_flight["max"] = max(in_flight["max"], in_flight["now"])
        await asyncio.sleep(0.01)
        in_flight["now"] -= 1
        return (0, "x", 0.0)
    with patch.object(tb, "_run_claude_via_sdk", new=_track):
        await tb.boomerang(
            [f"q{i}" for i in range(10)], max_parallel=2,
        )
    assert in_flight["max"] <= 2


# ── Constants / public surface ───────────────────────────────────────────────


def test_default_timeout_is_120():
    assert tb.DEFAULT_TIMEOUT_S == 120


def test_summary_preamble_constrains_output():
    assert "ONLY" in tb.SUMMARY_PREAMBLE
    assert "UNKNOWN:" in tb.SUMMARY_PREAMBLE
