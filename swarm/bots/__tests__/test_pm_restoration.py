"""Scaffold tests for swarm/bots/pm_restoration.py — PM-Restoration (Marcus Bellini)."""
from __future__ import annotations

import json

import pytest


def test_pm_restoration_imports_cleanly():
    from swarm.bots import pm_restoration  # noqa: F401


def test_pm_restoration_persona_prompt_contains_name_and_lane():
    from swarm.bots.pm_restoration import PERSONA_PROMPT

    assert "Marcus Bellini" in PERSONA_PROMPT
    for kw in ("RestoreAssist", "Disaster Recovery", "NRPG", "IICRC", "App Store"):
        assert kw.lower() in PERSONA_PROMPT.lower(), (
            f"PERSONA_PROMPT missing lane keyword: {kw}"
        )


def test_pm_restoration_state_path_is_correct():
    from swarm.bots.pm_restoration import STATE_FILE_REL, _state_path

    assert STATE_FILE_REL == ".harness/swarm/pm_restoration_state.jsonl"
    p = _state_path()
    assert p.is_absolute()
    assert p.name == "pm_restoration_state.jsonl"


async def test_pm_restoration_dry_run_writes_state_without_llm(tmp_path, monkeypatch):
    from swarm.bots import pm_restoration

    fake_state = tmp_path / "pm_restoration_state.jsonl"
    monkeypatch.setattr(pm_restoration, "_state_path", lambda: fake_state)
    async def _explode(*_a, **_kw):
        raise AssertionError("dry_run must not call the LLM")
    monkeypatch.setattr(pm_restoration, "_call_persona", _explode)

    out = await pm_restoration.run_pm_restoration(
        session_id="test-dry", dry_run=True, force=True,
    )
    assert out["status"] == "ok_dry_run"
    assert out["persona"].startswith("Marcus Bellini")
    rows = [json.loads(ln) for ln in fake_state.read_text().splitlines() if ln.strip()]
    assert len(rows) == 1
    assert rows[0]["mode"] == "dry_run"


def test_pm_restoration_run_cycle_gates_on_swarm_enabled(monkeypatch):
    from swarm.bots import pm_restoration
    monkeypatch.delenv("TAO_SWARM_ENABLED", raising=False)
    out = pm_restoration.run_cycle(0, state={})
    assert out["status"] == "skipped"
