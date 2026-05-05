"""tests/test_tao_loop.py — RA-1970 unit tests for run_until_done.

Mocks `_run_claude_via_sdk` (worker step) and `tao_judge.judge` (verdict)
separately so every test is deterministic and runs in milliseconds.
"""
from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


pytestmark = pytest.mark.asyncio


def _reload_modules(monkeypatch, **env):
    """Reload kill_switch + tao_loop with patched env so LoopCounter limits
    pick up env values at construction time."""
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, str(v))
    import app.server.kill_switch as ks
    importlib.reload(ks)
    import app.server.tao_loop as tl
    importlib.reload(tl)
    return tl


def _verdict(reason="STILL_WORKING", done=False, score=0.5):
    from app.server.tao_judge import JudgeVerdict
    return JudgeVerdict(
        done=done, reason=reason, score=score, next_action_hint="x",
    )


async def test_happy_path_done_after_two_iters(monkeypatch):
    tl = _reload_modules(
        monkeypatch,
        TAO_MAX_ITERS="100",
        TAO_MAX_COST_USD="100.00",
        TAO_HARD_STOP_FILE="/nonexistent/HARD_STOP",
    )

    sdk = AsyncMock(return_value=(0, "ok", 0.0))
    judge_mock = AsyncMock(side_effect=[
        _verdict(reason="STILL_WORKING", done=False, score=0.3),
        _verdict(reason="GOAL_MET", done=True, score=0.95),
    ])

    with patch.object(tl, "_run_worker_step", sdk), \
         patch.object(tl, "judge", judge_mock), \
         patch.object(tl, "_build_state", lambda i, w: __import__("app.server.tao_judge", fromlist=["JudgeState"]).JudgeState(iters=i)):
        result = await tl.run_until_done(goal="g", workspace="/tmp/x")

    assert result.iters == 2
    assert result.reason == "GOAL_MET"
    assert result.done is True
    assert len(result.judge_history) == 2


async def test_max_iters_abort(monkeypatch):
    tl = _reload_modules(
        monkeypatch,
        TAO_MAX_ITERS="3",
        TAO_MAX_COST_USD="100.00",
        TAO_HARD_STOP_FILE="/nonexistent/HARD_STOP",
    )

    sdk = AsyncMock(return_value=(0, "", 0.0))
    judge_mock = AsyncMock(return_value=_verdict(reason="STILL_WORKING", done=False))

    with patch.object(tl, "_run_worker_step", sdk), \
         patch.object(tl, "judge", judge_mock), \
         patch.object(tl, "_build_state", lambda i, w: __import__("app.server.tao_judge", fromlist=["JudgeState"]).JudgeState(iters=i)):
        result = await tl.run_until_done(goal="g", workspace="/tmp/x")

    assert result.reason == "MAX_ITERS"
    assert result.iters in (3, 4)
    assert result.done is False


async def test_hard_stop_precedence(monkeypatch, tmp_path: Path):
    hs = tmp_path / "HARD_STOP"
    hs.write_text("stop")

    tl = _reload_modules(
        monkeypatch,
        TAO_MAX_ITERS="100",
        TAO_MAX_COST_USD="100.00",
        TAO_HARD_STOP_FILE=str(hs),
    )

    sdk = AsyncMock(return_value=(0, "", 0.0))
    judge_mock = AsyncMock(return_value=_verdict())

    with patch.object(tl, "_run_worker_step", sdk), \
         patch.object(tl, "judge", judge_mock):
        result = await tl.run_until_done(goal="g", workspace="/tmp/x")

    assert result.reason == "HARD_STOP"
    assert result.iters == 0
    sdk.assert_not_awaited()


async def test_judge_every_n_iters_skips_intermediate(monkeypatch):
    tl = _reload_modules(
        monkeypatch,
        TAO_MAX_ITERS="6",
        TAO_MAX_COST_USD="100.00",
        TAO_HARD_STOP_FILE="/nonexistent/HARD_STOP",
    )

    sdk = AsyncMock(return_value=(0, "", 0.0))
    judge_mock = AsyncMock(return_value=_verdict(reason="STILL_WORKING", done=False))

    with patch.object(tl, "_run_worker_step", sdk), \
         patch.object(tl, "judge", judge_mock), \
         patch.object(tl, "_build_state", lambda i, w: __import__("app.server.tao_judge", fromlist=["JudgeState"]).JudgeState(iters=i)):
        await tl.run_until_done(
            goal="g", workspace="/tmp/x", judge_every_n_iters=2,
        )

    # MAX_ITERS=6 → loop runs 7 ticks (last over-limit). Worker called 6 times,
    # judge called only on iters 2, 4, 6 = 3 invocations.
    assert judge_mock.await_count == 3


