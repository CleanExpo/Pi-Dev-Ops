"""Verified subscription SDK dispatch without model, account, or secret-file access."""
import asyncio
import json
import subprocess
import sys
from unittest.mock import Mock

import pytest

from app.server import provider_policy as policy, session_sdk as sdk


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    for key in policy.CLAUDE_ROUTING_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(sdk, "_write_sdk_metric", lambda **kw: None)
    import swarm.budget_tracker
    monkeypatch.setattr(swarm.budget_tracker, "record_cost", lambda **kw: None)


def auth_result(**overrides):
    auth = dict(loggedIn=True, authMethod="claude.ai", apiProvider="firstParty", subscriptionType="max")
    auth.update(overrides)
    return subprocess.CompletedProcess([], 0, json.dumps(auth), "")


def test_sdk_auth_uses_exact_execution_binary_and_environment(monkeypatch):
    env = {"PATH": "synthetic", "ANTHROPIC_API_KEY": ""}
    call = Mock(return_value=auth_result())
    monkeypatch.setattr(policy.subprocess, "run", call)
    result = policy.require_transport("anthropic_agent_sdk", cli_path=sys.executable, env=env)
    assert call.call_args.args[0] == [sys.executable, "auth", "status"]
    assert call.call_args.kwargs["env"] == env
    assert result["auth_verified"] is True
    assert result["billing_class"] == "subscription"
    assert result["cost_verified"] is False


@pytest.mark.parametrize("kwargs", [{}, {"cli_path": "claude", "env": {}}, {"cli_path": sys.executable}])
def test_sdk_requires_explicit_execution_binding(monkeypatch, kwargs):
    call = Mock()
    monkeypatch.setattr(policy.subprocess, "run", call)
    with pytest.raises(policy.ProviderPolicyError, match="bound"):
        policy.require_transport("anthropic_agent_sdk", **kwargs)
    call.assert_not_called()


@pytest.mark.parametrize("where", ["ambient", "child"])
def test_api_override_cannot_be_hidden_by_environment_scrubbing(monkeypatch, where):
    env = {"ANTHROPIC_API_KEY": ""}
    if where == "ambient":
        monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic")
    else:
        env["ANTHROPIC_API_KEY"] = "synthetic"
    call = Mock()
    monkeypatch.setattr(policy.subprocess, "run", call)
    with pytest.raises(policy.ProviderPolicyError):
        policy.require_transport("anthropic_agent_sdk", cli_path=sys.executable, env=env)
    call.assert_not_called()


@pytest.mark.parametrize("auth", [dict(loggedIn=False), dict(authMethod="api_key"), dict(subscriptionType=None), dict(apiProvider="bedrock")])
def test_invalid_sdk_auth_never_authorizes(monkeypatch, auth):
    monkeypatch.setattr(policy.subprocess, "run", Mock(return_value=auth_result(**auth)))
    with pytest.raises(policy.ProviderPolicyError):
        policy.require_transport("anthropic_agent_sdk", cli_path=sys.executable, env={})


@pytest.mark.parametrize("supported", [True, False])
def test_readiness_never_runs_auth_or_models(monkeypatch, supported):
    monkeypatch.setattr(sdk.sys, "platform", "linux" if supported else "win32")
    monkeypatch.setattr(sdk.shutil, "which", lambda name: sys.executable)
    call = Mock(side_effect=AssertionError("readiness must not launch subprocesses"))
    monkeypatch.setattr(policy.subprocess, "run", call)
    result = sdk.generation_readiness()
    assert result["status"] == ("unverified" if supported else "blocked")
    assert result["ready"] is (None if supported else False)
    assert result["auth_verified"] is False
    assert result["cost_verified"] is False
    call.assert_not_called()


def test_absent_credentials_cannot_be_inherited_later(monkeypatch):
    for name in ("CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CONFIG_DIR"):
        monkeypatch.delenv(name, raising=False)
    child = sdk._child_environment()
    for name in (*policy.CLAUDE_ROUTING_ENV, "CLAUDE_CODE_OAUTH_TOKEN"):
        assert child[name] == ""


def test_config_dir_is_pinned_to_the_home_default_and_never_blanked(monkeypatch, tmp_path):
    """An empty CLAUDE_CONFIG_DIR is not an unset one.

    Blanking the path resolves the CLI's credential store to the wrong location,
    so a correctly logged-in subscription host reports loggedIn:false and the
    transport check refuses it. Measured on the deployed container: absent and
    `<home>/.claude` both report claude.ai/max; `""` reports authMethod none.
    """
    monkeypatch.setattr(sdk.sys, "platform", "linux")
    monkeypatch.setenv("HOME", str(tmp_path))
    child = sdk._child_environment()
    assert child["CLAUDE_CONFIG_DIR"] == str(tmp_path / ".claude")


