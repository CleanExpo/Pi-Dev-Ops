"""Regression tests for Mission Control Model Fabric."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server import model_fabric as MF  # noqa: E402


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("OMNIROUTE_ENABLED", raising=False)
    assert MF.enabled() is False
    assert MF.role_allowed("margot.casual") is False


def test_margot_role_enabled_explicitly(monkeypatch):
    monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
    monkeypatch.setenv("OMNIROUTE_ROLES", "margot.casual")
    assert MF.role_allowed("margot.casual") is True
    assert MF.role_allowed("planner") is False


def test_default_founder_ladder_blocks_ollama_and_gemma(monkeypatch):
    monkeypatch.delenv("OMNIROUTE_MODELS_FOUNDER_CHAT", raising=False)
    models = MF.models_for_lane("founder-chat")
    assert models
    assert all("ollama" not in model.lower() for model in models)
    assert all("gemma" not in model.lower() for model in models)


def test_env_ladder_filters_banned_models(monkeypatch):
    monkeypatch.setenv(
        "OMNIROUTE_MODELS_FOUNDER_CHAT",
        "ollama:bad,openrouter/nvidia/nemotron-3-super-120b-a12b:free,google/gemma-4",
    )
    assert MF.models_for_lane("founder-chat") == [
        "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
    ]


def test_ladder_falls_back_then_strengthens(monkeypatch):
    monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
    monkeypatch.setenv("OMNIROUTE_ROLES", "margot.casual")
    monkeypatch.setenv(
        "OMNIROUTE_MODELS_FOUNDER_CHAT",
        "openrouter/free-one,openrouter/cheap-two",
    )
    monkeypatch.setenv("OMNIROUTE_MODEL_STRENGTHEN", "openrouter/strong-reviewer")
    monkeypatch.setenv("OMNIROUTE_STRENGTHEN_MARGOT", "always")
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)

    calls: list[str] = []

    def fake_chat_once(*, prompt, model, session_id, timeout_s, max_tokens):
        calls.append(model)
        if model == "openrouter/free-one":
            return False, "", model, "openrouter", 10, "rate_limited"
        if model == "openrouter/cheap-two":
            return True, "draft answer", model, "openrouter", 20, None
        if model == "openrouter/strong-reviewer":
            return True, "strengthened answer", model, "openrouter", 30, None
        raise AssertionError(model)

    monkeypatch.setattr(MF, "_chat_once", fake_chat_once)

    rc, text, cost, error = MF.complete(
        prompt="Please fix and finalise the production issue",
        role="margot.casual",
        session_id="test",
    )
    assert (rc, text, cost, error) == (0, "strengthened answer", 0.0, None)
    assert calls == [
        "openrouter/free-one",
        "openrouter/cheap-two",
        "openrouter/strong-reviewer",
    ]


def test_banned_strength_model_is_disabled(monkeypatch):
    monkeypatch.setenv("OMNIROUTE_MODEL_STRENGTHEN", "google/gemma-4")
    assert MF.strength_model() == ""
