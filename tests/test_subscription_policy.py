"""No model traffic: enforce billing and execution identity at dispatch boundaries."""
import asyncio
import json
import subprocess
from unittest.mock import Mock

import pytest

from app.server import provider_policy as policy
from app.server import provider_router as router
from swarm import fleet_value_optimizer as fleet
from swarm import model_router


@pytest.fixture(autouse=True)
def clean_transport_env(monkeypatch):
    for key in policy.CLAUDE_ROUTING_ENV + policy.CODEX_ROUTING_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)


@pytest.mark.parametrize("provider", ["anthropic_api", "openrouter", "openai", "minimax", "unknown"])
def test_paid_and_unknown_transports_blocked(provider):
    with pytest.raises(policy.ProviderPolicyError, match="subscription_only"):
        policy.require_transport(provider)


@pytest.mark.parametrize("auth", [{}, {"loggedIn": False}, {"loggedIn": True, "authMethod": "api_key"}])
def test_unverified_expired_or_api_login_blocks_model(monkeypatch, auth):
    call = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps(auth), ""))
    monkeypatch.setattr(subprocess, "run", call)
    with pytest.raises(policy.ProviderPolicyError):
        policy.require_transport("claude_print")
    assert call.call_count == 1
    assert "--print" not in call.call_args.args[0]


