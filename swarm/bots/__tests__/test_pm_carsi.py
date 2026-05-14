"""Scaffold tests for swarm/bots/pm_carsi.py — PM-CARSI (Rohan Mehta)."""
from __future__ import annotations

import json

import pytest


def test_pm_carsi_imports_cleanly():
    from swarm.bots import pm_carsi  # noqa: F401


def test_pm_carsi_persona_prompt_contains_name_and_lane():
    from swarm.bots.pm_carsi import PERSONA_PROMPT

    assert "Rohan Mehta" in PERSONA_PROMPT
    for kw in ("CARSI", "syllab", "S500", "S520", "CPD", "vocational"):
        assert kw.lower() in PERSONA_PROMPT.lower(), (
            f"PERSONA_PROMPT missing lane keyword: {kw}"
        )


def test_pm_carsi_module_docstring_disambiguates_from_duncan():
    """The module docstring must call out the Duncan-work / tax-SME overlap."""
    from swarm.bots import pm_carsi
    assert pm_carsi.__doc__ is not None
    assert "Duncan" in pm_carsi.__doc__, (
        "Module docstring must disambiguate Rohan Mehta from Duncan's tax-SME context"
    )


def test_pm_carsi_state_path_is_correct():
    from swarm.bots.pm_carsi import STATE_FILE_REL, _state_path

    assert STATE_FILE_REL == ".harness/swarm/pm_carsi_state.jsonl"
    p = _state_path()
    assert p.name == "pm_carsi_state.jsonl"


async def test_pm_carsi_dry_run_writes_state_without_llm(tmp_path, monkeypatch):
    from swarm.bots import pm_carsi

    fake_state = tmp_path / "pm_carsi_state.jsonl"
    monkeypatch.setattr(pm_carsi, "_state_path", lambda: fake_state)
    async def _explode(*_a, **_kw):
        raise AssertionError("dry_run must not call the LLM")
    monkeypatch.setattr(pm_carsi, "_call_persona", _explode)

    out = await pm_carsi.run_pm_carsi(session_id="test-dry", dry_run=True, force=True)
    assert out["status"] == "ok_dry_run"
    assert out["persona"].startswith("Rohan Mehta")
    rows = [json.loads(ln) for ln in fake_state.read_text().splitlines() if ln.strip()]
    assert len(rows) == 1
    assert rows[0]["mode"] == "dry_run"
    # Friday-review flag is captured.
    assert "is_friday_review" in rows[0]


def test_pm_carsi_run_cycle_gates_on_swarm_enabled(monkeypatch):
    from swarm.bots import pm_carsi
    monkeypatch.delenv("TAO_SWARM_ENABLED", raising=False)
    out = pm_carsi.run_cycle(0, state={})
    assert out["status"] == "skipped"
