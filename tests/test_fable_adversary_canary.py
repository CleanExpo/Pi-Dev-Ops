"""tests/test_fable_adversary_canary.py — RA-1099 Wave-3 regression.

Locks the fable adversary canary contract:
  (i)   adversary + TAO_FABLE_ALLOWED_ROLES=adversary resolves to claude-fable-5
  (ii)  adversary with the env unset stays on opus (canary OFF by default)
  (iii) a fable-path stop_reason=="refusal" triggers the one-shot opus retry and
        does NOT return silent success; sampling params never reach the fable path.

Mirrors the reload pattern in test_portfolio_synthesis_opus_policy.py and the
fake-`claude_agent_sdk` injection so the SDK path is testable without the real
package installed.
"""
from __future__ import annotations

import importlib
import sys
import types
from unittest.mock import patch

import pytest


def _reload_policy_with(env_value: str | None, monkeypatch):
    """Re-import config + model_policy with a chosen TAO_FABLE_ALLOWED_ROLES."""
    if env_value is None:
        monkeypatch.delenv("TAO_FABLE_ALLOWED_ROLES", raising=False)
    else:
        monkeypatch.setenv("TAO_FABLE_ALLOWED_ROLES", env_value)
    import app.server.config as config
    importlib.reload(config)
    import app.server.model_policy as model_policy
    importlib.reload(model_policy)
    return config, model_policy


def test_adversary_resolves_to_fable_when_canary_on(monkeypatch):
    """(i) With the env set, the adversary role selects and is permitted the fable tier."""
    config, model_policy = _reload_policy_with("adversary", monkeypatch)
    assert "adversary" in config.FABLE_ALLOWED_ROLES
    assert model_policy.select_model("adversary") == "fable"
    assert model_policy.resolve_to_id("fable") == "claude-fable-5"
    # Gate permits fable for the allow-listed role (must not raise).
    model_policy.assert_model_allowed("adversary", "claude-fable-5")


def test_adversary_stays_opus_when_canary_off(monkeypatch):
    """(ii) With the env unset (default), adversary stays opus and fable is rejected."""
    config, model_policy = _reload_policy_with(None, monkeypatch)
    assert config.FABLE_ALLOWED_ROLES == set()
    assert model_policy.select_model("adversary") == "opus"
    with pytest.raises(ValueError, match="cannot use fable"):
        model_policy.assert_model_allowed("adversary", "claude-fable-5")


def test_non_allowlisted_role_cannot_use_fable(monkeypatch):
    """Enabling fable for adversary must not loosen the gate for other roles."""
    _config, model_policy = _reload_policy_with("adversary", monkeypatch)
    with pytest.raises(ValueError, match="role=generator cannot use fable"):
        model_policy.assert_model_allowed("generator", "claude-fable-5")


def _install_fake_sdk(monkeypatch, seen_models, seen_opts):
    """Inject a fake claude_agent_sdk. The fable model refuses; opus succeeds."""
    class _TB:
        def __init__(self, text):
            self.text = text

    class _AM:
        def __init__(self, content, stop_reason=None, usage=None):
            self.content = content
            self.stop_reason = stop_reason
            self.usage = usage

    class _RM:
        def __init__(self, stop_reason=None, usage=None):
            self.stop_reason = stop_reason
            self.usage = usage

    class _Opts:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    class _ThAdaptive:
        def __init__(self, type="adaptive"):
            self.type = type

    class _ThEnabled:
        def __init__(self, type="enabled", budget_tokens=None):
            self.type = type
            self.budget_tokens = budget_tokens

    class _ThDisabled:
        def __init__(self, type="disabled"):
            self.type = type

    async def _query(prompt=None, options=None):  # noqa: ARG001
        seen_models.append(options.model)
        seen_opts.append(options)
        if options.model == "claude-fable-5":
            # Hard refusal — no text, ResultMessage carries stop_reason=refusal.
            yield _RM(stop_reason="refusal", usage={"output_tokens": 12})
        else:
            yield _AM(content=[_TB("Concern 1: race in handler\nAPPROVE")],
                      usage={"output_tokens": 40})
            yield _RM(stop_reason="end_turn", usage={"output_tokens": 40})

    fake_sdk = types.ModuleType("claude_agent_sdk")
    fake_sdk.AssistantMessage = _AM
    fake_sdk.ResultMessage = _RM
    fake_sdk.TextBlock = _TB
    fake_sdk.ClaudeAgentOptions = _Opts
    fake_sdk.query = _query
    fake_types = types.ModuleType("claude_agent_sdk.types")
    fake_types.ThinkingConfigAdaptive = _ThAdaptive
    fake_types.ThinkingConfigEnabled = _ThEnabled
    fake_types.ThinkingConfigDisabled = _ThDisabled
    return {"claude_agent_sdk": fake_sdk, "claude_agent_sdk.types": fake_types}


@pytest.mark.asyncio
async def test_fable_refusal_falls_back_to_opus_no_silent_success(monkeypatch):
    """(iii) A fable refusal retries on opus-4-8 and returns opus's real review —
    never a silent success — and no sampling params reach the fable path."""
    from app.server import config, session_sdk

    monkeypatch.setattr(config, "FABLE_ALLOWED_ROLES", {"adversary"})

    seen_models: list[str] = []
    seen_opts: list = []
    fake_modules = _install_fake_sdk(monkeypatch, seen_models, seen_opts)

    metrics: list[dict] = []
    monkeypatch.setattr(session_sdk, "_write_sdk_metric", lambda **kw: metrics.append(kw))

    with patch.dict(sys.modules, fake_modules):
        rc, text, cost = await session_sdk._run_claude_via_sdk(
            prompt="review this diff",
            model="opus",           # adversary passes 'opus'; canary overrides to fable
            workspace="/tmp",
            timeout=30,
            session_id="t-canary",
            phase="adversary",
            thinking="enabled",     # exercise the fable adaptive-only strip
        )

    # Fable refused → one-shot retry on opus-5 → opus's success is returned.
    assert seen_models == ["claude-fable-5", "claude-opus-5"]
    assert rc == 0
    assert "APPROVE" in text

    # The fable attempt is recorded as an explicit failure (not silent success).
    fable_rows = [m for m in metrics if m["model"] == "claude-fable-5"]
    assert fable_rows and fable_rows[0]["success"] is False
    assert fable_rows[0]["error"] == "refusal"
    assert fable_rows[0]["stop_reason"] == "refusal"
    assert fable_rows[0]["output_tokens"] == 12  # amplification field populated
    opus_rows = [m for m in metrics if m["model"] == "claude-opus-5"]
    assert opus_rows and opus_rows[0]["success"] is True
    assert opus_rows[0]["output_tokens"] == 40

    # PARAM STRIP — the fable options carry no sampling params and thinking is
    # forced to adaptive (no budget_tokens), even though thinking='enabled' was
    # requested. This proves no temperature/top_p/top_k reaches the fable path.
    fable_opts = seen_opts[0]
    assert fable_opts.model == "claude-fable-5"
    for banned in ("temperature", "top_p", "top_k", "budget_tokens"):
        assert not hasattr(fable_opts, banned)
    assert fable_opts.thinking.type == "adaptive"
    assert not hasattr(fable_opts.thinking, "budget_tokens")
