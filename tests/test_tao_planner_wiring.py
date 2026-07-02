"""tests/test_tao_planner_wiring.py — RA-1970 step-3 integration tests.

Covers the lookahead planner's wiring into a real loop entry point plus the
re-plan hard cap (the founder-locked safety bound):

  * OFF path  — run_tdd with TAO_PLANNER_HORIZON=0 passes planner_horizon=None,
                so the loop is byte-identical reactive (planner never invoked).
  * ON path   — run_tdd with TAO_PLANNER_HORIZON=3 threads the horizon through.
  * Cap       — run_until_done never re-plans more than max_replans times, then
                emits planner_replan_capped and degrades to reactive.

Loop internals are mocked (`_run_worker_step`, `judge`, `_build_state`,
`make_plan`) so every test is deterministic and runs in milliseconds.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


pytestmark = pytest.mark.asyncio


def _reload_loop(monkeypatch, **env):
    """Patch env limits without reloading kill_switch (RA-6869)."""
    for k, v in env.items():
        monkeypatch.setenv(k, str(v))
    import app.server.tao_loop as tl
    return tl


def _verdict(reason="STILL_WORKING", done=False, score=0.5):
    from app.server.tao_judge import JudgeVerdict
    return JudgeVerdict(done=done, reason=reason, score=score, next_action_hint="x")


def _state(i, w):
    from app.server.tao_judge import JudgeState
    return JudgeState(iters=i)


# ── run_tdd flag wiring ──────────────────────────────────────────────────────

async def _run_tdd_capturing(monkeypatch, horizon_flag):
    """Run run_tdd with run_until_done mocked; return the captured kwargs."""
    import app.server.tao_tdd_pipeline as tp
    import app.server.config as config
    monkeypatch.setattr(config, "TAO_PLANNER_HORIZON", horizon_flag, raising=False)
    monkeypatch.setattr(config, "TAO_PLANNER_MAX_REPLANS", 2, raising=False)

    loop_mock = AsyncMock(return_value=tp.LoopResult(
        done=False, reason="MAX_ITERS", iters=1, cost_usd=0.0,
    ))
    with patch.object(tp, "run_until_done", loop_mock), \
         patch.object(tp, "_git_diff_files", lambda w: []), \
         patch.object(tp, "_run_full_pytest", lambda w, timeout_s: (True, "passed")):
        await tp.run_tdd(goal="g", workspace="/tmp/x")
    return loop_mock.call_args.kwargs


async def test_flag_off_passes_horizon_none(monkeypatch):
    kwargs = await _run_tdd_capturing(monkeypatch, horizon_flag=0)
    assert kwargs["planner_horizon"] is None
    assert kwargs["max_replans"] == 2


async def test_flag_on_threads_horizon_through(monkeypatch):
    kwargs = await _run_tdd_capturing(monkeypatch, horizon_flag=3)
    assert kwargs["planner_horizon"] == 3


async def test_explicit_arg_overrides_flag(monkeypatch):
    import app.server.tao_tdd_pipeline as tp
    import app.server.config as config
    monkeypatch.setattr(config, "TAO_PLANNER_HORIZON", 0, raising=False)
    monkeypatch.setattr(config, "TAO_PLANNER_MAX_REPLANS", 2, raising=False)
    loop_mock = AsyncMock(return_value=tp.LoopResult(
        done=False, reason="MAX_ITERS", iters=1, cost_usd=0.0,
    ))
    with patch.object(tp, "run_until_done", loop_mock), \
         patch.object(tp, "_git_diff_files", lambda w: []), \
         patch.object(tp, "_run_full_pytest", lambda w, timeout_s: (True, "passed")):
        await tp.run_tdd(goal="g", workspace="/tmp/x", planner_horizon=5)
    assert loop_mock.call_args.kwargs["planner_horizon"] == 5


# ── re-plan hard cap (the founder-locked safety bound) ───────────────────────

async def test_offpath_never_invokes_planner(monkeypatch):
    """planner_horizon=None must leave make_plan completely untouched."""
    tl = _reload_loop(
        monkeypatch, TAO_MAX_ITERS="2", TAO_MAX_COST_USD="100.00",
        TAO_HARD_STOP_FILE="/nonexistent/HARD_STOP",
    )
    make_plan = AsyncMock()
    with patch.object(tl, "_run_worker_step", AsyncMock(return_value=(0, "ok", 0.0))), \
         patch.object(tl, "judge", AsyncMock(return_value=_verdict())), \
         patch.object(tl, "_build_state", _state), \
         patch.object(tl, "make_plan", make_plan):
        await tl.run_until_done(goal="g", workspace="/tmp/x")
    make_plan.assert_not_called()


async def test_replan_respects_hard_cap(monkeypatch):
    """With a plan that exhausts every iteration, make_plan is called at most
    1 (initial) + max_replans times, then the loop emits planner_replan_capped
    and degrades to reactive."""
    tl = _reload_loop(
        monkeypatch, TAO_MAX_ITERS="8", TAO_MAX_COST_USD="100.00",
        TAO_HARD_STOP_FILE="/nonexistent/HARD_STOP",
    )

    def _fresh_plan(*_a, **_k):
        # A one-step plan: after the first advance() it is exhausted, forcing a
        # re-plan on the next iteration.
        return tl.Plan.from_steps("g", ["only-step"], horizon=2)

    make_plan = AsyncMock(side_effect=_fresh_plan)
    events: list[dict] = []
    with patch.object(tl, "_run_worker_step", AsyncMock(return_value=(0, "ok", 0.0))), \
         patch.object(tl, "judge", AsyncMock(return_value=_verdict())), \
         patch.object(tl, "_build_state", _state), \
         patch.object(tl, "make_plan", make_plan):
        result = await tl.run_until_done(
            goal="g", workspace="/tmp/x",
            planner_horizon=2, max_replans=2, on_event=events.append,
        )

    assert make_plan.call_count == 3  # 1 initial + 2 re-plans (cap)
    assert any(e.get("action") == "planner_replan_capped" for e in events)
    assert result.reason == "MAX_ITERS"  # loop ran to completion, never stalled


async def test_zero_replans_degrades_on_first_exhaustion(monkeypatch):
    """max_replans=0 means the initial plan is the only one; first exhaustion
    degrades straight to reactive."""
    tl = _reload_loop(
        monkeypatch, TAO_MAX_ITERS="4", TAO_MAX_COST_USD="100.00",
        TAO_HARD_STOP_FILE="/nonexistent/HARD_STOP",
    )
    make_plan = AsyncMock(side_effect=lambda *a, **k: tl.Plan.from_steps(
        "g", ["only-step"], horizon=1,
    ))
    events: list[dict] = []
    with patch.object(tl, "_run_worker_step", AsyncMock(return_value=(0, "ok", 0.0))), \
         patch.object(tl, "judge", AsyncMock(return_value=_verdict())), \
         patch.object(tl, "_build_state", _state), \
         patch.object(tl, "make_plan", make_plan):
        await tl.run_until_done(
            goal="g", workspace="/tmp/x",
            planner_horizon=1, max_replans=0, on_event=events.append,
        )
    assert make_plan.call_count == 1  # initial only, no re-plans
    assert any(e.get("action") == "planner_replan_capped" for e in events)
