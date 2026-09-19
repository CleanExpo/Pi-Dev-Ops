"""Every legacy model transport must obey the shared no-API-credit policy."""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def outbound(monkeypatch):
    import httpx
    import anthropic
    import urllib.request
    calls = MagicMock(side_effect=AssertionError("No outbound model call permitted"))
    monkeypatch.setattr(httpx, "Client", calls)
    monkeypatch.setattr(httpx, "post", calls)
    monkeypatch.setattr(anthropic, "Anthropic", calls)
    monkeypatch.setattr(urllib.request, "urlopen", calls)
    for name in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(name, "synthetic-api-key")
    return calls


def test_research_sonar_cannot_spend(outbound):
    from app.server.research_sonar import sonar_caller
    assert sonar_caller("synthetic query") == []
    outbound.assert_not_called()


def test_whisper_cannot_upload_or_spend(outbound, tmp_path):
    from app.server.provider_whisper import transcribe
    audio = tmp_path / "synthetic.ogg"
    audio.write_bytes(b"synthetic")
    rc, _, _, error = asyncio.run(transcribe(audio))
    assert rc != 0 and "subscription_only" in error
    outbound.assert_not_called()


def test_cached_board_prompt_cannot_spend(outbound, monkeypatch):
    from app.server.agents import board_meeting
    monkeypatch.setattr(board_meeting.config, "ENABLE_PROMPT_CACHING_1H", True)
    assert board_meeting._run_prompt_with_cache("system", "user") == ""
    outbound.assert_not_called()


def test_seo_analysis_cannot_spend(outbound):
    from app.server.agents import pi_seo_monitor
    pi_seo_monitor._run_agent_analysis(SimpleNamespace(), {})
    outbound.assert_not_called()


def test_delegate_cannot_fall_back_to_api(outbound, monkeypatch):
    from fastapi import HTTPException
    from app.server.routes import delegate
    monkeypatch.setattr(delegate, "_check_secret", lambda value: None)
    body = delegate.DelegateRequest(task_type="code_gen", spec="synthetic", chat_id="synthetic")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(delegate.delegate_task(body, "synthetic"))
    assert exc.value.status_code == 503
    assert "subscription_only" in exc.value.detail
    outbound.assert_not_called()


def test_pii_api_factory_cannot_spend(outbound):
    from swarm.pii_classify import _make_classifier_with_anthropic
    assert _make_classifier_with_anthropic("haiku")("synthetic text") == []
    outbound.assert_not_called()


@pytest.mark.parametrize("name", ["_openrouter_summarise", "_gemini_summarise"])
def test_preamble_paid_fallbacks_cannot_spend(outbound, name):
    from swarm.inbox import preamble_trainer
    with pytest.raises(preamble_trainer._SummariseError, match="subscription_only"):
        getattr(preamble_trainer, name)("synthetic prompt")
    outbound.assert_not_called()


def test_independent_sdk_helpers_cannot_bypass_transport_policy(monkeypatch):
    import claude_agent_sdk
    from app.server import pipeline
    from app.server.agents import board_meeting, plan_discovery
    calls = MagicMock(side_effect=AssertionError("SDK must not be instantiated"))
    monkeypatch.setattr(claude_agent_sdk, "ClaudeSDKClient", calls)
    assert asyncio.run(pipeline._run_claude_via_sdk_async("synthetic"))[0] is False
    assert board_meeting._run_prompt_via_sdk("synthetic") == ""
    assert board_meeting._run_research_via_sdk("synthetic") == ""
    assert asyncio.run(plan_discovery._generate_plan_variant("synthetic", "synthetic")) == ""
    assert asyncio.run(plan_discovery._score_plan("synthetic", "synthetic")) == 0.0
    calls.assert_not_called()
