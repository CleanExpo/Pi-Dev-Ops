"""RA-8100 B4a: scheduler seam, flag, status snapshot (spec ids F3, E10, T7)."""
from __future__ import annotations

import ast
import asyncio
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.server import cron_scheduler, delivery_reconcile as dr

REPO = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
TICK = NOW.timestamp() - 600
pulses: list[int] = []


class _Stop(Exception):
    pass


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAO_DELIVERY_RECONCILE", raising=False)
    monkeypatch.setattr(dr, "_last_save_ok", None)
    monkeypatch.setattr(dr, "_last_tick_error", None, raising=False)
    monkeypatch.setattr(dr, "_inflight", None)
    pulses.clear()


class _Fut:
    """Stand-in future: records callbacks; result() returns or raises."""

    def __init__(self, outcome: Any = None, exc: BaseException | None = None) -> None:
        self.cbs: list[Any] = []
        self.outcome, self.exc = outcome, exc

    def add_done_callback(self, cb: Any) -> None:
        self.cbs.append(cb)

    def cancelled(self) -> bool:
        return False

    def result(self) -> Any:
        if self.exc:
            raise self.exc
        return self.outcome

    def exception(self) -> BaseException | None:
        return self.exc


class _SpyLoop:
    def __init__(self, fut: _Fut | None = None) -> None:
        self.calls: list[Any] = []
        self.fut = fut or _Fut()

    def run_in_executor(self, executor: Any, fn: Any, *args: Any) -> _Fut:
        self.calls.append(fn)
        return self.fut


class _BoomLoop:
    def run_in_executor(self, *_a: Any, **_k: Any) -> None:
        raise RuntimeError("loop closed")


# ---------------------------------------------------------------- loop drive
def _drive(mp: pytest.MonkeyPatch, on_sleep: Any, fires: list[int]) -> None:
    """Run cron_loop with a fake sleep. on_sleep(n) is awaited at each sleep, n from 1."""
    import app.server.linear_pulse as linear_pulse

    n = {"n": 0}

    async def fake_sleep(seconds: float) -> None:
        n["n"] += 1
        await on_sleep(n["n"])

    async def fake_fire(trigger: dict, log: object) -> None:
        fires.append(n["n"])

    mp.setattr(cron_scheduler, "_load_triggers", lambda: [{"id": "t0"}])
    mp.setattr(cron_scheduler, "_save_triggers", lambda triggers: None)
    mp.setattr(cron_scheduler, "should_fire_on_boot", lambda t: False)
    mp.setattr(cron_scheduler, "_matches", lambda *a: True)
    mp.setattr(cron_scheduler, "_fire_trigger", fake_fire)
    mp.setattr(cron_scheduler.asyncio, "sleep", fake_sleep)
    mp.setenv("PI_CEO_DIGEST_HOURS", "")
    mp.setattr(linear_pulse, "run_pulse", lambda: pulses.append(1))  # never the real pulse
    with pytest.raises(_Stop):
        asyncio.run(cron_scheduler.cron_loop())


