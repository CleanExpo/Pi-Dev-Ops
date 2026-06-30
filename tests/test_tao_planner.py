"""tests/test_tao_planner.py — unit tests for the lookahead planner.

The planning brain is orchestrator._decompose_brief; make_plan tests mock it so
they are deterministic and SDK-free. _plan_descriptions is tested against the
real orchestrator topo-sort/brief helpers.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


# ── _plan_descriptions: flatten _decompose_brief output ──────────

def test_plan_descriptions_topo_orders_dicts_and_injects_scenarios():
    from app.server.tao_planner import _plan_descriptions
    tasks = [
        {"id": 2, "title": "B", "brief": "do B", "depends_on": [1],
         "test_scenarios": ["happy: x"], "is_behavioral": True},
        {"id": 1, "title": "A", "brief": "do A", "depends_on": [],
         "test_scenarios": [], "is_behavioral": False},
    ]
    descs = _plan_descriptions(tasks, horizon=15)
    # Topologically ordered: A (no deps) before B (depends on 1).
    assert descs[0].startswith("do A")
    assert descs[1].startswith("do B")
    assert "happy: x" in descs[1]  # scenarios folded into the brief


def test_plan_descriptions_clamps_to_horizon():
    from app.server.tao_planner import _plan_descriptions
    tasks = [{"id": i, "brief": f"t{i}", "depends_on": []} for i in range(10)]
    assert len(_plan_descriptions(tasks, horizon=3)) == 3


def test_plan_descriptions_passes_through_string_fallback():
    from app.server.tao_planner import _plan_descriptions
    assert _plan_descriptions(["alpha", "  ", "beta"], horizon=15) == ["alpha", "beta"]


def test_plan_descriptions_empty_returns_empty():
    from app.server.tao_planner import _plan_descriptions
    assert _plan_descriptions([], horizon=15) == []
    assert _plan_descriptions(None, horizon=15) == []


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


# ── make_plan (backed by _decompose_brief, mocked) ───────────────

@pytest.mark.asyncio
async def test_make_plan_builds_plan_from_decompose(monkeypatch):
    import app.server.tao_planner as tp
    tasks = [
        {"id": 1, "title": "A", "brief": "do A", "depends_on": [], "test_scenarios": []},
        {"id": 2, "title": "B", "brief": "do B", "depends_on": [1], "test_scenarios": []},
    ]
    dec = AsyncMock(return_value=tasks)
    with patch("app.server.orchestrator._decompose_brief", dec):
        plan = await tp.make_plan("goal", "/tmp/x", horizon=15)
    assert [s.description.split("\n")[0] for s in plan.steps] == ["do A", "do B"]
    assert plan.active_step().description.startswith("do A")
    # Decomposition runs on the Opus orchestrator role (RA-1099) inside _decompose_brief.
    assert dec.await_args.kwargs["n_workers"] == 15


@pytest.mark.asyncio
async def test_make_plan_clamps_horizon_to_max():
    import app.server.tao_planner as tp
    tasks = [{"id": i, "brief": f"s{i}", "depends_on": []} for i in range(40)]
    dec = AsyncMock(return_value=tasks)
    with patch("app.server.orchestrator._decompose_brief", dec):
        plan = await tp.make_plan("goal", "/tmp/x", horizon=999)
    assert len(plan.steps) == tp.MAX_HORIZON
    assert dec.await_args.kwargs["n_workers"] == tp.MAX_HORIZON


@pytest.mark.asyncio
async def test_make_plan_falls_back_to_single_step_on_empty():
    import app.server.tao_planner as tp
    dec = AsyncMock(return_value=[])
    with patch("app.server.orchestrator._decompose_brief", dec):
        plan = await tp.make_plan("achieve the goal", "/tmp/x", horizon=15)
    assert [s.description for s in plan.steps] == ["achieve the goal"]


@pytest.mark.asyncio
async def test_make_plan_falls_back_on_decompose_exception():
    import app.server.tao_planner as tp
    dec = AsyncMock(side_effect=RuntimeError("sdk down"))
    with patch("app.server.orchestrator._decompose_brief", dec):
        plan = await tp.make_plan("achieve the goal", "/tmp/x", horizon=15)
    assert [s.description for s in plan.steps] == ["achieve the goal"]


@pytest.mark.asyncio
async def test_make_plan_handles_string_fallback_from_decompose():
    import app.server.tao_planner as tp
    dec = AsyncMock(return_value=["step one", "step two"])
    with patch("app.server.orchestrator._decompose_brief", dec):
        plan = await tp.make_plan("goal", "/tmp/x", horizon=15)
    assert [s.description for s in plan.steps] == ["step one", "step two"]
