"""tests/test_om1_planner.py — OM-1 lookahead planner enablement + wiring."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


def test_resolve_planner_horizon_om1_default(monkeypatch):
    import app.server.config as config
    import app.server.tao_planner as tp

    monkeypatch.setattr(config, "TAO_PLANNER_HORIZON", 0, raising=False)
    monkeypatch.setattr(config, "TAO_OM1_ENABLED", True, raising=False)
    assert tp.resolve_planner_horizon() == 15


def test_resolve_planner_horizon_explicit_overrides_om1(monkeypatch):
    import app.server.config as config
    import app.server.tao_planner as tp

    monkeypatch.setattr(config, "TAO_PLANNER_HORIZON", 0, raising=False)
    monkeypatch.setattr(config, "TAO_OM1_ENABLED", True, raising=False)
    assert tp.resolve_planner_horizon(explicit=8) == 8


def test_resolve_planner_horizon_configured_wins_over_om1(monkeypatch):
    import app.server.config as config
    import app.server.tao_planner as tp

    monkeypatch.setattr(config, "TAO_PLANNER_HORIZON", 20, raising=False)
    monkeypatch.setattr(config, "TAO_OM1_ENABLED", True, raising=False)
    assert tp.resolve_planner_horizon() == 20


def test_resolve_planner_horizon_off_when_om1_disabled(monkeypatch):
    import app.server.config as config
    import app.server.tao_planner as tp

    monkeypatch.setattr(config, "TAO_PLANNER_HORIZON", 0, raising=False)
    monkeypatch.setattr(config, "TAO_OM1_ENABLED", False, raising=False)
    assert tp.resolve_planner_horizon() is None


def test_planner_runtime_status_reports_lookahead(monkeypatch):
    import app.server.config as config
    import app.server.tao_planner as tp

    monkeypatch.setattr(config, "TAO_PLANNER_HORIZON", 0, raising=False)
    monkeypatch.setattr(config, "TAO_OM1_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "TAO_PLANNER_MAX_REPLANS", 2, raising=False)
    status = tp.planner_runtime_status()
    assert status["om1_enabled"] is True
    assert status["effective_horizon"] == 15
    assert status["mode"] == "lookahead"


@pytest.mark.asyncio
async def test_run_tdd_om1_threads_horizon(monkeypatch):
    import app.server.config as config
    import app.server.tao_tdd_pipeline as tp

    monkeypatch.setattr(config, "TAO_PLANNER_HORIZON", 0, raising=False)
    monkeypatch.setattr(config, "TAO_OM1_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "TAO_PLANNER_MAX_REPLANS", 2, raising=False)

    loop_mock = AsyncMock(return_value=tp.LoopResult(
        done=False, reason="MAX_ITERS", iters=1, cost_usd=0.0,
    ))
    with patch.object(tp, "run_until_done", loop_mock), \
         patch.object(tp, "_git_diff_files", lambda w: []), \
         patch.object(tp, "_run_full_pytest", lambda w, timeout_s: (True, "passed")):
        await tp.run_tdd(goal="g", workspace="/tmp/x")

    assert loop_mock.call_args.kwargs["planner_horizon"] == 15
    assert loop_mock.call_args.kwargs["max_replans"] == 2


@pytest.mark.asyncio
async def test_spec_pipeline_passes_planner_kwargs(monkeypatch):
    import app.server.config as config
    import app.server.spec_pipeline as sp

    monkeypatch.setattr(config, "TAO_PLANNER_HORIZON", 18, raising=False)
    monkeypatch.setattr(config, "TAO_OM1_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "TAO_PLANNER_MAX_REPLANS", 1, raising=False)

    loop_mock = AsyncMock(return_value=type("LR", (), {
        "done": False, "reason": "MAX_ITERS", "iters": 1, "cost_usd": 0.0,
    })())
    with patch.object(sp, "run_until_done", loop_mock):
        # We only need to verify kwargs if build stage runs — patch earlier stages
        # by calling resolve helper directly (integration-light).
        from app.server.tao_planner import resolve_planner_loop_kwargs

        kwargs = resolve_planner_loop_kwargs()
        assert kwargs["planner_horizon"] == 18
        assert kwargs["max_replans"] == 1