def test_ambient_api_key_blocks_before_any_subprocess(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-placeholder")
    call = Mock()
    monkeypatch.setattr(subprocess, "run", call)
    with pytest.raises(policy.ProviderPolicyError, match="ambient"):
        policy.require_transport("claude_print")
    call.assert_not_called()


def test_api_dispatch_denied_before_transport(monkeypatch):
    monkeypatch.setenv("TAO_MODEL_EVALUATOR_SECONDARY", "openrouter:review-model")
    call = Mock(side_effect=AssertionError("must not spend"))
    from app.server import provider_openrouter
    monkeypatch.setattr(provider_openrouter, "call", call)
    result = asyncio.run(router.run_via_provider_with_evidence("review", role="evaluator_secondary"))
    assert result.rc != 0
    assert "subscription_only" in result.error
    call.assert_not_called()


def test_cli_passes_model_and_records_returned_identity_without_zero_cost(monkeypatch):
    monkeypatch.setenv("TAO_MODEL_EVALUATOR_SECONDARY", "claude_print:requested-model")
    auth = {"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max"}
    result = {"type": "result", "is_error": False, "result": "reviewed", "modelUsage": {"actual-model": {}}}
    call = Mock(side_effect=[subprocess.CompletedProcess([], 0, json.dumps(auth), ""),
                            subprocess.CompletedProcess([], 0, json.dumps(result), "")])
    monkeypatch.setattr(subprocess, "run", call)
    outcome = asyncio.run(router.run_via_provider_with_evidence("review", role="evaluator_secondary"))
    assert outcome.rc == 0
    assert outcome.cost_usd is None
    assert outcome.provenance["actual_model"] == "actual-model"
    assert outcome.provenance["requested_model"] == "requested-model"
    args = call.call_args.args[0]
    assert args[args.index("--model") + 1] == "requested-model"
    assert args[args.index("--output-format") + 1] == "json"
    assert all(invocation.kwargs["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)
               for invocation in call.call_args_list)


def test_missing_reported_model_cannot_pass_independent_review():
    assert not policy.independent_identity({"provider": "claude_print", "actual_model": "a"},
                                           {"provider": "ollama", "actual_model": None})


def test_local_fallback_never_uses_paid_provider():
    local = Mock(name="local")
    local.name = "ollama"
    local.is_available.return_value = False
    paid = Mock(name="paid")
    paid.name = "openrouter"
    client = model_router.ModelClient(model_router.Tier.LOCAL, providers=[local, paid])
    with pytest.raises(model_router.NoProviderAvailable):
        client.complete(system="s", user="u")
    paid.complete.assert_not_called()
    paid.is_available.assert_not_called()


def test_remote_ollama_is_not_assumed_local(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://unknown.example/v1")
    with pytest.raises(policy.ProviderPolicyError):
        policy.require_transport("ollama")


def test_provider_name_does_not_invent_subscription_seat():
    assert fleet._provider_to_plan("anthropic") is None
    assert fleet._provider_to_plan("claude_print") is None
    assert fleet._provider_to_plan("openai") is None


def test_fleet_report_does_not_present_assumed_quotas_as_verified(monkeypatch):
    monkeypatch.setattr(fleet, "monthly_usage_counts", lambda **kw: {})
    report = fleet.monthly_utilization_report()
    assert all(row["utilization_pct"] is None for row in report["plans"])
    assert all(row["quota_source"] == "planning_assumption" for row in report["plans"])


@pytest.mark.parametrize("name", ["openrouter", "nex_n2"])
def test_direct_adapters_do_not_bypass_policy(monkeypatch, name):
    import httpx
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-placeholder")
    network = Mock(side_effect=AssertionError("must not spend"))
    monkeypatch.setattr(httpx, "Client", network)
    from app.server import provider_openrouter, provider_nex_n2
    kwargs = {"prompt": "review"}
    adapter = provider_nex_n2 if name == "nex_n2" else provider_openrouter
    if name == "openrouter":
        kwargs["model_id"] = "some-model"
    result = asyncio.run(adapter.call(**kwargs))
    assert result[0] != 0 and "subscription_only" in result[3]
    network.assert_not_called()


@pytest.mark.parametrize("provider_class", [model_router.AnthropicProvider, model_router.OpenRouterProvider])
def test_direct_swarm_adapter_cannot_bypass_policy(monkeypatch, provider_class):
    import urllib.request
    network = Mock(side_effect=AssertionError("must not spend"))
    monkeypatch.setattr(urllib.request, "urlopen", network)
    with pytest.raises(policy.ProviderPolicyError):
        provider_class(model="some-model").complete(system="s", user="u")
    network.assert_not_called()


def test_different_models_from_same_vendor_do_not_count_as_cross_vendor_review():
    evidence = {"auth_verified": True, "model_verified": True, "source": "claude_auth_status"}
    assert not policy.independent_identity(
        dict(evidence, provider="claude_print", actual_model="opus"),
        dict(evidence, provider="anthropic", actual_model="sonnet"),
    )


def test_codex_report_without_observed_model_cannot_be_release_evidence(monkeypatch):
    monkeypatch.setenv("TAO_MODEL_EVALUATOR_SECONDARY", "codex:gpt-example")
    events = '\n'.join(json.dumps(item) for item in [
        {"type": "thread.started", "thread_id": "t"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "review"}},
        {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}},
    ])
    call = Mock(side_effect=[subprocess.CompletedProcess([], 0, "", "Logged in using ChatGPT\n"),
                            subprocess.CompletedProcess([], 0, events, "")])
    monkeypatch.setattr(subprocess, "run", call)
    result = asyncio.run(router.run_via_provider_with_evidence("review", role="evaluator_secondary"))
    assert result.rc == 0
    assert result.provenance["actual_model"] is None
    assert result.provenance["model_verified"] is False
    assert result.cost_usd is None
    args = call.call_args.args[0]
    assert "--ignore-user-config" in args
    assert args[args.index("--sandbox") + 1] == "read-only"
    assert args[args.index("--model") + 1] == "gpt-example"
    assert all(invocation.kwargs["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)
               for invocation in call.call_args_list)


def test_codex_api_auth_is_not_subscription(monkeypatch):
    monkeypatch.setattr(subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, "", "Logged in using an API key")))
    with pytest.raises(policy.ProviderPolicyError):
        policy.require_transport("codex")


