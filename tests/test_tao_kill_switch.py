"""tests/test_tao_kill_switch.py — RA-1966 integration test.

Proves all three abort paths of `app.server.kill_switch`:
  * MAX_ITERS  — counter exceeds env-set limit
  * MAX_COST   — cumulative cost exceeds env-set limit
  * HARD_STOP  — file existence triggers immediate abort

Plus negative tests:
  * happy path (under limits) does not raise
  * invalid env values fall back to defaults

These tests run in-process — no SDK calls, no subprocesses. Fast; included
in the default pytest gate.
"""
from __future__ import annotations

import importlib

import pytest


def _fresh_module(monkeypatch, **env):
    """Reload the kill_switch module with a clean env so module-level
    factory defaults pick up the patched values for each test."""
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, str(v))
    import app.server.kill_switch as ks
    return importlib.reload(ks)


def test_happy_path_no_abort(monkeypatch):
    ks = _fresh_module(
        monkeypatch,
        TAO_MAX_ITERS="5",
        TAO_MAX_COST_USD="1.00",
        TAO_HARD_STOP_FILE="/nonexistent/path/HARD_STOP",
    )
    counter = ks.LoopCounter()
    for _ in range(4):
        counter.tick(cost_delta_usd=0.10)
    snap = counter.snapshot()
    assert snap["iters"] == 4
    assert snap["cost_usd"] == 0.40
    assert snap["hard_stop_exists"] is False


def test_max_iters_abort(monkeypatch):
    ks = _fresh_module(
        monkeypatch,
        TAO_MAX_ITERS="3",
        TAO_MAX_COST_USD="100.00",
        TAO_HARD_STOP_FILE="/nonexistent/path/HARD_STOP",
    )
    counter = ks.LoopCounter()
    counter.tick()  # iters=1
    counter.tick()  # iters=2
    counter.tick()  # iters=3
    with pytest.raises(ks.KillSwitchAbort) as excinfo:
        counter.tick()  # iters=4 → over limit
    assert excinfo.value.reason == "MAX_ITERS"
    assert excinfo.value.snapshot["iters"] == 4
    assert excinfo.value.snapshot["limit_iters"] == 3


def test_max_cost_abort(monkeypatch):
    ks = _fresh_module(
        monkeypatch,
        TAO_MAX_ITERS="100",
        TAO_MAX_COST_USD="1.00",
        TAO_HARD_STOP_FILE="/nonexistent/path/HARD_STOP",
    )
    counter = ks.LoopCounter()
    counter.tick(cost_delta_usd=0.40)
    counter.tick(cost_delta_usd=0.40)
    with pytest.raises(ks.KillSwitchAbort) as excinfo:
        counter.tick(cost_delta_usd=0.40)  # cumulative 1.20 > 1.00
    assert excinfo.value.reason == "MAX_COST"
    assert excinfo.value.snapshot["cost_usd"] == pytest.approx(1.20, abs=0.01)
    assert excinfo.value.snapshot["limit_cost_usd"] == 1.00


def test_hard_stop_abort(monkeypatch, tmp_path):
    flag = tmp_path / "HARD_STOP"
    flag.write_text("stop")
    ks = _fresh_module(
        monkeypatch,
        TAO_MAX_ITERS="100",
        TAO_MAX_COST_USD="100.00",
        TAO_HARD_STOP_FILE=str(flag),
    )
    counter = ks.LoopCounter()
    with pytest.raises(ks.KillSwitchAbort) as excinfo:
        counter.tick()
    assert excinfo.value.reason == "HARD_STOP"
    assert excinfo.value.snapshot["hard_stop_exists"] is True


def test_hard_stop_check_module_level(monkeypatch, tmp_path):
    """check_hard_stop() should raise even without a counter."""
    flag = tmp_path / "HARD_STOP"
    flag.write_text("stop")
    ks = _fresh_module(monkeypatch, TAO_HARD_STOP_FILE=str(flag))
    with pytest.raises(ks.KillSwitchAbort) as excinfo:
        ks.check_hard_stop()
    assert excinfo.value.reason == "HARD_STOP"


def test_hard_stop_takes_precedence(monkeypatch, tmp_path):
    """When all three would trip, HARD_STOP wins."""
    flag = tmp_path / "HARD_STOP"
    flag.write_text("stop")
    ks = _fresh_module(
        monkeypatch,
        TAO_MAX_ITERS="1",
        TAO_MAX_COST_USD="0.01",
        TAO_HARD_STOP_FILE=str(flag),
    )
    counter = ks.LoopCounter()
    with pytest.raises(ks.KillSwitchAbort) as excinfo:
        counter.tick(cost_delta_usd=10.0)
    assert excinfo.value.reason == "HARD_STOP"


def test_invalid_env_falls_back_to_defaults(monkeypatch):
    ks = _fresh_module(
        monkeypatch,
        TAO_MAX_ITERS="not-a-number",
        TAO_MAX_COST_USD="garbage",
    )
    assert ks.max_iters() == ks.DEFAULT_MAX_ITERS
    assert ks.max_cost_usd() == ks.DEFAULT_MAX_COST_USD


def test_zero_or_negative_env_falls_back(monkeypatch):
    ks = _fresh_module(
        monkeypatch,
        TAO_MAX_ITERS="0",
        TAO_MAX_COST_USD="-1.0",
    )
    assert ks.max_iters() == ks.DEFAULT_MAX_ITERS
    assert ks.max_cost_usd() == ks.DEFAULT_MAX_COST_USD


def test_module_snapshot_diagnostic(monkeypatch):
    ks = _fresh_module(
        monkeypatch,
        TAO_MAX_ITERS="42",
        TAO_MAX_COST_USD="3.50",
        TAO_HARD_STOP_FILE="/nonexistent/path/HARD_STOP",
    )
    snap = ks.snapshot()
    assert snap["max_iters"] == 42
    assert snap["max_cost_usd"] == 3.50
    assert snap["hard_stop_exists"] is False


def test_counter_freezes_limits_at_construction(monkeypatch):
    """Mid-loop env changes do NOT alter an existing counter's limits."""
    ks = _fresh_module(monkeypatch, TAO_MAX_ITERS="3", TAO_MAX_COST_USD="100.00",
                       TAO_HARD_STOP_FILE="/nonexistent/HARD_STOP")
    counter = ks.LoopCounter()
    # Operator widens the limit mid-loop — counter must IGNORE.
    monkeypatch.setenv("TAO_MAX_ITERS", "999")
    counter.tick()
    counter.tick()
    counter.tick()
    with pytest.raises(ks.KillSwitchAbort) as excinfo:
        counter.tick()
    assert excinfo.value.reason == "MAX_ITERS"
    # New counter sees the new env.
    counter2 = ks.LoopCounter()
    assert counter2.snapshot()["limit_iters"] == 999