def test_f3_tick_does_not_block_next_loop_iteration(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("TAO_DELIVERY_RECONCILE", "canary")
    gate = threading.Event()
    timed_out: list[bool] = []

    def blocking_tick(now: Any = None, path: Any = None) -> dict:
        if not gate.wait(3):
            timed_out.append(True)
        return {"summary_marker": "f3-done"}

    monkeypatch.setattr(dr, "run_reconcile_tick", blocking_tick)
    real_sleep = asyncio.sleep
    fires: list[int] = []
    seen: dict[str, Any] = {}

    async def on_sleep(n: int) -> None:
        if n == 18:  # iteration 17 starts; the tick submitted in iteration 15 is still gated
            seen["fires_before_release"] = list(fires)
            seen["timed_out"] = list(timed_out)
            gate.set()
            for _ in range(200):
                if any("f3-done" in r.getMessage() for r in caplog.records):
                    break
                await real_sleep(0.01)
            raise _Stop

    with caplog.at_level(logging.INFO):
        _drive(monkeypatch, on_sleep, fires)
    assert max(seen["fires_before_release"]) >= 17, seen
    assert seen["timed_out"] == [], "the loop waited for the tick"
    assert any("f3-done" in r.getMessage() for r in caplog.records)
    assert len(pulses) == 1


def test_flag_unset_loop_pulses_once_and_submits_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks: list[int] = []
    monkeypatch.setattr(dr, "run_reconcile_tick", lambda *a, **k: ticks.append(1) or {})
    real_sleep = asyncio.sleep

    async def on_sleep(n: int) -> None:
        if n == 17:
            await real_sleep(0.05)
            raise _Stop

    _drive(monkeypatch, on_sleep, [])
    assert len(pulses) == 1
    assert ticks == []


def test_pulse_that_raises_still_submits(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.server.linear_pulse as linear_pulse

    def bad() -> None:
        raise RuntimeError("pulse down")

    spy: list[Any] = []
    monkeypatch.setattr(linear_pulse, "run_pulse", bad)
    monkeypatch.setattr(dr, "submit_tick", lambda loop, log: spy.append(log))
    asyncio.run(cron_scheduler._pulse_and_reconcile(logging.getLogger("t")))
    assert len(spy) == 1


def test_submit_that_raises_does_not_escape(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.server.linear_pulse as linear_pulse

    def boom(loop: Any, log: Any) -> None:
        raise ValueError("nope")

    monkeypatch.setattr(linear_pulse, "run_pulse", lambda: None)
    monkeypatch.setattr(dr, "submit_tick", boom)
    asyncio.run(cron_scheduler._pulse_and_reconcile(logging.getLogger("t")))


# ---------------------------------------------------------------------- E10
@pytest.mark.parametrize("value", [None, "", "1", "true", "CANARY", "canary now", "off"])
def test_e10_wrong_flag_submits_nothing(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    if value is not None:
        monkeypatch.setenv("TAO_DELIVERY_RECONCILE", value)
    loop = _SpyLoop()
    assert dr.submit_tick(loop, logging.getLogger("t")) is None
    assert loop.calls == []
    assert dr.enabled() is False


def test_e10_canary_submits_exactly_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAO_DELIVERY_RECONCILE", " canary ")
    loop = _SpyLoop()
    dr.submit_tick(loop, logging.getLogger("t"))
    assert loop.calls == [dr.run_reconcile_tick]


def test_submit_never_raises_when_loop_does(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAO_DELIVERY_RECONCILE", "canary")
    dr.submit_tick(_BoomLoop(), logging.getLogger("t"))


def test_done_callback_logs_summary(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("TAO_DELIVERY_RECONCILE", "canary")
    fut = _Fut(outcome={"marker": "sum-123"})
    with caplog.at_level(logging.INFO):
        dr.submit_tick(_SpyLoop(fut), logging.getLogger("t.cb"))
        fut.cbs[0](fut)
    recs = [r for r in caplog.records if "sum-123" in r.getMessage()]
    assert len(recs) == 1 and recs[0].levelno == logging.INFO


def test_done_callback_logs_type_name_only(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("TAO_DELIVERY_RECONCILE", "canary")
    fut = _Fut(exc=KeyError("PLANTED-SECRET-TEXT"))
    with caplog.at_level(logging.INFO):
        dr.submit_tick(_SpyLoop(fut), logging.getLogger("t.cb2"))
        fut.cbs[0](fut)
    errs = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errs) == 1 and "KeyError" in errs[0].getMessage()
    assert "PLANTED-SECRET-TEXT" not in caplog.text
    assert errs[0].exc_info is None


def test_run_reconcile_tick_returns_error_dict_when_tick_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys
    import types

    mod = types.ModuleType("app.server.delivery_reconcile_tick")

    def run_tick(now: Any, path: Any) -> dict:
        raise OSError("disk")

    mod.run_tick = run_tick  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.server.delivery_reconcile_tick", mod)
    out = dr.run_reconcile_tick()
    assert out == {"error": "tick_failed_OSError", "complete": False, "persisted": False}


def test_run_reconcile_tick_error_dict_when_module_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    # None in sys.modules makes the import raise; the real tick must never run from a test.
    monkeypatch.setitem(sys.modules, "app.server.delivery_reconcile_tick", None)
    out = dr.run_reconcile_tick()
    assert out["error"] == "tick_failed_ModuleNotFoundError"
    assert out["complete"] is False and out["persisted"] is False
    assert out["error"].startswith("tick_failed_")


# ------------------------------------------------------- route and imports
def test_route_returns_delivery_reconcile_key() -> None:
    src = (REPO / "app/server/routes/mission_control.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "mission_control_live")
    keys: set[str] = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict):
            keys |= {k.value for k in n.value.keys if isinstance(k, ast.Constant)}
    assert "delivery_reconcile" in keys


FORBIDDEN = ("linear_pulse", "urllib", "requests", "httpx", "supabase_log", "ticket_sweeper_write",
             "session_linear", "ship_gate", "telegram", "slack")


@pytest.mark.parametrize("name", ["delivery_reconcile.py", "delivery_reconcile_status.py"])
def test_modules_import_nothing_that_writes_outside(name: str) -> None:
    path = REPO / "app/server" / name
    assert path.exists(), name  # a missing module fails; it never skips
    mods: list[str] = []
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Import):
            mods += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            mods += [n.module or ""] + [a.name for a in n.names]
    bad = [m for m in mods if any(f in m.lower() for f in FORBIDDEN)]
    assert bad == []
