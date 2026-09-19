"""Blocking golden evals for subscription defaults and paid-transport denials."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
import yaml

from app.server import provider_ollama, provider_router

_GOLDEN = Path(__file__).parent / "golden" / "provider_router_roles.yaml"
_CASES = yaml.safe_load(_GOLDEN.read_text())["cases"]


@pytest.fixture(autouse=True)
def default_routes(monkeypatch):
    """Exercise code defaults independently of developer or obsolete CI pins."""
    for key in list(os.environ):
        if key.startswith(("TAO_MODEL_", "TAO_TOP_", "TAO_MID_", "TAO_CHEAP_")):
            monkeypatch.delenv(key)
    for key in ("OLLAMA_BASE_URL", "MARGOT_OLLAMA_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    def no_probe(**kwargs):
        pytest.fail("Default routing must not probe a local model server")
    monkeypatch.setattr(provider_ollama, "is_reachable", no_probe)


@pytest.mark.parametrize("case", _CASES, ids=lambda c: c["role"])
def test_router_matches_golden(case: dict) -> None:
    pm = provider_router.select_provider_model(case["role"], record_observation=False)
    assert pm.role == case["role"]
    assert pm.tier == case["tier"]
    assert pm.provider == case["provider"]
    assert pm.model_id == case["model_id"]
    if case.get("not_anthropic"):
        assert not provider_router.is_anthropic(pm), "Metered Anthropic API route selected"


def test_unmapped_role_never_escalates_to_top() -> None:
    """Cost guard: an unknown role must never silently route to the top tier."""
    pm = provider_router.select_provider_model("definitely_not_a_registered_role", record_observation=False)
    assert pm.tier != "top", f"unmapped role escalated to top tier: {pm!r}"


@pytest.mark.parametrize("provider", ["anthropic", "openrouter"])
def test_explicit_paid_pins_remain_visible_but_cannot_dispatch(monkeypatch, provider):
    monkeypatch.setenv("TAO_MODEL_MONITOR", f"{provider}:explicit-model")
    pm = provider_router.select_provider_model("monitor", record_observation=False)
    assert (pm.provider, pm.model_id) == (provider, "explicit-model")
    result = asyncio.run(provider_router.run_via_provider_with_evidence("test", role="monitor"))
    assert result.rc != 0 and result.text == ""
    assert "subscription_only" in result.error
    assert result.provenance["model_verified"] is False


def test_margot_free_label_does_not_bypass_subscription_policy():
    rc, text, _, error = asyncio.run(provider_router.run_via_provider("test", role="margot.casual"))
    assert rc != 0 and text == ""
    assert "subscription_only" in error
