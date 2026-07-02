"""Tests for swarm.model_router — pure unit tests with stub providers.

No real HTTP. No real env vars beyond what the test sets. No network."""
from __future__ import annotations

import os
import urllib.error
from typing import Literal

import pytest

from swarm.model_router import (
    LLMResponse,
    ModelClient,
    NoProviderAvailable,
    Tier,
    get_client,
    is_openrouter_allowed_for_role,
    is_openrouter_enforce_enabled,
    openrouter_allowed_roles,
)


# ============================================================
# Stub provider — fully controllable
# ============================================================

class StubProvider:
    def __init__(
        self,
        *,
        name: Literal["anthropic", "openrouter", "ollama"] = "anthropic",
        model: str = "stub-model",
        available: bool = True,
        raises: Exception | None = None,
        text: str = "hello from stub",
    ):
        self.name = name
        self._model = model
        self._available = available
        self._raises = raises
        self._text = text
        self.calls = 0

    def is_available(self) -> bool:
        return self._available

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse:
        self.calls += 1
        if self._raises:
            raise self._raises
        return LLMResponse(
            text=self._text,
            model=self._model,
            tier=Tier.FRONTIER,  # client patches the actual tier
            provider=self.name,
            latency_ms=12,
        )


# ============================================================
# Happy-path tests
# ============================================================

class TestHappyPath:
    def test_first_provider_in_ladder_used_when_available(self):
        primary = StubProvider(name="anthropic", model="m1")
        fallback = StubProvider(name="openrouter", model="m2")
        client = get_client(Tier.FRONTIER, providers=[primary, fallback])
        resp = client.complete(system="s", user="u")
        assert primary.calls == 1
        assert fallback.calls == 0
        assert resp.provider == "anthropic"
        assert resp.model == "m1"
        assert resp.tier == Tier.FRONTIER
        assert resp.fell_back is False

    def test_tier_propagates_through_response(self):
        p = StubProvider()
        client = get_client(Tier.WORKING, providers=[p])
        resp = client.complete(system="s", user="u")
        assert resp.tier == Tier.WORKING

    def test_latency_recorded(self):
        p = StubProvider()
        client = get_client(Tier.REMEDIAL, providers=[p])
        resp = client.complete(system="s", user="u")
        assert resp.latency_ms >= 0


# ============================================================
# Fallback ladder tests
# ============================================================

class TestFallback:
    def test_unavailable_first_provider_falls_to_second(self):
        primary = StubProvider(name="anthropic", available=False)
        fallback = StubProvider(name="openrouter", model="fallback")
        client = get_client(Tier.FRONTIER, providers=[primary, fallback])
        resp = client.complete(system="s", user="u")
        assert primary.calls == 0  # never invoked because unavailable
        assert fallback.calls == 1
        assert resp.provider == "openrouter"
        assert resp.fell_back is True

    def test_http_error_falls_to_next_provider(self):
        primary = StubProvider(
            name="anthropic",
            raises=urllib.error.HTTPError("u", 429, "rate-limited", {}, None),
        )
        fallback = StubProvider(name="openrouter", model="fallback")
        client = get_client(Tier.FRONTIER, providers=[primary, fallback])
        resp = client.complete(system="s", user="u")
        assert primary.calls == 1
        assert fallback.calls == 1
        assert resp.provider == "openrouter"
        assert resp.fell_back is True

    def test_no_provider_available_raises_when_ladder_exhausted(self):
        p1 = StubProvider(name="anthropic", available=False)
        p2 = StubProvider(name="openrouter", available=False)
        p3 = StubProvider(name="ollama", available=False)
        client = get_client(Tier.FRONTIER, providers=[p1, p2, p3])
        with pytest.raises(NoProviderAvailable):
            client.complete(system="s", user="u")

    def test_network_error_falls_through(self):
        primary = StubProvider(
            name="anthropic",
            raises=urllib.error.URLError("network unreachable"),
        )
        fallback = StubProvider(name="openrouter", model="fb")
        client = get_client(Tier.FRONTIER, providers=[primary, fallback])
        resp = client.complete(system="s", user="u")
        assert resp.provider == "openrouter"

    def test_no_provider_available_exception_falls_through(self):
        primary = StubProvider(name="anthropic", raises=NoProviderAvailable("key"))
        fallback = StubProvider(name="openrouter", model="fb")
        client = get_client(Tier.FRONTIER, providers=[primary, fallback])
        resp = client.complete(system="s", user="u")
        assert resp.provider == "openrouter"

    def test_is_available_exception_falls_through(self):
        """CodeRabbit finding #3: a probe that raises must NOT abort the ladder.

        Previously is_available() ran outside the try/except, so any exception
        from the probe (e.g. flaky Ollama socket) aborted the whole call.
        Now wrapped in the same try block.
        """
        class ExplodingProbeProvider:
            name = "ollama"
            def is_available(self):
                raise ConnectionError("ollama socket flaky")
            def complete(self, **kwargs):
                pytest.fail("complete() should not be called when is_available raises")

        primary = ExplodingProbeProvider()
        fallback = StubProvider(name="openrouter", model="fb")
        client = get_client(Tier.FRONTIER, providers=[primary, fallback])
        resp = client.complete(system="s", user="u")
        assert resp.provider == "openrouter"
        assert resp.fell_back is True


