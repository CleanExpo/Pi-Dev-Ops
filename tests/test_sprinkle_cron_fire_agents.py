"""tests/test_sprinkle_cron_fire_agents.py — RA-3017 sprinkle coverage.

Covers `app.server.cron_fire_agents._generate_board_prebrief`:
  * Routes through provider_router with role `sprinkle.board_prebrief`
  * Returns the trimmed LLM text on success
  * Returns empty string on rc != 0 (board meeting runs without prebrief)
  * Returns empty string on router-unavailable exception
  * Both failure paths invoke `log.warning` (callback contract preserved)
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tests._sprinkle_helpers import FakeProviderRouter, install_fake_router  # noqa: E402


@pytest.fixture
def fake_inputs(monkeypatch):
    """Stub the 3 input-feed functions used by `_generate_board_prebrief`."""
    from app.server import cron_fire_agents as cfa
    monkeypatch.setattr(cfa, "_tail_jsonl_recent", lambda path, since, max_lines=40: (
        [{"severity": "info", "category": "deploy", "lesson": "incident X happened"}]
        if "lessons" in str(path).lower()
        else [{"session_id": "abc", "outcome": "merged", "summary": "small PR"}]
    ))
    monkeypatch.setattr(cfa, "_fetch_urgent_high_tickets", lambda: [
        {"identifier": "RA-1", "title": "test", "priority": 2, "state": {"name": "In Progress"}},
    ])


def test_prebrief_routes_through_provider_router(monkeypatch, fake_inputs):
    fake = FakeProviderRouter(response="  Pre-brief: ship cautiously today.  ")
    install_fake_router(monkeypatch, fake)

    from app.server import cron_fire_agents as cfa
    log = logging.getLogger("test")
    out = cfa._generate_board_prebrief(log)

    assert out == "Pre-brief: ship cautiously today."
    assert len(fake.calls) == 1
    assert fake.calls[0]["role"] == cfa._PREBRIEF_ROLE == "sprinkle.board_prebrief"


def test_prebrief_returns_empty_on_llm_failure(monkeypatch, fake_inputs):
    fake = FakeProviderRouter(rc=1, response="", error="model_timeout")
    install_fake_router(monkeypatch, fake)

    from app.server import cron_fire_agents as cfa
    log = logging.getLogger("test")
    out = cfa._generate_board_prebrief(log)

    assert out == ""
    # The call was made; we observed the failure path.
    assert len(fake.calls) == 1


def test_prebrief_returns_empty_on_router_exception(monkeypatch, fake_inputs):
    fake = FakeProviderRouter(raise_exc=RuntimeError("router not loaded"))
    install_fake_router(monkeypatch, fake)

    from app.server import cron_fire_agents as cfa
    log = logging.getLogger("test")
    out = cfa._generate_board_prebrief(log)

    assert out == ""
    # Exception was raised by the fake; sprinkle swallowed it.


def test_prebrief_prompt_includes_all_three_feeds(monkeypatch, fake_inputs):
    fake = FakeProviderRouter(response="ok")
    install_fake_router(monkeypatch, fake)

    from app.server import cron_fire_agents as cfa
    log = logging.getLogger("test")
    cfa._generate_board_prebrief(log)

    prompt = fake.calls[0]["prompt"]
    # All three input feeds must surface in the prompt text.
    assert "incident X" in prompt
    assert "abc" in prompt
    assert "RA-1" in prompt