@pytest.mark.parametrize("key", policy.CODEX_ROUTING_ENV)
def test_codex_ambient_api_configuration_blocks_before_login(monkeypatch, key):
    monkeypatch.setenv(key, "test-placeholder")
    call = Mock()
    monkeypatch.setattr(subprocess, "run", call)
    with pytest.raises(policy.ProviderPolicyError, match="ambient"):
        policy.require_transport("codex")
    call.assert_not_called()


def test_cli_missing_or_multiple_reported_models_stays_unverified(monkeypatch):
    monkeypatch.setenv("TAO_MODEL_EVALUATOR_SECONDARY", "claude_print:requested")
    auth = {"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max"}
    result = {"type": "result", "is_error": False, "result": "ok", "modelUsage": {"one": {}, "two": {}}}
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=[
        subprocess.CompletedProcess([], 0, json.dumps(auth), ""),
        subprocess.CompletedProcess([], 0, json.dumps(result), ""),
    ]))
    outcome = asyncio.run(router.run_via_provider_with_evidence("review", role="evaluator_secondary"))
    assert outcome.rc == 0
    assert outcome.provenance["actual_model"] is None
    assert outcome.provenance["model_verified"] is False


@pytest.mark.parametrize("reported, observed", [
    ("served-model", "served-model"),
    (" served-model ", "served-model"),
    (None, ""),
    ("", ""),
    ("   ", ""),
    (42, ""),
])
@pytest.mark.parametrize("via_client", [False, True])
def test_swarm_local_model_identity_is_observed_not_requested(monkeypatch, reported, observed, via_client):
    import io
    import urllib.request
    raw = {"response": "ok"}
    if reported is not None:
        raw["model"] = reported
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(raw).encode()))
    provider = model_router.OllamaProvider(model="requested-model")
    client = model_router.ModelClient(model_router.Tier.LOCAL, providers=[provider]) if via_client else provider
    result = client.complete(system="s", user="u")
    assert result.model == observed
    assert result.requested_model == "requested-model"


@pytest.mark.parametrize("env_key", ["OLLAMA_BASE_URL", "CUSTOM_OLLAMA_URL"])
@pytest.mark.parametrize("operation", ["complete", "is_available"])
def test_direct_swarm_local_adapter_blocks_remote_endpoint(monkeypatch, env_key, operation):
    import urllib.request

    monkeypatch.setenv(env_key, "https://unverified.example")
    network = Mock(side_effect=AssertionError("remote transport must not be contacted"))
    monkeypatch.setattr(urllib.request, "urlopen", network)
    provider = model_router.OllamaProvider(model="requested", base_url_env=env_key)
    with pytest.raises(policy.ProviderPolicyError):
        if operation == "complete":
            provider.complete(system="s", user="u")
        else:
            provider.is_available()
    network.assert_not_called()


def test_direct_server_local_adapter_blocks_remote_endpoint(monkeypatch):
    import httpx
    from app.server import provider_ollama

    monkeypatch.setenv("OLLAMA_BASE_URL", "https://unverified.example")
    network = Mock(side_effect=AssertionError("remote transport must not be contacted"))
    monkeypatch.setattr(httpx, "Client", network)
    result = asyncio.run(provider_ollama.call(prompt="review", model_id="requested"))
    assert result[0] != 0 and "subscription_only" in result[3]
    assert provider_ollama.is_reachable(force_refresh=True) is False
    network.assert_not_called()


@pytest.mark.parametrize("task", ["classification", "summary"])
def test_background_subscription_helpers_create_no_console(monkeypatch, task):
    from swarm import pii_classify
    from swarm.inbox import preamble_trainer

    module = pii_classify if task == "classification" else preamble_trainer
    monkeypatch.setattr(module, "require_transport", lambda _: {})
    result = "[]" if task == "classification" else "summary"
    call = Mock(return_value=subprocess.CompletedProcess([], 0, result, ""))
    monkeypatch.setattr(subprocess, "run", call)
    if task == "classification":
        module._classify_via_claude_print("some content")
    else:
        module._claude_print_summarise("some content")
    assert call.call_args.kwargs["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)
