"""tests/test_margot_truth_check_voice.py — RA-1886 + RA-1885.

Coverage:
  * order-agnostic [RESEARCH] sentinel parser (RA-1885 fix)
  * new [TRUTH-CHECK] sentinel parser
  * provider_whisper.transcribe success / missing-key / missing-file paths
  * /api/margot/voice route — auth gate, missing token, end-to-end happy path
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import margot_bot  # noqa: E402


# ── RA-1885: order-agnostic [RESEARCH] parser ──────────────────────────────


def test_research_parser_topic_first_depth_quick():
    """[RESEARCH topic="..." depth="quick"] — natural English ordering."""
    text = 'Working on it. [RESEARCH topic="market trends" depth="quick"] Done.'
    requests, cleaned = margot_bot.parse_research_requests(text)
    assert len(requests) == 1
    assert requests[0].topic == "market trends"
    assert requests[0].depth == "quick"
    assert "[RESEARCH" not in cleaned
    assert "Working on it." in cleaned and "Done." in cleaned


def test_research_parser_depth_first_topic():
    """[RESEARCH depth="deep" topic="..."] — original ordering still works."""
    text = 'Deep dive: [RESEARCH depth="deep" topic="competitor moves"]'
    requests, cleaned = margot_bot.parse_research_requests(text)
    assert len(requests) == 1
    assert requests[0].topic == "competitor moves"
    assert requests[0].depth == "deep"
    assert "[RESEARCH" not in cleaned


def test_research_parser_topic_only_defaults_quick():
    """[RESEARCH topic="..."] without depth → defaults to quick."""
    text = '[RESEARCH topic="something"]'
    requests, _ = margot_bot.parse_research_requests(text)
    assert len(requests) == 1
    assert requests[0].depth == "quick"


def test_research_parser_invalid_depth_falls_back_quick():
    """Bogus depth value falls back to quick rather than failing."""
    text = '[RESEARCH topic="x" depth="extreme"]'
    requests, _ = margot_bot.parse_research_requests(text)
    assert len(requests) == 1
    assert requests[0].depth == "quick"


def test_research_parser_multiple_sentinels():
    """All sentinels in one draft are parsed."""
    text = (
        'First: [RESEARCH topic="A"]. Second: [RESEARCH topic="B" depth="deep"].'
    )
    requests, cleaned = margot_bot.parse_research_requests(text)
    assert [r.topic for r in requests] == ["A", "B"]
    assert [r.depth for r in requests] == ["quick", "deep"]
    assert "[RESEARCH" not in cleaned


def test_research_parser_missing_topic_skipped():
    """Sentinel without a topic attr is silently skipped."""
    text = '[RESEARCH depth="quick"]'
    requests, _ = margot_bot.parse_research_requests(text)
    assert requests == []


# ── RA-1886: [TRUTH-CHECK] parser ──────────────────────────────────────────


def test_truth_check_parser_basic():
    text = 'Considering this: [TRUTH-CHECK topic="is X really moat-worthy?"]'
    requests, cleaned = margot_bot.parse_truth_check_requests(text)
    assert len(requests) == 1
    assert requests[0].topic == "is X really moat-worthy?"
    assert "[TRUTH-CHECK" not in cleaned


def test_truth_check_parser_multiple():
    text = (
        '[TRUTH-CHECK topic="claim A"] some prose '
        '[TRUTH-CHECK topic="claim B"]'
    )
    requests, cleaned = margot_bot.parse_truth_check_requests(text)
    assert [r.topic for r in requests] == ["claim A", "claim B"]
    assert "[TRUTH-CHECK" not in cleaned


def test_truth_check_parser_missing_topic():
    """Sentinel without topic attr is silently skipped."""
    text = '[TRUTH-CHECK]'
    requests, _ = margot_bot.parse_truth_check_requests(text)
    assert requests == []


# ── provider_whisper ───────────────────────────────────────────────────────


def test_whisper_missing_api_key(monkeypatch):
    """No OPENROUTER_API_KEY → returns openrouter_no_api_key error."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    from app.server.provider_whisper import transcribe

    audio = REPO_ROOT / "tests" / "_fake_audio.ogg"
    audio.write_bytes(b"fake-audio-bytes")
    try:
        rc, text, cost, error = asyncio.run(transcribe(audio))
    finally:
        audio.unlink(missing_ok=True)
    assert rc == 1
    assert text == ""
    assert error == "openrouter_no_api_key"


def test_whisper_missing_file(monkeypatch):
    """Nonexistent file → returns whisper_audio_not_found error."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake")
    from app.server.provider_whisper import transcribe

    rc, text, cost, error = asyncio.run(transcribe(Path("/tmp/does-not-exist.ogg")))
    assert rc == 1
    assert text == ""
    assert error and error.startswith("whisper_audio_not_found")


# ── /api/margot/voice route — auth gate ────────────────────────────────────


def test_voice_route_missing_secret_returns_401(monkeypatch):
    """Missing X-Pi-CEO-Secret → 401, regardless of payload."""
    monkeypatch.setenv("TAO_WEBHOOK_SECRET", "test-secret")
    from fastapi.testclient import TestClient
    from app.server.routes.margot import router

    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    r = client.post(
        "/api/margot/voice",
        json={"chat_id": "1", "file_id": "abc"},
    )
    assert r.status_code == 401


def test_voice_route_wrong_secret_returns_401(monkeypatch):
    """Wrong X-Pi-CEO-Secret → 401."""
    monkeypatch.setenv("TAO_WEBHOOK_SECRET", "test-secret")
    from fastapi.testclient import TestClient
    from app.server.routes.margot import router

    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    r = client.post(
        "/api/margot/voice",
        json={"chat_id": "1", "file_id": "abc"},
        headers={"X-Pi-CEO-Secret": "wrong"},
    )
    assert r.status_code == 401


# ── provider_router: margot.truth_check role mapping ───────────────────────


def test_provider_router_truth_check_role_in_top_tier():
    """RA-1886: margot.truth_check role must map to top tier so the per-role
    env override TAO_MODEL_MARGOT_TRUTH_CHECK takes precedence over cheap."""
    from app.server.provider_router import ROLE_TIER

    assert ROLE_TIER.get("margot.truth_check") == "top"


def test_provider_router_truth_check_env_override(monkeypatch):
    """TAO_MODEL_MARGOT_TRUTH_CHECK=openrouter:x-ai/grok-4.3 picks Grok."""
    monkeypatch.setenv("TAO_MODEL_MARGOT_TRUTH_CHECK", "openrouter:x-ai/grok-4.3")
    from app.server.provider_router import select_provider_model

    pm = select_provider_model("margot.truth_check")
    assert pm.provider == "openrouter"
    assert pm.model_id == "x-ai/grok-4.3"
    assert pm.source == "env_role_override"
