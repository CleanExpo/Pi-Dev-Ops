"""tests/test_portfolio_synthesis_opus_policy.py — RA-1922 regression.

Locks the contract: the role bucket ``portfolio`` (which is what arrives at
``model_policy.assert_model_allowed`` after ``session_sdk.py:127`` strips the
dot-suffix from ``portfolio.synthesis``) is allowed to use Opus.

Without this allow-listing the cross-portfolio synthesis (RA-1892, the "10x
layer" of the daily Portfolio Pulse) silently degrades to its
``synthesis unavailable`` fallback every run, defeating the purpose.
"""
from __future__ import annotations

import importlib

import pytest


def _reload_policy_with(env_value: str | None, monkeypatch):
    """Re-import config + model_policy with a chosen TAO_OPUS_ALLOWED_ROLES."""
    if env_value is None:
        monkeypatch.delenv("TAO_OPUS_ALLOWED_ROLES", raising=False)
    else:
        monkeypatch.setenv("TAO_OPUS_ALLOWED_ROLES", env_value)
    import app.server.config as config
    importlib.reload(config)
    import app.server.model_policy as model_policy
    importlib.reload(model_policy)
    return config, model_policy


def test_portfolio_role_can_use_opus_by_default(monkeypatch):
    """RA-1922: ``portfolio`` is in the default allow-list so synthesis works."""
    config, model_policy = _reload_policy_with(None, monkeypatch)
    assert "portfolio" in config.OPUS_ALLOWED_ROLES
    # Should not raise.
    model_policy.assert_model_allowed("portfolio", "claude-opus-4-7")


def test_portfolio_synthesis_dot_suffix_strips_to_portfolio_bucket(monkeypatch):
    """``session_sdk.py:127`` does ``role.split(".")[0]`` — assert the
    same transformation lands on a role that survives the policy gate."""
    config, model_policy = _reload_policy_with(None, monkeypatch)
    role_full = "portfolio.synthesis"
    role_bucket = role_full.split(".")[0]  # mirror session_sdk.py:127
    assert role_bucket == "portfolio"
    # Should not raise.
    model_policy.assert_model_allowed(role_bucket, "claude-opus-4-7")


def test_unrelated_role_still_rejected(monkeypatch):
    """Adding ``portfolio`` must not loosen the gate for arbitrary roles."""
    _, model_policy = _reload_policy_with(None, monkeypatch)
    with pytest.raises(ValueError, match="role=evaluator cannot use opus"):
        model_policy.assert_model_allowed("evaluator", "claude-opus-4-7")


def test_env_override_can_still_remove_portfolio(monkeypatch):
    """An operator who explicitly tightens the allow-list still can."""
    config, model_policy = _reload_policy_with("planner,orchestrator", monkeypatch)
    assert "portfolio" not in config.OPUS_ALLOWED_ROLES
    with pytest.raises(ValueError, match="role=portfolio cannot use opus"):
        model_policy.assert_model_allowed("portfolio", "claude-opus-4-7")


def test_planner_orchestrator_adversary_still_allowed(monkeypatch):
    """Existing roles must keep working — no regression."""
    _, model_policy = _reload_policy_with(None, monkeypatch)
    for role in ("planner", "orchestrator", "adversary"):
        # Should not raise for any of these.
        model_policy.assert_model_allowed(role, "claude-opus-4-7")
