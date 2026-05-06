"""tests/test_research_provider.py — RA-2027 Wave 1 SCAN routing tests.

Covers NotebookLM-first routing with Perplexity fallback, $5/day cap
enforcement, no-signal heuristic, persona→notebook mapping, and the
external-signal shortcut.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import research_provider  # noqa: E402


@pytest.fixture
def isolated_ledger(tmp_path, monkeypatch):
    """Redirect the Perplexity ledger to tmp_path so tests don't pollute
    ~/.hermes/."""
    monkeypatch.setattr(
        research_provider, "_PERPLEXITY_LEDGER_PATH",
        tmp_path / "perplexity-ledger.json",
    )
    return tmp_path


@pytest.fixture
def isolated_notebook_map(tmp_path, monkeypatch):
    """Override HERMES_ROOT so discovery-notebooks.json reads from tmp."""
    monkeypatch.setenv("HERMES_ROOT", str(tmp_path))
    return tmp_path


# ── No-signal heuristic ──────────────────────────────────────────────────────


def test_looks_like_no_signal_empty():
    assert research_provider._looks_like_no_signal("") is True
    assert research_provider._looks_like_no_signal("   ") is True


def test_looks_like_no_signal_short_canned_phrases():
    """Short responses with canned 'no info' phrases trigger fallback."""
    samples = [
        "I don't have specific information about that.",
        "The sources don't cover this topic.",
        "Unknown.",
        "Not enough context to answer.",
    ]
    for s in samples:
        assert research_provider._looks_like_no_signal(s) is True


def test_looks_like_no_signal_long_genuine_answer():
    """Long genuine answer that happens to mention 'I don't have' is
    NOT a no-signal."""
    answer = (
        "The IICRC S540 standard covers trauma cleanup. While I don't have "
        "the exact 2026 revisions yet, the current 2018 edition mandates "
        "personal protective equipment, biohazard handling, and a chain-of-"
        "custody protocol. Australian operators must also comply with state "
        "WHS regulators, particularly NSW SafeWork. The standard runs ~280 "
        "pages. Recent industry discussion focuses on extending to crime-"
        "scene sub-categories and updating PPE specs for novel pathogens."
    )
    assert research_provider._looks_like_no_signal(answer) is False


# ── NotebookLM answer → Finding ──────────────────────────────────────────────


def test_notebooklm_answer_to_finding_creates_corpus_finding():
    answer = "RestoreAssist's authority position is built on IICRC compliance and a single national NIR format..."
    finding = research_provider._notebooklm_answer_to_finding(
        answer, persona_id="restoreassist",
        query="what is RA's authority position",
        notebook_name="Pi-CEO — RestoreAssist Knowledge Base",
    )
    assert finding is not None
    assert finding.persona_id == "restoreassist"
    assert finding.source == "notebooklm"
    assert "[corpus]" in finding.title
    assert finding.url.startswith("notebooklm://")
    assert "authority position" in finding.summary.lower() or "IICRC" in finding.summary


def test_notebooklm_answer_to_finding_returns_none_on_no_signal():
    """Empty / canned no-signal answers produce no Finding."""
    finding = research_provider._notebooklm_answer_to_finding(
        "I don't have that.",
        persona_id="restoreassist", query="x", notebook_name="Y",
    )
    assert finding is None


# ── Notebook map override ────────────────────────────────────────────────────


def test_notebook_map_uses_defaults_when_no_override(isolated_notebook_map):
    m = research_provider._load_notebook_map()
    assert m["restoreassist"] == "Pi-CEO — RestoreAssist Knowledge Base"
    assert m["synthex"] == "Pi-CEO — Synthex Knowledge Base"


def test_notebook_map_loads_overrides(isolated_notebook_map):
    override = isolated_notebook_map / "discovery-notebooks.json"
    override.write_text(json.dumps({
        "dr-nrpg": "Pi-CEO — DR-NRPG KB",
        "carsi": "CARSI Courses Content",
    }))
    m = research_provider._load_notebook_map()
    # Defaults preserved
    assert m["restoreassist"] == "Pi-CEO — RestoreAssist Knowledge Base"
    # Overrides applied
    assert m["dr-nrpg"] == "Pi-CEO — DR-NRPG KB"
    assert m["carsi"] == "CARSI Courses Content"


def test_notebook_map_handles_corrupt_override(isolated_notebook_map):
    override = isolated_notebook_map / "discovery-notebooks.json"
    override.write_text("not valid json {{{")
    m = research_provider._load_notebook_map()
    # Falls back to defaults silently
    assert m["restoreassist"] == "Pi-CEO — RestoreAssist Knowledge Base"


# ── Perplexity ledger / cap ──────────────────────────────────────────────────


def test_perplexity_budget_full_when_ledger_empty(isolated_ledger):
    assert research_provider._perplexity_budget_remaining_usd() == \
        research_provider.PERPLEXITY_DAILY_CAP_USD


def test_perplexity_budget_decrements_on_record(isolated_ledger):
    research_provider._record_perplexity_spend(0.50)
    research_provider._record_perplexity_spend(1.00)
    remaining = research_provider._perplexity_budget_remaining_usd()
    assert remaining == pytest.approx(
        research_provider.PERPLEXITY_DAILY_CAP_USD - 1.50,
    )


def test_perplexity_budget_per_day_isolation(isolated_ledger, monkeypatch):
    """Spend on a previous day doesn't count against today's budget."""
    research_provider._record_perplexity_spend(4.00)
    # Monkeypatch the day key so we look at "tomorrow"
    monkeypatch.setattr(
        research_provider, "_ledger_today_key", lambda: "2099-12-31",
    )
    assert research_provider._perplexity_budget_remaining_usd() == \
        research_provider.PERPLEXITY_DAILY_CAP_USD


# ── research() routing ───────────────────────────────────────────────────────


def test_research_returns_empty_on_empty_query(isolated_notebook_map, isolated_ledger):
    assert research_provider.research("", persona_id="restoreassist") == []
    assert research_provider.research("   ", persona_id="restoreassist") == []


def test_research_returns_notebooklm_finding_on_signal(isolated_notebook_map, isolated_ledger):
    canned = "RestoreAssist runs on IICRC S500/S520 compliance; the NIR format is the de facto national standard."
    research_provider.set_notebooklm_caller(lambda nb, q: canned)
    try:
        out = research_provider.research(
            "what is RA's compliance posture",
            persona_id="restoreassist",
        )
    finally:
        research_provider.set_notebooklm_caller(research_provider._default_notebooklm_caller)
    assert len(out) == 1
    assert out[0].source == "notebooklm"
    assert out[0].persona_id == "restoreassist"


def test_research_falls_through_to_perplexity_on_no_signal(isolated_notebook_map, isolated_ledger):
    """When NotebookLM returns no-signal, Perplexity is called."""
    research_provider.set_notebooklm_caller(lambda nb, q: "I don't have that.")
    research_provider.set_perplexity_caller(lambda q: [
        {"title": "External signal X", "url": "http://example/x",
         "summary": "Body", "published_date": "2026-05-06"},
    ])
    try:
        out = research_provider.research(
            "x", persona_id="restoreassist",
        )
    finally:
        research_provider.set_notebooklm_caller(research_provider._default_notebooklm_caller)
        research_provider.set_perplexity_caller(research_provider._default_perplexity_caller)
    assert len(out) == 1
    assert out[0].source == "perplexity"
    assert out[0].title == "External signal X"
    # Spend recorded
    assert research_provider._perplexity_budget_remaining_usd() < \
        research_provider.PERPLEXITY_DAILY_CAP_USD


def test_research_prefer_external_skips_notebooklm(isolated_notebook_map, isolated_ledger):
    """prefer_external=True goes straight to Perplexity (no NotebookLM call)."""
    nlm_calls: list[str] = []
    research_provider.set_notebooklm_caller(
        lambda nb, q: nlm_calls.append(q) or "rich answer"
    )
    research_provider.set_perplexity_caller(lambda q: [
        {"title": "Reg update", "url": "http://gov/u",
         "summary": "Body", "published_date": "2026-05-06"},
    ])
    try:
        out = research_provider.research(
            "regulator update", persona_id="restoreassist",
            prefer_external=True,
        )
    finally:
        research_provider.set_notebooklm_caller(research_provider._default_notebooklm_caller)
        research_provider.set_perplexity_caller(research_provider._default_perplexity_caller)
    assert len(nlm_calls) == 0
    assert len(out) == 1
    assert out[0].source == "perplexity"


def test_research_returns_empty_when_perplexity_budget_exhausted(
    isolated_notebook_map, isolated_ledger,
):
    """Once we cross the $5 cap, Perplexity calls are skipped."""
    research_provider._record_perplexity_spend(5.0)
    research_provider.set_notebooklm_caller(lambda nb, q: "I don't have that.")
    perplexity_calls: list[str] = []
    research_provider.set_perplexity_caller(
        lambda q: perplexity_calls.append(q) or [{"title": "x"}]
    )
    try:
        out = research_provider.research("any query", persona_id="restoreassist")
    finally:
        research_provider.set_notebooklm_caller(research_provider._default_notebooklm_caller)
        research_provider.set_perplexity_caller(research_provider._default_perplexity_caller)
    assert out == []
    assert perplexity_calls == []  # Perplexity not invoked


def test_research_unknown_persona_falls_through_to_perplexity(
    isolated_notebook_map, isolated_ledger,
):
    """A persona without a notebook mapping falls straight to Perplexity."""
    nlm_calls: list[str] = []
    research_provider.set_notebooklm_caller(
        lambda nb, q: nlm_calls.append(q) or "answer"
    )
    research_provider.set_perplexity_caller(lambda q: [
        {"title": "p result", "url": "u", "summary": "s",
         "published_date": "d"},
    ])
    try:
        out = research_provider.research(
            "x", persona_id="some-persona-with-no-notebook",
        )
    finally:
        research_provider.set_notebooklm_caller(research_provider._default_notebooklm_caller)
        research_provider.set_perplexity_caller(research_provider._default_perplexity_caller)
    assert len(nlm_calls) == 0  # No notebook → skip NotebookLM
    assert len(out) == 1
    assert out[0].source == "perplexity"


def test_research_perplexity_caller_raise_returns_empty(
    isolated_notebook_map, isolated_ledger,
):
    research_provider.set_notebooklm_caller(lambda nb, q: "I don't have that.")
    def boom(q):
        raise RuntimeError("api down")
    research_provider.set_perplexity_caller(boom)
    try:
        out = research_provider.research("x", persona_id="restoreassist")
    finally:
        research_provider.set_notebooklm_caller(research_provider._default_notebooklm_caller)
        research_provider.set_perplexity_caller(research_provider._default_perplexity_caller)
    assert out == []
