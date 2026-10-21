"""The one OpenRouter exception in provider_policy (founder ruling 21/10/2026).

OpenRouter is allowed ONLY for role ``margot.casual`` with a model id that ends
in ``:free``. Every other OpenRouter use stays blocked. Each blocked case below is a near-miss of the one
allowed case, so a widened exception turns at least one of them red.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server import provider_policy as policy  # noqa: E402

FREE_ID = "nvidia/nemotron-3-super-120b-a12b:free"


@pytest.fixture(autouse=True)
def _no_subprocess(monkeypatch):
    """A blocked OpenRouter call must be refused by name, never by a failed
    Claude CLI probe that happens to raise the same error class."""
    import subprocess  # noqa: PLC0415
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=AssertionError("no CLI probe")))
    for key in policy.CLAUDE_ROUTING_ENV + policy.CODEX_ROUTING_ENV:
        monkeypatch.delenv(key, raising=False)


def test_margot_casual_with_a_free_id_is_allowed():
    evidence = policy.require_transport("openrouter", role="margot.casual", model_id=FREE_ID)
    assert evidence["billing_class"] == "free"
    assert evidence["source"] == "openrouter_free_margot_casual"


@pytest.mark.parametrize("model_id", [
    "z-ai/glm-4.7-flash",
    "minimax/minimax-m3.1-flash",
    "anthropic/claude-sonnet-latest",
    "",
    None,
])
def test_margot_casual_with_a_paid_id_is_blocked(model_id):
    with pytest.raises(policy.ProviderPolicyError, match="paid or unverified transport blocked"):
        policy.require_transport("openrouter", role="margot.casual", model_id=model_id)


@pytest.mark.parametrize("role", [
    None, "", "margot.synthesis", "margot.casual.reply", "Margot.casual",
    " margot.casual", "monitor", "evaluator_secondary", "planner",
])
def test_another_role_with_a_free_id_is_blocked(role):
    with pytest.raises(policy.ProviderPolicyError, match="paid or unverified transport blocked"):
        policy.require_transport("openrouter", role=role, model_id=FREE_ID)


@pytest.mark.parametrize("model_id", [
    "nvidia/nemotron-3-super-120b-a12b:free:paid",
    "openai/gpt-4o:free-trial",
    "x:free/y",
    "nvidia/nemotron-3-super-120b-a12b:FREE",
    "nvidia/nemotron-3-super-120b-a12b:free ",
])
def test_free_in_the_middle_but_not_at_the_end_is_blocked(model_id):
    with pytest.raises(policy.ProviderPolicyError, match="paid or unverified transport blocked"):
        policy.require_transport("openrouter", role="margot.casual", model_id=model_id)


@pytest.mark.parametrize("provider", ["anthropic", "anthropic_api", "minimax", "gemini"])
def test_the_exception_is_openrouter_only(provider):
    with pytest.raises(policy.ProviderPolicyError, match="subscription_only"):
        policy.require_transport(provider, role="margot.casual", model_id=FREE_ID)


def test_openrouter_adapter_passes_role_and_model_to_the_policy(monkeypatch):
    """provider_openrouter.call must hand the policy its role and model id, or
    the exception above can never apply and margot.casual fails closed."""
    import httpx  # noqa: PLC0415
    from app.server import provider_openrouter  # noqa: PLC0415

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(httpx, "Client", Mock(side_effect=AssertionError("no network")))
    seen: list = []
    real = policy.require_transport

    def spy(provider, **kw):
        seen.append((provider, kw.get("role"), kw.get("model_id")))
        return real(provider, **kw)

    monkeypatch.setattr(policy, "require_transport", spy)
    free = asyncio.run(provider_openrouter.call(prompt="hi", model_id=FREE_ID, role="margot.casual"))
    # Policy admitted it; with no key the adapter stops before any network call.
    assert free[0] == 1 and free[3] == "openrouter_no_api_key"
    paid = asyncio.run(provider_openrouter.call(prompt="hi", model_id=FREE_ID, role="monitor"))
    assert paid[0] == 1 and "subscription_only" in paid[3]
    assert seen == [("openrouter", "margot.casual", FREE_ID), ("openrouter", "monitor", FREE_ID)]

