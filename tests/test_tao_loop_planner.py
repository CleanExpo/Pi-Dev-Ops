"""tests/test_tao_loop_planner.py — opt-in lookahead integration in run_until_done.

Verifies the planner_horizon path: a plan is built up front, the active step is
folded into each worker prompt, the plan advances per iteration, and a judge
INSUFFICIENT_PROGRESS verdict triggers a re-plan. Default (None) must be
byte-identical to the reactive loop — make_plan is never called.

Mocks _run_worker_step, judge, and make_plan separately so tests are
deterministic and SDK-free (mirrors tests/test_tao_loop.py).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


pytestmark = pytest.mark.asyncio


def _reload_modules(monkeypatch, **env):
    """Patch env limits without reloading kill_switch (RA-6869)."""
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, str(v))
    import app.server.tao_loop as tl
    return tl


def _verdict(reason="STILL_WORKING", done=False, score=0.5):
    from app.server.tao_judge import JudgeVerdict
    return JudgeVerdict(done=done, reason=reason, score=score, next_action_hint="x")


def _state(i, w):
    from app.server.tao_judge import JudgeState
    return JudgeState(iters=i)


_GREEN_ENV = dict(
    TAO_MAX_ITERS="100",
    TAO_MAX_COST_USD="100.00",
    TAO_HARD_STOP_FILE="/nonexistent/HARD_STOP",
)


async def test_planner_horizon_feeds_active_step_into_worker(monkeypatch):
    tl = _reload_modules(monkeypatch, **_GREEN_ENV)
    from app.server.tao_planner import Plan
    plan = Plan.from_steps("g", ["alpha", "beta"], horizon=15)

    make_plan_mock = AsyncMock(return_value=plan)
    sdk = AsyncMock(return_value=(0, "ok", 0.0))
    judge_mock = AsyncMock(side_effect=[
        _verdict("STILL_WORKING", False, 0.3),
        _verdict("GOAL_MET", True, 0.95),
    ])

    with patch.object(tl, "_run_worker_step", sdk), \
         patch.object(tl, "judge", judge_mock), \
         patch.object(tl, "make_plan", make_plan_mock), \
         patch.object(tl, "_build_state", _state):
        result = await tl.run_until_done(
            goal="g", workspace="/tmp/x", planner_horizon=15,
        )

    make_plan_mock.assert_awaited_once()
    # iter 1 runs the active step "alpha"; iter 2 advanced to "beta".
    first_goal = sdk.await_args_list[0].kwargs["goal"]
    second_goal = sdk.await_args_list[1].kwargs["goal"]
    assert "alpha" in first_goal and "g" in first_goal
    assert "beta" in second_goal
    assert result.reason == "GOAL_MET"


async def test_planner_replans_on_insufficient_progress(monkeypatch):
    tl = _reload_modules(monkeypatch, **_GREEN_ENV)
    from app.server.tao_planner import Plan
    plan1 = Plan.from_steps("g", ["alpha"], horizon=15)
    plan2 = Plan.from_steps("g", ["recovery"], horizon=15)

    make_plan_mock = AsyncMock(side_effect=[plan1, plan2])
    sdk = AsyncMock(return_value=(0, "ok", 0.0))
    judge_mock = AsyncMock(side_effect=[
        _verdict("INSUFFICIENT_PROGRESS", False, 0.2),
        _verdict("GOAL_MET", True, 0.95),
    ])

    with patch.object(tl, "_run_worker_step", sdk), \
         patch.object(tl, "judge", judge_mock), \
         patch.object(tl, "make_plan", make_plan_mock), \
         patch.object(tl, "_build_state", _state):
        result = await tl.run_until_done(
            goal="g", workspace="/tmp/x", planner_horizon=15,
        )

    assert make_plan_mock.await_count == 2  # initial + one re-plan
    second_goal = sdk.await_args_list[1].kwargs["goal"]
    assert "recovery" in second_goal
    assert result.reason == "GOAL_MET"


async def test_planner_replans_when_horizon_exhausted(monkeypatch):
    tl = _reload_modules(monkeypatch, **_GREEN_ENV)
    from app.server.tao_planner import Plan
    plan1 = Plan.from_steps("g", ["only-step"], horizon=15)
    plan2 = Plan.from_steps("g", ["fresh-step"], horizon=15)

    make_plan_mock = AsyncMock(side_effect=[plan1, plan2])
    sdk = AsyncMock(return_value=(0, "ok", 0.0))
    # never satisfied on iter 1 (still working, but step list exhausted),
    # done on iter 2 with the re-planned step.
    judge_mock = AsyncMock(side_effect=[
        _verdict("STILL_WORKING", False, 0.4),
        _verdict("GOAL_MET", True, 0.95),
    ])

    with patch.object(tl, "_run_worker_step", sdk), \
         patch.object(tl, "judge", judge_mock), \
         patch.object(tl, "make_plan", make_plan_mock), \
         patch.object(tl, "_build_state", _state):
        result = await tl.run_until_done(
            goal="g", workspace="/tmp/x", planner_horizon=15,
        )

    assert make_plan_mock.await_count == 2  # initial + re-plan after exhaustion
    second_goal = sdk.await_args_list[1].kwargs["goal"]
    assert "fresh-step" in second_goal
    assert result.reason == "GOAL_MET"


async def test_no_planner_horizon_skips_planner_entirely(monkeypatch):
    tl = _reload_modules(monkeypatch, **_GREEN_ENV)
    make_plan_mock = AsyncMock()
    sdk = AsyncMock(return_value=(0, "ok", 0.0))
    judge_mock = AsyncMock(side_effect=[_verdict("GOAL_MET", True, 0.95)])

    with patch.object(tl, "_run_worker_step", sdk), \
         patch.object(tl, "judge", judge_mock), \
         patch.object(tl, "make_plan", make_plan_mock), \
         patch.object(tl, "_build_state", _state):
        result = await tl.run_until_done(goal="g", workspace="/tmp/x")

    make_plan_mock.assert_not_awaited()
    # raw goal passed straight through, no plan wrapping.
    assert sdk.await_args.kwargs["goal"] == "g"
    assert result.reason == "GOAL_MET"
