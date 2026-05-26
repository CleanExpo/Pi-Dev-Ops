"""Tiered model router for the swarm.

Three tiers map to four candidate providers with a fallback ladder so the
swarm degrades gracefully when any single provider is rate-limited or down:

    Tier            Primary                    Fallback ladder
    ──────────────────────────────────────────────────────────────────────
    FRONTIER        Anthropic Opus 4.7         → Anthropic Sonnet 4.6
                                                → OpenRouter Sonnet
                                                → raise NoProviderAvailable
    WORKING         Anthropic Sonnet 4.6       → Anthropic Haiku 4.5
                                                → OpenRouter Llama 3.3 70B
                                                → raise NoProviderAvailable
    REMEDIAL        OpenRouter Llama 3.3 70B   → OpenRouter DeepSeek-V3
                                                → Ollama local (if reachable)
                                                → Anthropic Haiku 4.5
                                                → raise NoProviderAvailable
    LOCAL           Ollama local               → OpenRouter Llama 3.3 70B
                                                → raise NoProviderAvailable

Env vars (read on demand, NOT at import time, so callers can rotate keys):
    ANTHROPIC_API_KEY     — required for ANY Anthropic tier
    OPENROUTER_API_KEY    — required for any OpenRouter fallback
    OLLAMA_BASE_URL       — defaults to http://localhost:11434
    MODEL_TIER_OVERRIDE   — optional; force a specific tier (e.g. for tests)

Public surface (the only API callers should touch):
    Tier                     — enum, the four tiers above
    LLMResponse              — frozen dataclass (text, model, tier, provider, latency_ms)
    NoProviderAvailable     — raised when every fallback exhausts
    get_client(tier)         — returns a ModelClient honouring the ladder
    ModelClient.complete()   — one synchronous text completion

This module is import-side-effect-free. Tests stub providers via the
ModelProvider Protocol (no real HTTP).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import Literal, Protocol, runtime_checkable


# ============================================================
# Public surface
# ============================================================

class Tier(str, Enum):
    FRONTIER = "frontier"   # judgment, irreversible, customer-facing generation
    WORKING = "working"     # state machine, classification, planning
    REMEDIAL = "remedial"   # bulk, always-on, drift watching
    LOCAL = "local"         # privacy-sensitive or offline-required

    @property
    def description(self) -> str:
        return {
            Tier.FRONTIER: "frontier judgment (Opus/Sonnet)",
            Tier.WORKING: "working tier (Sonnet/Haiku)",
            Tier.REMEDIAL: "remedial / always-on (OpenRouter)",
            Tier.LOCAL: "local (Ollama)",
        }[self]


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    tier: Tier
    provider: Literal["anthropic", "openrouter", "ollama"]
    latency_ms: int
    fell_back: bool = False


class NoProviderAvailable(RuntimeError):
    """Every fallback in the ladder for this tier was exhausted."""


# ============================================================
# Provider Protocol
# ============================================================

@runtime_checkable
class ModelProvider(Protocol):
    name: Literal["anthropic", "openrouter", "ollama"]

    def is_available(self) -> bool: ...
    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse: ...


# ============================================================
# Anthropic provider
# ============================================================

class AnthropicProvider:
    name: Literal["anthropic"] = "anthropic"

    def __init__(self, *, model: str, api_key_env: str = "ANTHROPIC_API_KEY"):
        self._model = model
        self._api_key_env = api_key_env

    def is_available(self) -> bool:
        return bool(os.environ.get(self._api_key_env))

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse:
        api_key = os.environ.get(self._api_key_env)
        if not api_key:
            raise NoProviderAvailable(f"{self._api_key_env} not set")
        body = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        dt_ms = int((time.monotonic() - t0) * 1000)
        # Anthropic response: content is a list of blocks
        text = "".join(
            block.get("text", "")
            for block in raw.get("content", [])
            if block.get("type") == "text"
        )
        return LLMResponse(
            text=text,
            model=self._model,
            tier=Tier.FRONTIER,  # caller patches tier on return; this is the raw provider tier
            provider="anthropic",
            latency_ms=dt_ms,
        )


# ============================================================
# OpenRouter provider
# ============================================================

class OpenRouterProvider:
    name: Literal["openrouter"] = "openrouter"

    def __init__(self, *, model: str, api_key_env: str = "OPENROUTER_API_KEY"):
        self._model = model
        self._api_key_env = api_key_env

    def is_available(self) -> bool:
        return bool(os.environ.get(self._api_key_env))

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse:
        api_key = os.environ.get(self._api_key_env)
        if not api_key:
            raise NoProviderAvailable(f"{self._api_key_env} not set")
        body = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/CleanExpo/Pi-Dev-Ops",
                "X-Title": "Pi-CEO swarm",
            },
            method="POST",
        )
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        dt_ms = int((time.monotonic() - t0) * 1000)
        # OpenAI-compatible: choices[0].message.content
        text = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
        return LLMResponse(
            text=text,
            model=self._model,
            tier=Tier.REMEDIAL,
            provider="openrouter",
            latency_ms=dt_ms,
        )


# ============================================================
# Ollama provider (local)
# ============================================================

class OllamaProvider:
    name: Literal["ollama"] = "ollama"

    def __init__(self, *, model: str, base_url_env: str = "OLLAMA_BASE_URL"):
        self._model = model
        self._base_url_env = base_url_env

    def _base_url(self) -> str:
        return os.environ.get(self._base_url_env, "http://localhost:11434")

    def is_available(self) -> bool:
        try:
            req = urllib.request.Request(f"{self._base_url()}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2):
                return True
        except (urllib.error.URLError, OSError, ConnectionError):
            return False

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse:
        body = {
            "model": self._model,
            "system": system,
            "prompt": user,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }
        req = urllib.request.Request(
            f"{self._base_url()}/api/generate",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ConnectionError) as exc:
            raise NoProviderAvailable(f"ollama unreachable: {exc}") from exc
        dt_ms = int((time.monotonic() - t0) * 1000)
        return LLMResponse(
            text=raw.get("response", ""),
            model=self._model,
            tier=Tier.LOCAL,
            provider="ollama",
            latency_ms=dt_ms,
        )


# ============================================================
# Routing — the fallback ladder
# ============================================================

# Default model assignments per tier. Overridable via env or by passing
# explicit provider lists into `get_client`.
_DEFAULT_FRONTIER_LADDER = (
    ("anthropic", "claude-opus-4-7"),
    ("anthropic", "claude-sonnet-4-6"),
    ("openrouter", "anthropic/claude-sonnet-4.5"),
)
_DEFAULT_WORKING_LADDER = (
    ("anthropic", "claude-sonnet-4-6"),
    ("anthropic", "claude-haiku-4-5-20251001"),
    ("openrouter", "meta-llama/llama-3.3-70b-instruct"),
)
_DEFAULT_REMEDIAL_LADDER = (
    ("openrouter", "meta-llama/llama-3.3-70b-instruct"),
    ("openrouter", "deepseek/deepseek-chat"),
    ("ollama", "llama3.3:70b"),
    ("anthropic", "claude-haiku-4-5-20251001"),
)
_DEFAULT_LOCAL_LADDER = (
    ("ollama", "llama3.3:70b"),
    ("openrouter", "meta-llama/llama-3.3-70b-instruct"),
)


def _build_provider(kind: str, model: str) -> ModelProvider:
    if kind == "anthropic":
        return AnthropicProvider(model=model)
    if kind == "openrouter":
        return OpenRouterProvider(model=model)
    if kind == "ollama":
        return OllamaProvider(model=model)
    raise ValueError(f"unknown provider kind: {kind}")


class ModelClient:
    """The single object callers use. Wraps the ladder and the fallback logic."""

    def __init__(self, tier: Tier, *, providers: list[ModelProvider] | None = None):
        self._tier = tier
        if providers is not None:
            self._ladder = providers
        else:
            ladder_def = {
                Tier.FRONTIER: _DEFAULT_FRONTIER_LADDER,
                Tier.WORKING: _DEFAULT_WORKING_LADDER,
                Tier.REMEDIAL: _DEFAULT_REMEDIAL_LADDER,
                Tier.LOCAL: _DEFAULT_LOCAL_LADDER,
            }[tier]
            self._ladder = [_build_provider(k, m) for k, m in ladder_def]

    @property
    def tier(self) -> Tier:
        return self._tier

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse:
        last_exc: Exception | None = None
        fell_back = False
        for i, provider in enumerate(self._ladder):
            if not provider.is_available():
                last_exc = NoProviderAvailable(
                    f"{provider.name} not available (env / network)"
                )
                fell_back = True
                continue
            try:
                resp = provider.complete(
                    system=system, user=user,
                    max_tokens=max_tokens, temperature=temperature,
                )
                return LLMResponse(
                    text=resp.text,
                    model=resp.model,
                    tier=self._tier,
                    provider=resp.provider,
                    latency_ms=resp.latency_ms,
                    fell_back=fell_back or (i > 0),
                )
            except NoProviderAvailable as exc:
                last_exc = exc
                fell_back = True
                continue
            except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
                last_exc = exc
                fell_back = True
                continue
        raise NoProviderAvailable(
            f"all providers in {self._tier.value} ladder exhausted; last={last_exc}"
        )


def get_client(tier: Tier, *, providers: list[ModelProvider] | None = None) -> ModelClient:
    """Get a tiered client. `providers` override is used by tests."""
    return ModelClient(tier=tier, providers=providers)
