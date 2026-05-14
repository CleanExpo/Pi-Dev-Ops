"""Scaffold tests for swarm/bots/pm_iep.py — PM-IEP (Dr Aria Whitcombe)."""
from __future__ import annotations

import json

import pytest


def test_pm_iep_imports_cleanly():
    from swarm.bots import pm_iep  # noqa: F401


def test_pm_iep_persona_prompt_contains_name_and_lane():
    from swarm.bots.pm_iep import PERSONA_PROMPT

    assert "Dr Aria Whitcombe" in PERSONA_PROMPT
    for kw in ("IEP", "NIEPA", "Bulcs", "IAQ", "Moisture Meter", "Ivi Sims"):
        assert kw.lower() in PERSONA_PROMPT.lower(), (
            f"PERSONA_PROMPT missing lane keyword: {kw}"
        )


def test_pm_iep_state_path_is_correct():
    from swarm.bots.pm_iep import STATE_FILE_REL, _state_path

    assert STATE_FILE_REL == ".harness/swarm/pm_iep_state.jsonl"
    p = _state_path()
    assert p.name == "pm_iep_state.jsonl"


async def test_pm_iep_dry_run_writes_state_without_llm(tmp_path, monkeypatch):
    from swarm.bots import pm_iep

    fake_state = tmp_path / "pm_iep_state.jsonl"
    monkeypatch.setattr(pm_iep, "_state_path", lambda: fake_state)
    async def _explode(*_a, **_kw):
        raise AssertionError("dry_run must not call the LLM")
    monkeypatch.setattr(pm_iep, "_call_persona", _explode)

    out = await pm_iep.run_pm_iep(session_id="test-dry", dry_run=True, force=True)
    assert out["status"] == "ok_dry_run"
    assert out["persona"].startswith("Dr Aria Whitcombe")
    rows = [json.loads(ln) for ln in fake_state.read_text().splitlines() if ln.strip()]
    assert len(rows) == 1
    assert rows[0]["mode"] == "dry_run"


def test_pm_iep_run_cycle_gates_on_swarm_enabled(monkeypatch):
    from swarm.bots import pm_iep
    monkeypatch.delenv("TAO_SWARM_ENABLED", raising=False)
    out = pm_iep.run_cycle(0, state={})
    assert out["status"] == "skipped"
