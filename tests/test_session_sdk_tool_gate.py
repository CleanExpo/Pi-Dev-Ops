"""Wiring tests for the session_sdk tool-gate adapter.

The pure decision logic is covered in test_tool_gate.py. Here we verify the SDK
adapter shape: can_use_tool returns the right PermissionResult, the streaming
wrapper yields the documented message dict, and escalation is best-effort.
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

from app.server import session_sdk


def _run(coro):
    return asyncio.run(coro)


def test_stream_wrapper_yields_one_user_message():
    async def collect():
        return [m async for m in session_sdk._tool_gate_stream("hello", "sid-1")]

    msgs = _run(collect())
    assert len(msgs) == 1
    m = msgs[0]
    assert m["type"] == "user"
    assert m["message"] == {"role": "user", "content": "hello"}
    assert m["parent_tool_use_id"] is None
    assert m["session_id"] == "sid-1"


def test_stream_wrapper_defaults_session_id():
    async def first():
        async for m in session_sdk._tool_gate_stream("x", ""):
            return m

    assert _run(first())["session_id"] == "tao"


def test_can_use_tool_allows_benign():
    cb = session_sdk._make_can_use_tool()
    res = _run(cb("Bash", {"command": "ls -la"}, None))
    assert res.behavior == "allow"
    assert res.updated_input == {"command": "ls -la"}


def test_can_use_tool_denies_irreversible_and_escalates(monkeypatch):
    sent = {}

    # Intercept the lazy escalation import path.
    import swarm.telegram_alerts as ta

    def fake_send(message, severity="info", bot_name="Swarm", dedup_key=None):
        sent.update(message=message, severity=severity, dedup_key=dedup_key)
        return True

    monkeypatch.setattr(ta, "send", fake_send)

    cb = session_sdk._make_can_use_tool()
    res = _run(cb("Bash", {"command": "rm -rf /tmp/x"}, None))
    assert res.behavior == "deny"
    assert "irreversible" in res.message.lower()
    assert res.interrupt is False
    assert sent["severity"] == "critical"
    assert sent["dedup_key"] == "toolgate:rm-rf"


def test_escalation_failure_is_swallowed(monkeypatch):
    import swarm.telegram_alerts as ta

    def boom(*a, **k):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(ta, "send", boom)

    cb = session_sdk._make_can_use_tool()
    # Must still return a clean deny despite escalation raising.
    res = _run(cb("Bash", {"command": "git push --force origin main"}, None))
    assert res.behavior == "deny"


def test_unsupported_platform_blocks_before_execution(monkeypatch, tmp_path):
    monkeypatch.setattr(session_sdk.sys, "platform", "win32")
    with pytest.raises(session_sdk.ExecutionBoundaryError, match="unsupported"):
        session_sdk._execution_options(str(tmp_path))


def test_missing_linux_sandbox_dependency_blocks(monkeypatch, tmp_path):
    monkeypatch.setattr(session_sdk.sys, "platform", "linux")
    monkeypatch.setattr(session_sdk.shutil, "which", lambda name: None)
    with pytest.raises(session_sdk.ExecutionBoundaryError, match="sandbox dependencies"):
        session_sdk._execution_options(str(tmp_path))


def test_child_environment_does_not_inherit_application_secrets(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "synthetic-github")
    monkeypatch.setenv("UNKNOWN_APPLICATION_CREDENTIAL", "synthetic-private")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-paid-key")
    monkeypatch.setenv("NODE_OPTIONS", "--require /tmp/untrusted.js")
    before = dict(os.environ)
    child = session_sdk._child_environment()
    for name in ("GITHUB_TOKEN", "UNKNOWN_APPLICATION_CREDENTIAL", "ANTHROPIC_API_KEY", "NODE_OPTIONS"):
        assert child[name] == ""
    assert dict(os.environ) == before


def test_pretool_hook_guards_reads_even_when_sdk_auto_allows(monkeypatch, tmp_path):
    monkeypatch.setattr(session_sdk, "_escalate_blocked_tool", lambda *a: None)
    hook = session_sdk._make_pre_tool_use(str(tmp_path))
    result = _run(hook({"tool_name": "Read", "tool_input": {"file_path": str(tmp_path.parent / "private.txt")}}, None, None))
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_supported_runtime_requests_strict_sandbox(monkeypatch, tmp_path):
    monkeypatch.setattr(session_sdk.sys, "platform", "linux")
    monkeypatch.setattr(session_sdk.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(session_sdk, "_require_supported_cli", lambda path, env: None)
    opts = session_sdk._execution_options(str(tmp_path))
    assert opts["permission_mode"] == "default"
    assert opts["setting_sources"] == []
    assert opts["strict_mcp_config"] is True
    assert opts["mcp_servers"] == {}
    assert opts["sandbox"]["enabled"] is True
    assert opts["sandbox"]["failIfUnavailable"] is True
    assert opts["sandbox"]["allowUnsandboxedCommands"] is False
    assert opts["sandbox"]["autoAllowBashIfSandboxed"] is False
    assert opts["sandbox"]["excludedCommands"] == []
    assert opts["sandbox"]["network"]["allowedDomains"] == []
    assert opts["hooks"]["PreToolUse"]


def test_policy_rejection_never_dispatches_sdk(monkeypatch, tmp_path):
    from app.server import provider_policy
    import claude_agent_sdk
    calls = []
    metrics = []
    def reject(*args, **kwargs):
        raise provider_policy.ProviderPolicyError("subscription_only: synthetic denial")
    monkeypatch.setattr(provider_policy, "require_transport", reject)
    monkeypatch.setattr(session_sdk, "_execution_options", lambda *a: {"cli_path": sys.executable, "env": {}})
    monkeypatch.setattr(claude_agent_sdk, "query", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(session_sdk, "_write_sdk_metric", lambda **kwargs: metrics.append(kwargs))
    rc, text, _ = _run(session_sdk._run_claude_via_sdk("test", "sonnet", str(tmp_path)))
    assert rc != 0
    assert "subscription_only" in text
    assert not calls
    assert metrics[-1]["success"] is False


def test_sandbox_error_result_is_not_success(monkeypatch, tmp_path):
    from app.server import provider_policy
    import claude_agent_sdk
    from unittest.mock import MagicMock
    import swarm.budget_tracker
    metrics = []
    result = MagicMock(spec=claude_agent_sdk.ResultMessage)
    result.is_error = True
    result.subtype = "error_during_execution"
    async def query(**kwargs):
        yield claude_agent_sdk.AssistantMessage(content=[claude_agent_sdk.TextBlock(text="Partial work")], model="sonnet")
        yield result
    monkeypatch.setattr(provider_policy, "require_transport", lambda *a, **kw: {"billing_class": "subscription"})
    monkeypatch.setattr(session_sdk, "_execution_options", lambda *a: {"cli_path": sys.executable, "env": {}})
    monkeypatch.setattr(claude_agent_sdk, "query", query)
    monkeypatch.setattr(swarm.budget_tracker, "record_cost", lambda **kw: None)
    monkeypatch.setattr(session_sdk, "_write_sdk_metric", lambda **kw: metrics.append(kw))
    rc, text, _ = _run(session_sdk._run_claude_via_sdk("test", "sonnet", str(tmp_path)))
    assert rc != 0
    assert "SDK did not report successful execution" in text
    assert metrics[-1]["success"] is False


def test_old_cli_is_not_assumed_to_enforce_new_settings(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(session_sdk.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout="2.1.80 (Claude Code)"))
    with pytest.raises(session_sdk.ExecutionBoundaryError, match="version"):
        session_sdk._require_supported_cli(sys.executable, {})