async def test_on_event_callback_invoked(monkeypatch):
    tl = _reload_modules(
        monkeypatch,
        TAO_MAX_ITERS="2",
        TAO_MAX_COST_USD="100.00",
        TAO_HARD_STOP_FILE="/nonexistent/HARD_STOP",
    )

    events: list[dict] = []

    sdk = AsyncMock(return_value=(0, "", 0.0))
    judge_mock = AsyncMock(return_value=_verdict(reason="STILL_WORKING", done=False))

    with patch.object(tl, "_run_worker_step", sdk), \
         patch.object(tl, "judge", judge_mock), \
         patch.object(tl, "_build_state", lambda i, w: __import__("app.server.tao_judge", fromlist=["JudgeState"]).JudgeState(iters=i)):
        await tl.run_until_done(
            goal="g", workspace="/tmp/x", on_event=events.append,
        )

    assert events, "on_event callback should have been invoked"
    for ev in events:
        assert ev["action"] == "iter_complete"
        assert "iters" in ev


async def test_max_cost_abort(monkeypatch):
    tl = _reload_modules(
        monkeypatch,
        TAO_MAX_ITERS="100",
        TAO_MAX_COST_USD="0.10",
        TAO_HARD_STOP_FILE="/nonexistent/HARD_STOP",
    )

    sdk = AsyncMock(return_value=(0, "", 0.05))  # cost per iter = 0.05
    judge_mock = AsyncMock(return_value=_verdict(reason="STILL_WORKING", done=False))

    with patch.object(tl, "_run_worker_step", sdk), \
         patch.object(tl, "judge", judge_mock), \
         patch.object(tl, "_build_state", lambda i, w: __import__("app.server.tao_judge", fromlist=["JudgeState"]).JudgeState(iters=i)):
        result = await tl.run_until_done(goal="g", workspace="/tmp/x")

    assert result.reason == "MAX_COST"
    # iter1 cost=0.05 ok, iter2 cost=0.10 not over (strict >), iter3 cost=0.15 over.
    assert result.iters == 3


async def test_explicit_max_iters_override(monkeypatch):
    tl = _reload_modules(
        monkeypatch,
        TAO_MAX_ITERS="100",
        TAO_MAX_COST_USD="100.00",
        TAO_HARD_STOP_FILE="/nonexistent/HARD_STOP",
    )

    sdk = AsyncMock(return_value=(0, "", 0.0))
    judge_mock = AsyncMock(return_value=_verdict(reason="STILL_WORKING", done=False))

    with patch.object(tl, "_run_worker_step", sdk), \
         patch.object(tl, "judge", judge_mock), \
         patch.object(tl, "_build_state", lambda i, w: __import__("app.server.tao_judge", fromlist=["JudgeState"]).JudgeState(iters=i)):
        result = await tl.run_until_done(
            goal="g", workspace="/tmp/x", max_iters=2,
        )

    assert result.reason == "MAX_ITERS"
    assert result.iters in (2, 3)


async def test_loop_result_dataclass_shape(monkeypatch):
    """Sanity check: LoopResult fields are populated, judge_history contains
    JudgeVerdict instances, final_state contains a JudgeState."""
    tl = _reload_modules(
        monkeypatch,
        TAO_MAX_ITERS="100",
        TAO_MAX_COST_USD="100.00",
        TAO_HARD_STOP_FILE="/nonexistent/HARD_STOP",
    )

    sdk = AsyncMock(return_value=(0, "", 0.0))
    judge_mock = AsyncMock(return_value=_verdict(reason="GOAL_MET", done=True, score=1.0))

    with patch.object(tl, "_run_worker_step", sdk), \
         patch.object(tl, "judge", judge_mock), \
         patch.object(tl, "_build_state", lambda i, w: __import__("app.server.tao_judge", fromlist=["JudgeState"]).JudgeState(iters=i)):
        result = await tl.run_until_done(goal="g", workspace="/tmp/x")

    from app.server.tao_judge import JudgeState, JudgeVerdict
    assert isinstance(result.final_state, JudgeState)
    assert all(isinstance(v, JudgeVerdict) for v in result.judge_history)
    assert result.iters == 1
    assert result.done is True
