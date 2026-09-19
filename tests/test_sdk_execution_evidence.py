"""SDK execution evidence is reported, never inferred from request options."""
import importlib
import json
import sys

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

from app.server import config, provider_policy, session_sdk


@pytest.fixture
def evidence(monkeypatch):
    rows, costs = [], []
    monkeypatch.setattr(provider_policy, "require_transport", lambda *a, **kw: {})
    monkeypatch.setattr(session_sdk, "_execution_options", lambda _: {"cli_path": sys.executable, "env": {}})
    monkeypatch.setattr(session_sdk, "_write_sdk_metric", lambda **kw: rows.append(kw))
    # Earlier budget tests evict sys.modules but leave swarm.budget_tracker's
    # package attribute stale. Patch the module a fresh SDK import will use.
    tracker = importlib.import_module("swarm.budget_tracker")
    monkeypatch.setattr(tracker, "record_cost", lambda **kw: costs.append(kw))
    monkeypatch.setattr(config, "FABLE_ALLOWED_ROLES", set())
    return rows, costs


def result(cost=None, **kwargs):
    return ResultMessage(subtype="success", duration_ms=10, duration_api_ms=5,
                         is_error=False, num_turns=1, session_id="test",
                         total_cost_usd=cost, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("cost", [0.0, 0.25, None, -1, float("nan"), float("inf"), True, "0.25"])
async def test_reported_cost_and_observed_identity(monkeypatch, evidence, cost):
    async def query(**kwargs):
        yield AssistantMessage(content=[TextBlock(text="done")], model="claude-served-snapshot")
        yield result(cost, usage={"input_tokens": 9, "output_tokens": 4})
    monkeypatch.setattr("claude_agent_sdk.query", query)
    rc, text, actual_cost = await session_sdk._run_claude_via_sdk("test", "sonnet", "/tmp")
    rows, costs = evidence
    valid = type(cost) in (int, float) and 0 <= cost < float("inf")
    assert (rc, text) == (0, "done")
    assert actual_cost == cost if valid else actual_cost is None
    assert rows[-1]["actual_model"] == "claude-served-snapshot"
    assert rows[-1]["requested_model"] == "sonnet"
    assert rows[-1]["cost_source"] == ("sdk_reported_usage" if valid else "unknown")
    assert rows[-1]["cost_verified"] is False
    if valid:
        assert costs[-1]["cost_usd"] == cost
        assert costs[-1]["model"] == "claude-served-snapshot"
        assert costs[-1]["tokens_in"] == 9
    else:
        assert costs == []


@pytest.mark.asyncio
async def test_missing_model_never_becomes_requested_model(monkeypatch, evidence):
    async def query(**kwargs):
        yield result(0.2)
    monkeypatch.setattr("claude_agent_sdk.query", query)
    await session_sdk._run_claude_via_sdk("test", "sonnet", "/tmp")
    rows, costs = evidence
    assert rows[-1]["actual_model"] is None
    assert rows[-1]["model_verified"] is False
    assert costs[-1]["model"] == "unknown"


@pytest.mark.asyncio
async def test_error_result_preserves_reported_usage_without_success(monkeypatch, evidence):
    async def query(**kwargs):
        message = result(0.17, model_usage={"observed-model": {"outputTokens": 2}})
        message.is_error = True
        yield message
    monkeypatch.setattr("claude_agent_sdk.query", query)
    rc, _, cost = await session_sdk._run_claude_via_sdk("test", "sonnet", "/tmp")
    rows, costs = evidence
    assert rc != 0
    assert cost == 0.17
    assert rows[-1]["actual_model"] == "observed-model"
    assert rows[-1]["success"] is False
    assert costs[-1]["cost_usd"] == 0.17


@pytest.mark.asyncio
async def test_multiple_observed_models_do_not_claim_single_identity(monkeypatch, evidence):
    async def query(**kwargs):
        yield AssistantMessage(content=[TextBlock(text="done")], model="observed-one")
        yield result(0.2, model_usage={"observed-one": {}, "observed-two": {}})
    monkeypatch.setattr("claude_agent_sdk.query", query)
    await session_sdk._run_claude_via_sdk("test", "sonnet", "/tmp")
    rows, costs = evidence
    assert rows[-1]["actual_model"] is None
    assert rows[-1]["observed_models"] == ["observed-one", "observed-two"]
    assert rows[-1]["model_verified"] is False
    assert costs[-1]["model"] == "unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize("first_cost, expected", [(0.1, 0.3), (None, None)])
async def test_fallback_preserves_each_attempt_identity_and_total_cost(monkeypatch, evidence, first_cost, expected):
    monkeypatch.setattr(config, "FABLE_ALLOWED_ROLES", {"adversary"})
    async def query(**kwargs):
        fable = kwargs["options"].model == "claude-fable-5"
        yield AssistantMessage(content=[TextBlock(text="refused" if fable else "approved")],
                               model="fable-observed" if fable else "opus-observed")
        yield result(first_cost if fable else 0.2, stop_reason="refusal" if fable else "end_turn")
    monkeypatch.setattr("claude_agent_sdk.query", query)
    rc, text, cost = await session_sdk._run_claude_via_sdk("test", "opus", "/tmp", phase="adversary")
    rows, costs = evidence
    assert (rc, text) == (0, "approved")
    assert cost == pytest.approx(expected) if expected is not None else cost is None
    assert [r["actual_model"] for r in rows] == ["fable-observed", "opus-observed"]
    assert costs[-1]["model"] == "opus-observed"
    assert len(costs) == (2 if first_cost is not None else 1)


def test_sibling_server_data_denied_and_sdk_transports_all_boundary_keys(monkeypatch, tmp_path):
    from claude_agent_sdk import ClaudeAgentOptions
    from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport
    data = tmp_path / "app" / "data"
    workspace = tmp_path / "workspaces" / "job"
    workspace.mkdir(parents=True)
    monkeypatch.setattr(config, "DATA_DIR", str(data))
    monkeypatch.setattr(session_sdk, "_execution_cli", lambda: sys.executable)
    monkeypatch.setattr(session_sdk, "_require_supported_cli", lambda *a: None)
    options = session_sdk._execution_options(str(workspace))
    transport = SubprocessCLITransport(prompt="test", options=ClaudeAgentOptions(**options))
    settings = json.loads(transport._build_settings_value())
    assert str(data.resolve()) in settings["sandbox"]["filesystem"]["denyRead"]
    assert settings["sandbox"]["failIfUnavailable"] is True
    assert "envVars" in settings["sandbox"]["credentials"]
    assert settings["sandbox"]["filesystem"]["disabled"] is False
    assert settings["permissions"]["blockReadsOutsideWorkingDirectories"] is True
