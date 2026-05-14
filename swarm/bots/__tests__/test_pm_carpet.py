"""Scaffold tests for swarm/bots/pm_carpet.py — PM-Carpet (Toby Carstairs)."""
from __future__ import annotations

import json
from datetime import date

import pytest


def test_pm_carpet_imports_cleanly():
    from swarm.bots import pm_carpet  # noqa: F401


def test_pm_carpet_persona_prompt_contains_name_and_lane():
    from swarm.bots.pm_carpet import PERSONA_PROMPT

    assert "Toby Carstairs" in PERSONA_PROMPT
    for kw in ("CCW", "CCPA", "carpet", "S100", "Moisture Meter"):
        assert kw.lower() in PERSONA_PROMPT.lower(), (
            f"PERSONA_PROMPT missing lane keyword: {kw}"
        )


def test_pm_carpet_state_path_is_correct():
    from swarm.bots.pm_carpet import STATE_FILE_REL, _state_path

    assert STATE_FILE_REL == ".harness/swarm/pm_carpet_state.jsonl"
    p = _state_path()
    assert p.name == "pm_carpet_state.jsonl"


def test_pm_carpet_holiday_window_respected():
    """CCW founder Toby holiday window is 11–25 May 2026."""
    from swarm.bots.pm_carpet import _ccw_holiday_active

    assert _ccw_holiday_active(date(2026, 5, 11)) is True
    assert _ccw_holiday_active(date(2026, 5, 25)) is True
    assert _ccw_holiday_active(date(2026, 5, 14)) is True
    assert _ccw_holiday_active(date(2026, 5, 10)) is False
    assert _ccw_holiday_active(date(2026, 5, 26)) is False


async def test_pm_carpet_dry_run_writes_state_without_llm(tmp_path, monkeypatch):
    from swarm.bots import pm_carpet

    fake_state = tmp_path / "pm_carpet_state.jsonl"
    monkeypatch.setattr(pm_carpet, "_state_path", lambda: fake_state)
    async def _explode(*_a, **_kw):
        raise AssertionError("dry_run must not call the LLM")
    monkeypatch.setattr(pm_carpet, "_call_persona", _explode)

    out = await pm_carpet.run_pm_carpet(session_id="test-dry", dry_run=True, force=True)
    assert out["status"] == "ok_dry_run"
    assert out["persona"].startswith("Toby Carstairs")
    rows = [json.loads(ln) for ln in fake_state.read_text().splitlines() if ln.strip()]
    assert len(rows) == 1
    assert rows[0]["mode"] == "dry_run"
    # Holiday window field is captured.
    assert "ccw_holiday_active" in rows[0]


def test_pm_carpet_run_cycle_gates_on_swarm_enabled(monkeypatch):
    from swarm.bots import pm_carpet
    monkeypatch.delenv("TAO_SWARM_ENABLED", raising=False)
    out = pm_carpet.run_cycle(0, state={})
    assert out["status"] == "skipped"
