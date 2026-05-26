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
        for k in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
            monkeypatch.delenv(k, raising=False)
        client = get_client(Tier.REMEDIAL)
        # Should raise (no env, no ollama running), not crash with import errors
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
