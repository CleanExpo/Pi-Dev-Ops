"""Main compatibility must never remove required execution safeguards."""
import asyncio
from dataclasses import dataclass
import sys
from unittest.mock import Mock

import pytest
from app.server import provider_policy, session_sdk


@pytest.mark.asyncio
async def test_old_sdk_options_cannot_drop_execution_boundary(monkeypatch, tmp_path):
    import claude_agent_sdk
    @dataclass
    class OldOptions:
        cwd: str
        model: str
    query = Mock(side_effect=AssertionError("model dispatch forbidden"))
    monkeypatch.setattr(claude_agent_sdk, "ClaudeAgentOptions", OldOptions)
    monkeypatch.setattr(claude_agent_sdk, "query", query)
    monkeypatch.setattr(provider_policy, "require_transport", lambda *a, **kw: {})
    monkeypatch.setattr(session_sdk, "_execution_options", lambda _: {
        "cli_path": sys.executable, "env": {}, "sandbox": {"enabled": True},
    })
    monkeypatch.setattr(session_sdk, "_write_sdk_metric", lambda **kw: None)
    rc, text, cost = await session_sdk._run_claude_via_sdk("test", "sonnet", str(tmp_path))
    assert rc == 1 and text.startswith("execution_blocked:")
    assert cost is None
    query.assert_not_called()


@pytest.mark.asyncio
async def test_verified_sdk_preserves_scoped_trust_without_mutating_auth(monkeypatch, tmp_path):
    import claude_agent_sdk
    from app.server import claude_workspace_trust
    order = []
    async def query(**kwargs):
        order.append("query")
        yield claude_agent_sdk.ResultMessage(subtype="success", duration_ms=1,
            duration_api_ms=1, is_error=False, num_turns=1, session_id="synthetic")
    def trust(workspace):
        assert workspace == str(tmp_path)
        order.append("trust")
    monkeypatch.setattr(claude_workspace_trust, "ensure_workspace_trusted", trust)
    monkeypatch.setattr(claude_workspace_trust, "prepare_sdk_environment",
                        Mock(side_effect=AssertionError("ambient auth mutation forbidden")))
    monkeypatch.setattr(claude_agent_sdk, "query", query)
    monkeypatch.setattr(provider_policy, "require_transport", lambda *a, **kw: {})
    monkeypatch.setattr(session_sdk, "_execution_options", lambda _: {"cli_path": sys.executable, "env": {}})
    monkeypatch.setattr(session_sdk, "_write_sdk_metric", lambda **kw: None)
    assert (await session_sdk._run_claude_via_sdk("test", "sonnet", str(tmp_path)))[0] == 0
    assert order == ["trust", "query"]


@pytest.mark.asyncio
async def test_sdk_cancellation_closes_iterator_and_records_terminal_evidence(monkeypatch, tmp_path):
    import claude_agent_sdk
    from app.server import claude_workspace_trust
    entered, closed, rows = asyncio.Event(), asyncio.Event(), []
    async def query(**kwargs):
        try:
            entered.set()
            await asyncio.Future()
            yield
        finally:
            closed.set()
    monkeypatch.setattr(claude_agent_sdk, "query", query)
    monkeypatch.setattr(claude_workspace_trust, "ensure_workspace_trusted", lambda _: None)
    monkeypatch.setattr(provider_policy, "require_transport", lambda *a, **kw: {})
    monkeypatch.setattr(session_sdk, "_execution_options", lambda _: {"cli_path": sys.executable, "env": {}})
    monkeypatch.setattr(session_sdk, "_write_sdk_metric", lambda **kw: rows.append(kw))
    task = asyncio.create_task(session_sdk._run_claude_via_sdk("test", "sonnet", str(tmp_path)))
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()
    assert rows[-1]["success"] is False and rows[-1]["error"] == "cancelled"