def test_config_dir_cannot_be_redirected_by_the_parent_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(sdk.sys, "platform", "linux")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/tmp/parent-redirected-store")
    child = sdk._child_environment()
    assert child["CLAUDE_CONFIG_DIR"] == str(tmp_path / ".claude")


@pytest.mark.parametrize("home", ["/", ""])
def test_degenerate_home_leaves_the_config_dir_blank(monkeypatch, home):
    monkeypatch.setattr(sdk.sys, "platform", "linux")
    monkeypatch.setenv("HOME", home)
    assert sdk._child_environment()["CLAUDE_CONFIG_DIR"] == ""


def test_darwin_keeps_the_config_dir_blank_so_the_keychain_store_still_resolves(monkeypatch, tmp_path):
    """Pinning the path on darwin switches the CLI off the keychain onto a file
    store whose stale credentials authenticate as nobody, so darwin keeps the
    blanked value that leaves its supported login working."""
    monkeypatch.setattr(sdk.sys, "platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert sdk._child_environment()["CLAUDE_CONFIG_DIR"] == ""


def test_cli_replaced_during_version_check_is_rejected(monkeypatch, tmp_path):
    binary = tmp_path / "claude"
    binary.write_text("old executable")
    def version(*args, **kwargs):
        binary.write_text("different executable")
        return subprocess.CompletedProcess([], 0, "2.1.260 (Claude Code)", "")
    monkeypatch.setattr(sdk.subprocess, "run", version)
    with pytest.raises(sdk.ExecutionBoundaryError, match="version"):
        sdk._require_supported_cli(str(binary), {})


@pytest.mark.parametrize("swap_binary", [False, True])
def test_verified_sdk_can_dispatch_but_changed_binary_cannot(monkeypatch, tmp_path, swap_binary):
    import claude_agent_sdk
    from unittest.mock import MagicMock
    binary = tmp_path / "claude"
    binary.write_text("synthetic executable")
    opts = {"cli_path": str(binary), "env": {"ANTHROPIC_API_KEY": ""}}
    monkeypatch.setattr(sdk, "_execution_options", lambda _: opts)
    calls = []
    def verify(*args, **kwargs):
        assert args == ("anthropic_agent_sdk",)
        assert kwargs == {"cli_path": str(binary), "env": opts["env"]}
        if swap_binary:
            binary.write_text("replacement executable identity")
        return {"billing_class": "subscription", "auth_verified": True, "cost_verified": False}
    monkeypatch.setattr(policy, "require_transport", verify)
    result = MagicMock(spec=claude_agent_sdk.ResultMessage)
    result.is_error = False
    result.subtype = "success"
    async def query(**kwargs):
        calls.append(kwargs)
        yield claude_agent_sdk.AssistantMessage(content=[claude_agent_sdk.TextBlock(text="done")], model="sonnet")
        yield result
    monkeypatch.setattr(claude_agent_sdk, "query", query)
    rc, text, _ = asyncio.run(sdk._run_claude_via_sdk("work", "sonnet", str(tmp_path)))
    if swap_binary:
        assert rc != 0
        assert not calls
    else:
        assert rc == 0 and text == "done"
        assert calls[0]["options"].cli_path == str(binary)
        assert calls[0]["options"].env == opts["env"]


def test_retry_reverifies_subscription_and_stops_if_auth_changed(monkeypatch, tmp_path):
    import claude_agent_sdk
    from unittest.mock import MagicMock
    monkeypatch.setattr(sdk, "_execution_options", lambda _: {"cli_path": sys.executable, "env": {}})
    monkeypatch.setattr(sdk.config, "FABLE_ALLOWED_ROLES", {"adversary"})
    auth = Mock(side_effect=[
        {"auth_verified": True},
        policy.ProviderPolicyError("subscription_only: login changed"),
    ])
    monkeypatch.setattr(policy, "require_transport", auth)
    called = []
    async def query(**kwargs):
        called.append(kwargs)
        result = MagicMock(spec=claude_agent_sdk.ResultMessage)
        result.is_error = False
        result.subtype = "success"
        result.stop_reason = "refusal"
        yield result
    monkeypatch.setattr(claude_agent_sdk, "query", query)
    rc, text, _ = asyncio.run(sdk._run_claude_via_sdk("review", "opus", str(tmp_path), phase="adversary"))
    assert rc != 0 and "subscription_only" in text
    assert auth.call_count == 2
    assert len(called) == 1