# ============================================================
# Tier enum + defaults
# ============================================================

class TestTier:
    def test_all_four_tiers_have_descriptions(self):
        for tier in Tier:
            assert tier.description
            assert isinstance(tier.description, str)

    def test_tier_value_is_lowercase(self):
        for tier in Tier:
            assert tier.value == tier.value.lower()


# ============================================================
# Default-ladder smoke (no real HTTP; check shape only)
# ============================================================

class TestDefaultLadders:
    def test_frontier_default_ladder_has_anthropic_first(self, monkeypatch):
        # Wipe env vars so providers all report unavailable, but we can still
        # inspect the construction of the ladder.
        for k in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
            monkeypatch.delenv(k, raising=False)
        client = get_client(Tier.FRONTIER)
        # All providers will report unavailable; we should NOT make HTTP calls
        # and should raise NoProviderAvailable cleanly.
        with pytest.raises(NoProviderAvailable):
            client.complete(system="s", user="u")

    def test_remedial_default_ladder_starts_with_openrouter(self, monkeypatch):
        # Wipe API key env vars so Anthropic + OpenRouter report unavailable.
        for k in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
            monkeypatch.delenv(k, raising=False)
        # Force OllamaProvider.is_available() to report False regardless of
        # whether the developer's machine happens to be running Ollama on
        # localhost:11434. Without this patch the test stops being a pure
        # unit test on Ollama-equipped machines.
        from swarm.model_router import OllamaProvider
        monkeypatch.setattr(OllamaProvider, "is_available", lambda self: False)
        client = get_client(Tier.REMEDIAL)
        with pytest.raises(NoProviderAvailable):
            client.complete(system="s", user="u")


# ============================================================
# Environment isolation
# ============================================================

