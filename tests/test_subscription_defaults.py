"""Supported defaults and per-invocation local identity without live traffic."""
import asyncio
import json
import os
import subprocess
from unittest.mock import Mock

import httpx
import pytest

from app.server import provider_policy, provider_router, provider_ollama


@pytest.fixture(autouse=True)
def clean_routes(monkeypatch):
    for key in list(os.environ):
        if key.startswith(("TAO_MODEL_", "TAO_CHEAP_", "TAO_TOP_", "TAO_MID_")):
            monkeypatch.delenv(key)
    for key in provider_policy.CLAUDE_ROUTING_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setattr(provider_router, "_record_cost_safe", lambda **kwargs: None)


@pytest.mark.parametrize("role", ["planner", "generator", "spec_pipeline"])
def test_default_roles_use_supported_subscription_transport(role):
    assert provider_router.select_provider_model(role).provider == "claude_print"


@pytest.mark.parametrize("role", ["monitor", "boardroom_panellist_secondary", "evaluator_secondary"])
def test_default_roles_never_probe_or_spill_to_paid(monkeypatch, role):
    probe = Mock(side_effect=AssertionError("selection must not probe"))
    monkeypatch.setattr(provider_ollama, "is_reachable", probe)
    assert provider_router.select_provider_model(role).provider == "claude_print"
    probe.assert_not_called()


@pytest.mark.parametrize("provider", ["anthropic", "openrouter"])
async def test_explicit_paid_overrides_remain_blocked(monkeypatch, provider):
    monkeypatch.setenv("TAO_MODEL_SPEC_PIPELINE", f"{provider}:explicit-model")
    invocation = Mock(side_effect=AssertionError("must not start a model"))
    monkeypatch.setattr(subprocess, "run", invocation)
    outcome = await provider_router.run_via_provider_with_evidence("task", role="spec_pipeline")
    assert outcome.rc != 0 and "subscription_only" in outcome.error
    invocation.assert_not_called()


@pytest.mark.parametrize("reported", ["served-model", " served-model ", None, "", 42])
async def test_ollama_identity_is_response_metadata(monkeypatch, reported):
    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, **kwargs):
            return httpx.Response(200, json={"model": reported,
                "choices": [{"message": {"content": "response"}}]})

    monkeypatch.setattr(httpx, "Client", Client)
    outcome = await provider_ollama.call_with_evidence(prompt="task", model_id="requested-model")
    expected = reported.strip() if isinstance(reported, str) and reported.strip() else None
    assert outcome.provenance["actual_model"] == expected
    assert outcome.provenance["model_verified"] is bool(expected)
    assert outcome.provenance["requested_model"] == "requested-model"


@pytest.mark.parametrize("review", ["boardroom", "evaluator"])
async def test_configured_reviews_use_real_adapters_and_observed_independent_models(review_transports, review):
    from app.server.spec_pipeline.boardroom import boardroom_query

    if review == "evaluator":
        primary, secondary = await asyncio.gather(*(
            provider_router.run_via_provider_with_evidence("Review bounded change", role=role)
            for role in ("evaluator", "evaluator_secondary")
        ))
        assert primary.rc == secondary.rc == 0
        assert provider_policy.independent_identity(primary.provenance, secondary.provenance)
        assert secondary.provenance["actual_model"] == "gemma-served"
        return
    result = await boardroom_query(prompt="Approve the bounded change?")
    assert result.decision == "APPROVE_BUILD"
    assert [seat.model_id for seat in result.panel] == ["claude-served", "gemma-served"]
    assert [seat.provenance["provider"] for seat in result.panel] == ["anthropic", "ollama"]
    assert result.synthesised_by == "claude-served"


async def test_concurrent_ollama_results_keep_their_own_identity(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, **kwargs):
            requested = kwargs["json"]["model"]
            return httpx.Response(200, json={"model": f"served-{requested}",
                "choices": [{"message": {"content": "response"}}]})

    monkeypatch.setattr(httpx, "Client", Client)
    results = await asyncio.gather(*(
        provider_ollama.call_with_evidence(prompt="task", model_id=model)
        for model in ("one", "two")
    ))
    assert [result.provenance["actual_model"] for result in results] == ["served-one", "served-two"]
    assert results[0].provenance is not results[1].provenance


async def test_missing_explicit_local_does_not_try_any_paid_transport(monkeypatch):
    from app.server import provider_openrouter
    from unittest.mock import AsyncMock

    monkeypatch.setenv("TAO_MODEL_MONITOR", "ollama:requested-local")
    monkeypatch.setattr(httpx, "Client", Mock(side_effect=ConnectionError("local unavailable")))
    paid = AsyncMock(side_effect=AssertionError("must not spend"))
    monkeypatch.setattr(provider_openrouter, "call", paid)
    outcome = await provider_router.run_via_provider_with_evidence("task", role="monitor")
    assert outcome.rc != 0
    assert "local unavailable" in outcome.error
    paid.assert_not_called()


@pytest.fixture
def review_transports(monkeypatch):
    def run(command, **kwargs):
        if command[1:3] == ["auth", "status"]:
            payload = {"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max"}
        else:
            prompt = command[command.index("--print") + 1]
            text = ('{"decision":"APPROVE_BUILD","confidence":0.9}'
                    if "Synthesise" in prompt else "Approve small reversible scope.")
            payload = {"type": "result", "is_error": False, "result": text,
                       "modelUsage": {"claude-served": {}}}
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, **kwargs):
            assert url.startswith("http://localhost:")
            return httpx.Response(200, json={"model": "gemma-served",
                "choices": [{"message": {"content": "Approve small reversible scope."}}]})

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(httpx, "Client", Client)
    monkeypatch.setenv("TAO_MODEL_EVALUATOR_SECONDARY", "ollama:requested-local")
    monkeypatch.setenv("TAO_MODEL_BOARDROOM_PANELLIST_SECONDARY", "ollama:requested-local")
