"""tests/test_tao_planner.py — unit tests for the lookahead planner.

Mocks `_run_claude_via_sdk` so every test is deterministic and SDK-free,
mirroring tests/test_tao_loop.py / test_tao_judge.py style.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


# ── pure parse helper ────────────────────────────────────────────

def test_parse_steps_extracts_ordered_strings():
    from app.server.tao_planner import _parse_steps
    raw = '{"steps": ["read the failing test", "write the fixture", "run pytest"]}'
    assert _parse_steps(raw, horizon=15) == [
        "read the failing test",
        "write the fixture",
        "run pytest",
    ]


def test_parse_steps_clamps_to_horizon():
    from app.server.tao_planner import _parse_steps
    raw = '{"steps": ["a", "b", "c", "d", "e"]}'
    assert _parse_steps(raw, horizon=3) == ["a", "b", "c"]


def test_parse_steps_tolerates_prose_around_json():
    from app.server.tao_planner import _parse_steps
    raw = 'Sure, here is the plan:\n{"steps": ["x", "y"]}\nHope that helps.'
    assert _parse_steps(raw, horizon=15) == ["x", "y"]


def test_parse_steps_drops_empty_and_nonstring_entries():
    from app.server.tao_planner import _parse_steps
    raw = '{"steps": ["keep", "", "  ", 42, null, "also-keep"]}'
    assert _parse_steps(raw, horizon=15) == ["keep", "also-keep"]


def test_parse_steps_fails_safe_to_empty_on_junk():
    from app.server.tao_planner import _parse_steps
    assert _parse_steps("not json at all", horizon=15) == []
    assert _parse_steps('{"nope": 1}', horizon=15) == []
    assert _parse_steps("", horizon=15) == []


# ── Plan / PlanStep mechanics ────────────────────────────────────

def test_plan_first_step_active_rest_pending():
    from app.server.tao_planner import Plan
    plan = Plan.from_steps("goal", ["one", "two", "three"], horizon=15)
    assert plan.active_step().description == "one"
    assert plan.active_step().status == "active"
    assert [s.status for s in plan.steps] == ["active", "pending", "pending"]


def test_plan_advance_marks_done_and_activates_next():
    from app.server.tao_planner import Plan
    plan = Plan.from_steps("goal", ["one", "two"], horizon=15)
    nxt = plan.advance()
    assert nxt.description == "two"
    assert [s.status for s in plan.steps] == ["done", "active"]


def test_plan_advance_past_end_returns_none_and_exhausts():
    from app.server.tao_planner import Plan
    plan = Plan.from_steps("goal", ["only"], horizon=15)
    assert plan.advance() is None
    assert plan.is_exhausted() is True
    assert plan.active_step() is None


def test_plan_from_steps_empty_falls_back_to_goal():
    from app.server.tao_planner import Plan
    plan = Plan.from_steps("achieve the goal", [], horizon=15)
    assert [s.description for s in plan.steps] == ["achieve the goal"]


# ── format_step_goal ─────────────────────────────────────────────

def test_format_step_goal_embeds_overall_and_active_step():
    from app.server.tao_planner import Plan, format_step_goal
    plan = Plan.from_steps("ship feature X", ["scaffold", "test", "wire"], horizon=15)
    out = format_step_goal(plan, "ship feature X")
    assert "ship feature X" in out
    assert "scaffold" in out
    assert "1/3" in out


def test_format_step_goal_no_active_returns_overall():
    from app.server.tao_planner import Plan, format_step_goal
    plan = Plan.from_steps("g", ["only"], horizon=15)
    plan.advance()  # exhaust
    assert format_step_goal(plan, "g") == "g"


# ── make_plan (SDK-mocked) ───────────────────────────────────────

pytestmark_async = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_make_plan_builds_plan_from_sdk(monkeypatch):
    import app.server.tao_planner as tp
    sdk = AsyncMock(return_value=(0, '{"steps": ["a", "b", "c"]}', 0.0))
    with patch.object(tp, "_run_claude_via_sdk", sdk):
        plan = await tp.make_plan("goal", "/tmp/x", horizon=15)
    assert [s.description for s in plan.steps] == ["a", "b", "c"]
    assert plan.active_step().description == "a"
    # planner role (Opus) must be the model selected
    assert sdk.await_args.kwargs["model"] == tp.select_model("planner")


@pytest.mark.asyncio
async def test_make_plan_clamps_horizon_to_max():
    import app.server.tao_planner as tp
    steps = ",".join(f'"s{i}"' for i in range(40))
    sdk = AsyncMock(return_value=(0, f'{{"steps": [{steps}]}}', 0.0))
    with patch.object(tp, "_run_claude_via_sdk", sdk):
        plan = await tp.make_plan("goal", "/tmp/x", horizon=999)
    assert len(plan.steps) == tp.MAX_HORIZON


@pytest.mark.asyncio
async def test_make_plan_falls_back_to_single_step_on_junk():
    import app.server.tao_planner as tp
    sdk = AsyncMock(return_value=(0, "the planner refused to answer", 0.0))
    with patch.object(tp, "_run_claude_via_sdk", sdk):
        plan = await tp.make_plan("achieve the goal", "/tmp/x", horizon=15)
    assert [s.description for s in plan.steps] == ["achieve the goal"]


@pytest.mark.asyncio
async def test_make_plan_falls_back_on_sdk_error_rc():
    import app.server.tao_planner as tp
    sdk = AsyncMock(return_value=(1, "", 0.0))
    with patch.object(tp, "_run_claude_via_sdk", sdk):
        plan = await tp.make_plan("achieve the goal", "/tmp/x", horizon=15)
    assert [s.description for s in plan.steps] == ["achieve the goal"]
