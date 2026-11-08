"""Spec calls use subscription policy and observed identity without model traffic."""
import threading
from unittest.mock import AsyncMock

import pytest

from app.server import provider_openrouter, provider_router
from app.server.provider_execution import STOPPED_RC
from app.server.spec_pipeline import llm


@pytest.fixture
def execution(monkeypatch):
    result = provider_router.ProviderExecution(
        0, "completed", None, None,
        {"provider": "anthropic", "source": "test_transport", "auth_verified": True, "model_verified": True,
         "actual_model": "claude-test", "requested_model": "claude-test"},
    )
    route = AsyncMock(return_value=result)
    monkeypatch.setattr(provider_router, "select_provider_model", lambda role: provider_router.ProviderModel(
        "claude_print", "claude-test", "mid", role, "test",
    ))
    monkeypatch.setattr(provider_router, "run_via_provider_with_evidence", route)
    monkeypatch.setattr(provider_openrouter, "call", AsyncMock(side_effect=AssertionError("paid API dispatched")))
    return result, route


@pytest.mark.asyncio
async def test_spec_uses_subscription_router_and_preserves_unknown_cost(execution):
    _, route = execution
    assert await llm.complete(prompt="task", system="system", role="spm_runner") == ("completed", None)
    assert route.call_args.kwargs["role"] == "spm_runner"
    assert "system\n\ntask" in route.call_args.kwargs["prompt"]


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["auth_verified", "model_verified", "actual_model", "provider", "source"])
async def test_spec_refuses_unverified_identity(execution, field):
    result, _ = execution
    result.provenance[field] = None
    with pytest.raises(RuntimeError, match="unverified"):
        await llm.complete(prompt="task")


@pytest.mark.asyncio
async def test_spec_propagates_blocked_dispatch_without_fallback(execution):
    result, route = execution
    result.rc, result.error = 1, "subscription_only: blocked"
    with pytest.raises(RuntimeError, match="subscription_only"):
        await llm.complete(prompt="task")
    assert route.await_count == 1


@pytest.mark.asyncio
async def test_explicit_model_is_never_labelled_as_a_different_served_model(execution):
    with pytest.raises(RuntimeError, match="model mismatch"):
        await llm.complete(prompt="task", model_id="deepseek/different-model")


@pytest.mark.asyncio
async def test_explicit_anthropic_slug_matches_observed_claude_model(execution):
    assert await llm.complete(prompt="task", model_id="anthropic/claude-test") == ("completed", None)


@pytest.mark.asyncio
async def test_explicit_identity_requires_matching_execution_not_just_configuration(execution):
    outcome, route = execution
    outcome.provenance["actual_model"] = "different-served-model"
    with pytest.raises(RuntimeError, match="model mismatch"):
        await llm.complete(prompt="task", model_id="claude-test")
    assert route.await_count == 1


@pytest.mark.asyncio
async def test_spec_supported_route_reaches_checked_cli_without_api_fallback(monkeypatch):
    import json
    import subprocess
    from unittest.mock import Mock
    from app.server import provider_policy

    for key in provider_policy.CLAUDE_ROUTING_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TAO_MODEL_SPM_RUNNER", "claude_print:claude-test")
    invocation = Mock(side_effect=[
        subprocess.CompletedProcess([], 0, json.dumps({
            "loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max",
        }), ""),
        subprocess.CompletedProcess([], 0, json.dumps({
            "type": "result", "is_error": False, "result": "specification",
            "modelUsage": {"claude-test": {}},
        }), ""),
    ])
    monkeypatch.setattr(subprocess, "run", invocation)
    paid = AsyncMock(side_effect=AssertionError("paid fallback"))
    monkeypatch.setattr(provider_openrouter, "call", paid)
    assert await llm.complete(prompt="task", role="spm_runner") == ("specification", None)
    assert invocation.call_args_list[0].args[0][1:] == ["auth", "status"]
    assert invocation.call_args_list[1].args[0][1] == "--print"
    paid.assert_not_called()


@pytest.mark.asyncio
async def test_stop_reaches_the_model_runner(execution):
    _, route = execution
    stop = threading.Event()
    await llm.complete(prompt="task", stop=stop)
    assert route.call_args.kwargs["stop"] is stop


@pytest.mark.asyncio
async def test_no_stop_keeps_the_old_call_shape(execution):
    _, route = execution
    await llm.complete(prompt="task")
    assert "stop" not in route.call_args.kwargs


@pytest.mark.asyncio
async def test_a_stopped_call_is_reported_as_stopped_not_failed(execution):
    result, _ = execution
    stop = threading.Event()
    stop.set()
    result.rc, result.text, result.error = STOPPED_RC, "", "claude_print_stopped"
    with pytest.raises(llm.Stopped):
        await llm.complete(prompt="task", stop=stop)
    result.rc, result.error = 1, "claude_print_failed: exit 1"
    with pytest.raises(RuntimeError) as err:
        await llm.complete(prompt="task", stop=stop)
    assert not isinstance(err.value, llm.Stopped)