class TestEnvIsolation:
    def test_no_keys_means_no_call(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        # Stub providers ignore env vars, but real providers must check
        from swarm.model_router import AnthropicProvider, OpenRouterProvider
        assert AnthropicProvider(model="x").is_available() is False
        assert OpenRouterProvider(model="x").is_available() is False

    def test_env_present_makes_provider_available(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        from swarm.model_router import AnthropicProvider, OpenRouterProvider
        assert AnthropicProvider(model="x").is_available() is True
        assert OpenRouterProvider(model="x").is_available() is True


# ============================================================
# Public API smoke
# ============================================================

def test_get_client_returns_modelclient():
    client = get_client(Tier.FRONTIER, providers=[StubProvider()])
    assert isinstance(client, ModelClient)
    assert client.tier == Tier.FRONTIER


def test_llmresponse_is_frozen():
    p = StubProvider()
    client = get_client(Tier.FRONTIER, providers=[p])
    resp = client.complete(system="s", user="u")
    with pytest.raises((AttributeError, Exception)):
        resp.text = "mutated"  # type: ignore[misc]


# ============================================================
# OpenRouter enforce (RA-6470 phase 1)
# ============================================================

class TestOpenRouterEnforce:
    def test_enforce_defaults_off(self, monkeypatch):
        monkeypatch.delenv("TAO_OPENROUTER_ENFORCE", raising=False)
        assert is_openrouter_enforce_enabled() is False

    def test_default_allowed_roles_include_remedial_sub_agent(self, monkeypatch):
        monkeypatch.delenv("TAO_OPENROUTER_ALLOWED_ROLES", raising=False)
        allowed = openrouter_allowed_roles()
        assert "margot.casual" in allowed
        assert "sub_agent" in allowed
        assert "generator" not in allowed
        assert "evaluator" not in allowed

    def test_generator_blocked_when_enforce_on(self, monkeypatch):
        monkeypatch.setenv("TAO_OPENROUTER_ENFORCE", "1")
        assert is_openrouter_allowed_for_role("generator") is False
        assert is_openrouter_allowed_for_role("evaluator") is False

    def test_remedial_role_allowed_when_enforce_on(self, monkeypatch):
        monkeypatch.setenv("TAO_OPENROUTER_ENFORCE", "1")
        assert is_openrouter_allowed_for_role("margot.casual") is True
        assert is_openrouter_allowed_for_role("sub_agent") is True

    def test_generator_cannot_fallback_to_openrouter_when_enforced(self, monkeypatch):
        monkeypatch.setenv("TAO_OPENROUTER_ENFORCE", "1")
        primary = StubProvider(name="anthropic", available=False)
        fallback = StubProvider(name="openrouter", model="fb")
        client = get_client(
            Tier.FRONTIER,
            role="generator",
            providers=[primary, fallback],
        )
        with pytest.raises(NoProviderAvailable):
            client.complete(system="s", user="u")
        assert primary.calls == 0
        assert fallback.calls == 0

    def test_evaluator_cannot_fallback_to_openrouter_when_enforced(self, monkeypatch):
        monkeypatch.setenv("TAO_OPENROUTER_ENFORCE", "1")
        primary = StubProvider(
            name="anthropic",
            raises=urllib.error.HTTPError("u", 429, "rate-limited", {}, None),
        )
        fallback = StubProvider(name="openrouter", model="fb")
        client = get_client(
            Tier.WORKING,
            role="evaluator",
            providers=[primary, fallback],
        )
        with pytest.raises(NoProviderAvailable):
            client.complete(system="s", user="u")
        assert primary.calls == 1
        assert fallback.calls == 0

    def test_allowed_role_keeps_openrouter_fallback(self, monkeypatch):
        monkeypatch.setenv("TAO_OPENROUTER_ENFORCE", "1")
        primary = StubProvider(name="anthropic", available=False)
        fallback = StubProvider(name="openrouter", model="fb")
        client = get_client(
            Tier.REMEDIAL,
            role="margot.casual",
            providers=[primary, fallback],
        )
        resp = client.complete(system="s", user="u")
        assert resp.provider == "openrouter"
        assert fallback.calls == 1

    def test_enforce_off_preserves_openrouter_for_generator(self, monkeypatch):
        monkeypatch.delenv("TAO_OPENROUTER_ENFORCE", raising=False)
        primary = StubProvider(name="anthropic", available=False)
        fallback = StubProvider(name="openrouter", model="fb")
        client = get_client(
            Tier.FRONTIER,
            role="generator",
            providers=[primary, fallback],
        )
        resp = client.complete(system="s", user="u")
        assert resp.provider == "openrouter"

    def test_custom_allowed_roles_env(self, monkeypatch):
        monkeypatch.setenv("TAO_OPENROUTER_ENFORCE", "1")
        monkeypatch.setenv("TAO_OPENROUTER_ALLOWED_ROLES", "generator,evaluator")
        assert is_openrouter_allowed_for_role("generator") is True
        assert is_openrouter_allowed_for_role("margot.casual") is False

    def test_no_role_skips_enforce_filter(self, monkeypatch):
        """Callers without role= keep legacy ladder behaviour when enforce is on."""
        monkeypatch.setenv("TAO_OPENROUTER_ENFORCE", "1")
        primary = StubProvider(name="anthropic", available=False)
        fallback = StubProvider(name="openrouter", model="fb")
        client = get_client(Tier.FRONTIER, providers=[primary, fallback])
        resp = client.complete(system="s", user="u")
        assert resp.provider == "openrouter"
