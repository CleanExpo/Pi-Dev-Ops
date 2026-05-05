"""tests/test_tao_judge.py — RA-1970 unit tests for the judge primitive.

Mocks `_run_claude_via_sdk` to return canned outputs so every test is
deterministic and free of real LLM calls.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest


pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_sdk():
    """Patch the SDK call inside tao_judge with an AsyncMock."""
    with patch("app.server.tao_judge._run_claude_via_sdk", new_callable=AsyncMock) as m:
        yield m


async def test_goal_met_happy_path(mock_sdk):
    from app.server.tao_judge import judge

    payload = json.dumps({
        "done": True,
        "reason": "GOAL_MET",
        "score": 0.95,
        "next_action_hint": "ready to ship",
    })
    mock_sdk.return_value = (0, payload, 0.0)

    verdict = await judge(goal="implement X", workspace="/tmp/x")

    assert verdict.done is True
    assert verdict.reason == "GOAL_MET"
    assert verdict.score == pytest.approx(0.95)
    assert verdict.next_action_hint == "ready to ship"


async def test_tests_fail(mock_sdk):
    from app.server.tao_judge import judge

    payload = json.dumps({
        "done": False,
        "reason": "TESTS_FAIL",
        "score": 0.4,
        "next_action_hint": "fix failing test_foo",
    })
    mock_sdk.return_value = (0, payload, 0.0)

    verdict = await judge(goal="g", workspace="/tmp/x")

    assert verdict.done is False
    assert verdict.reason == "TESTS_FAIL"
    assert verdict.next_action_hint == "fix failing test_foo"


async def test_json_parse_failure_returns_still_working(mock_sdk):
    from app.server.tao_judge import judge

    mock_sdk.return_value = (0, "this is not json at all, just prose", 0.0)

    verdict = await judge(goal="g", workspace="/tmp/x")

    assert verdict.done is False
    assert verdict.reason == "STILL_WORKING"
    assert verdict.score == 0.0
    assert "judge JSON parse failure" in verdict.next_action_hint


async def test_timeout_passed_through(mock_sdk):
    from app.server.tao_judge import judge

    mock_sdk.return_value = (0, '{"done":false,"reason":"STILL_WORKING","score":0.1,"next_action_hint":""}', 0.0)
    await judge(goal="g", workspace="/tmp/x", timeout_s=42)

    _, kwargs = mock_sdk.call_args
    assert kwargs.get("timeout") == 42


async def test_role_is_evaluator(mock_sdk):
    from app.server.tao_judge import judge

    mock_sdk.return_value = (0, '{"done":false,"reason":"STILL_WORKING","score":0.0,"next_action_hint":""}', 0.0)
    await judge(goal="g", workspace="/tmp/x")

    _, kwargs = mock_sdk.call_args
    # phase encodes the role prefix used by RA-1099 model policy.
    assert kwargs.get("phase", "").startswith("evaluator.")


async def test_kill_switch_abort_bubbles(mock_sdk):
    from app.server.kill_switch import KillSwitchAbort
    from app.server.tao_judge import judge

    mock_sdk.side_effect = KillSwitchAbort("HARD_STOP", {"hard_stop_file": "/x"})

    with pytest.raises(KillSwitchAbort) as excinfo:
        await judge(goal="g", workspace="/tmp/x")
    assert excinfo.value.reason == "HARD_STOP"


async def test_invalid_reason_falls_back_to_still_working(mock_sdk):
    from app.server.tao_judge import judge

    payload = json.dumps({
        "done": True,
        "reason": "MADE_UP_REASON",
        "score": 0.99,
        "next_action_hint": "x",
    })
    mock_sdk.return_value = (0, payload, 0.0)

    verdict = await judge(goal="g", workspace="/tmp/x")

    # Invalid reason → STILL_WORKING; done forced false because reason != GOAL_MET.
    assert verdict.reason == "STILL_WORKING"
    assert verdict.done is False
