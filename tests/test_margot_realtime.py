"""tests/test_margot_realtime.py — RA-1903.

Coverage for the [REALTIME] sentinel pipeline (Perplexity Sonar Pro):

  * parse_realtime_requests strips sentinel + extracts topic
  * Multiple [REALTIME] sentinels parsed in one draft
  * Missing topic skipped silently
  * provider_router maps `realtime_lookup` to top tier
  * env override TAO_MODEL_REALTIME_LOOKUP picks the right model
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import margot_bot  # noqa: E402


def test_realtime_parser_basic():
    text = 'I should check that. [REALTIME topic="Anthropic latest model release this week"]'
    requests, cleaned = margot_bot.parse_realtime_requests(text)
    assert len(requests) == 1
    assert requests[0].topic == "Anthropic latest model release this week"
    assert "[REALTIME" not in cleaned


def test_realtime_parser_multiple():
    text = (
        '[REALTIME topic="claude pricing today"] some prose '
        '[REALTIME topic="sonar pro vs deep research benchmarks"]'
    )
    requests, cleaned = margot_bot.parse_realtime_requests(text)
    assert [r.topic for r in requests] == [
        "claude pricing today",
        "sonar pro vs deep research benchmarks",
    ]
    assert "[REALTIME" not in cleaned


def test_realtime_parser_missing_topic():
    """Sentinel without topic attr is silently skipped."""
    text = "[REALTIME]"
    requests, _ = margot_bot.parse_realtime_requests(text)
    assert requests == []


def test_realtime_parser_attrs_order_agnostic():
    """Same order-agnostic robustness as the RA-1885 fix."""
    text = '[REALTIME priority="high" topic="market open AUD/USD"]'
    requests, _ = margot_bot.parse_realtime_requests(text)
    assert len(requests) == 1
    assert requests[0].topic == "market open AUD/USD"


def test_provider_router_realtime_role_in_top_tier():
    """RA-1903: realtime_lookup role mapped to top tier so the per-role
    env override TAO_MODEL_REALTIME_LOOKUP takes precedence over cheap."""
    from app.server.provider_router import ROLE_TIER

    assert ROLE_TIER.get("realtime_lookup") == "top"
    assert ROLE_TIER.get("research.realtime") == "top"


def test_provider_router_realtime_env_override(monkeypatch):
    """TAO_MODEL_REALTIME_LOOKUP=openrouter:perplexity/sonar-pro picks Sonar."""
    monkeypatch.setenv(
        "TAO_MODEL_REALTIME_LOOKUP",
        "openrouter:perplexity/sonar-pro",
    )
    from app.server.provider_router import select_provider_model

    pm = select_provider_model("realtime_lookup")
    assert pm.provider == "openrouter"
    assert pm.model_id == "perplexity/sonar-pro"
    assert pm.source == "env_role_override"


def test_build_prompt_with_research_renders_realtime_section():
    """When realtime_findings is passed, it appears in the Phase-2 prompt."""
    realtime = [
        {"topic": "X", "response": "Live data: foo bar (citation: example.com)",
         "error": None},
    ]
    prompt = margot_bot.build_prompt_with_research(
        user_text="test",
        history=[],
        context={"cfo": [], "cmo": [], "cto": [], "cs": [],
                  "board_recent": [], "ccw": None},
        draft="draft text",
        research_findings=[],
        truth_check_findings=None,
        realtime_findings=realtime,
    )
    assert "Realtime (Perplexity Sonar — current web) findings:" in prompt
    assert "Live data: foo bar" in prompt
    assert "citation: example.com" in prompt
    assert "[REALTIME]" in prompt  # mentioned in the closing instructions


def test_build_prompt_with_research_no_realtime_section_when_empty():
    """When realtime_findings is None or [], no realtime section appears."""
    prompt = margot_bot.build_prompt_with_research(
        user_text="test",
        history=[],
        context={"cfo": [], "cmo": [], "cto": [], "cs": [],
                  "board_recent": [], "ccw": None},
        draft="draft",
        research_findings=[],
        truth_check_findings=None,
        realtime_findings=None,
    )
    assert "Realtime (Perplexity Sonar" not in prompt
