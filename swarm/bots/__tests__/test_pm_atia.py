"""Scaffold tests for swarm/bots/pm_atia.py — PM-ATIA (Catriona Walsh).

Tests verify:
  1. Import succeeds (module loads without error).
  2. Persona prompt contains the persona name + lane keywords.
  3. State JSONL path is correct.
  4. Dry-run executes without firing the LLM and writes a state row.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_pm_atia_imports_cleanly():
    from swarm.bots import pm_atia  # noqa: F401


def test_pm_atia_persona_prompt_contains_name_and_lane():
    from swarm.bots.pm_atia import PERSONA_PROMPT

    assert "Catriona Walsh" in PERSONA_PROMPT, \
        "PERSONA_PROMPT must name the persona Catriona Walsh"
    # Lane keywords — meta association + cross-vertical anchors
    for kw in ("ATIA", "insurance", "sub-bod", "trademark", "conference"):
        assert kw.lower() in PERSONA_PROMPT.lower(), (
            f"PERSONA_PROMPT missing lane keyword: {kw}"
        )


def test_pm_atia_state_path_is_correct():
    from swarm.bots.pm_atia import STATE_FILE_REL, _state_path

    assert STATE_FILE_REL == ".harness/swarm/pm_atia_state.jsonl"
    p = _state_path()
    assert p.is_absolute()
    assert p.name == "pm_atia_state.jsonl"
    assert ".harness/swarm" in str(p)


async def test_pm_atia_dry_run_writes_state_without_llm(tmp_path, monkeypatch):
    """Dry-run path must NOT hit Ollama and must append a row to the JSONL."""
    from swarm.bots import pm_atia

    # Redirect state file into tmp_path so we don't pollute the real ledger.
    fake_state = tmp_path / "pm_atia_state.jsonl"
    monkeypatch.setattr(pm_atia, "_state_path", lambda: fake_state)
    # Stub LLM call so it would explode if accidentally invoked.
    async def _explode(*_a, **_kw):
        raise AssertionError("dry_run must not call the LLM")
    monkeypatch.setattr(pm_atia, "_call_persona", _explode)

    out = await pm_atia.run_pm_atia(session_id="test-dry", dry_run=True, force=True)

    assert out["status"] == "ok_dry_run"
    assert out["persona"].startswith("Catriona Walsh")
    assert out["briefing_path"] is None
    assert fake_state.exists()
    rows = [json.loads(ln) for ln in fake_state.read_text().splitlines() if ln.strip()]
    assert len(rows) == 1
    assert rows[0]["mode"] == "dry_run"
    assert rows[0]["session_id"] == "test-dry"


def test_pm_atia_run_cycle_gates_on_swarm_enabled(monkeypatch):
    """The sync run_cycle entry must skip when TAO_SWARM_ENABLED!=1."""
    from swarm.bots import pm_atia
    monkeypatch.delenv("TAO_SWARM_ENABLED", raising=False)
    out = pm_atia.run_cycle(0, state={})
    assert out["status"] == "skipped"
    assert "TAO_SWARM_ENABLED" in out["reason"]
