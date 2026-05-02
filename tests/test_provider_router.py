"""tests/test_provider_router.py — provider router smoke."""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server import provider_router as PR  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for k in [
        "TAO_TOP_MODEL", "TAO_MID_MODEL", "TAO_CHEAP_MODEL",
    ]:
        monkeypatch.delenv(k, raising=False)
    import os
    for k in list(os.environ.keys()):
        if k.startswith("TAO_MODEL_"):
            monkeypatch.delenv(k, raising=False)


# ── Tier defaults ───────────────────────────────────────────────────────────


def test_planner_routes_to_top_anthropic():
    pm = PR.select_provider_model("planner")
    assert pm.tier == "top"
    assert pm.provider == "anthropic"
    assert pm.model_id == PR.DEFAULT_TOP_MODEL


def test_orchestrator_routes_to_top_anthropic():
    pm = PR.select_provider_model("orchestrator")
    assert pm.tier == "top"
    assert pm.provider == "anthropic"


def test_board_routes_to_top():
    pm = PR.select_provider_model("board")
    assert pm.tier == "top"


def test_debate_drafter_and_redteam_top():
    assert PR.select_provider_model("debate.drafter").tier == "top"
    assert PR.select_provider_model("debate.redteam").tier == "top"


def test_margot_synthesis_top():
    """Phase 2 (research-integrated) gets top tier."""
    pm = PR.select_provider_model("margot.synthesis")
    assert pm.tier == "top"
    assert pm.provider == "anthropic"


def test_generator_routes_to_mid():
    pm = PR.select_provider_model("generator")
    assert pm.tier == "mid"
    assert pm.provider == "anthropic"
    assert pm.model_id == PR.DEFAULT_MID_MODEL


def test_evaluator_mid():
    assert PR.select_provider_model("evaluator").tier == "mid"


def test_margot_casual_routes_to_cheap():
    """Phase 1 (default conversational turn) goes to cheap tier."""
    pm = PR.select_provider_model("margot.casual")
    assert pm.tier == "cheap"
    assert pm.provider == "openrouter"
    assert pm.model_id == PR.DEFAULT_CHEAP_MODEL


def test_intent_classify_cheap():
    assert PR.select_provider_model("intent_classify").tier == "cheap"


def test_unknown_role_defaults_to_mid():
    pm = PR.select_provider_model("unrecognised_role_xyz")
    assert pm.tier == "mid"


# ── Tier env overrides ──────────────────────────────────────────────────────


def test_tao_top_model_env_overrides_default(monkeypatch):
    monkeypatch.setenv("TAO_TOP_MODEL", "claude-sonnet-4-6")
    pm = PR.select_provider_model("planner")
    assert pm.model_id == "claude-sonnet-4-6"


def test_tao_cheap_model_env_overrides_default(monkeypatch):
    monkeypatch.setenv("TAO_CHEAP_MODEL", "meta-llama/llama-3.3-70b-instruct")
    pm = PR.select_provider_model("margot.casual")
    assert pm.model_id == "meta-llama/llama-3.3-70b-instruct"
    assert pm.provider == "openrouter"


def test_tao_cheap_anthropic_haiku_routes_via_anthropic(monkeypatch):
    """Setting cheap to claude-haiku-* keeps the call on Anthropic."""
    monkeypatch.setenv("TAO_CHEAP_MODEL", "claude-haiku-4-5")
    pm = PR.select_provider_model("margot.casual")
    assert pm.provider == "anthropic"
    assert pm.model_id == "claude-haiku-4-5"


# ── Per-role overrides ─────────────────────────────────────────────────────


def test_per_role_env_override(monkeypatch):
    monkeypatch.setenv(
        "TAO_MODEL_MARGOT_CASUAL",
        "openrouter:meta-llama/llama-3.3-70b-instruct",
    )
    pm = PR.select_provider_model("margot.casual")
    assert pm.source == "env_role_override"
    assert pm.provider == "openrouter"
    assert pm.model_id == "meta-llama/llama-3.3-70b-instruct"


def test_per_role_override_to_anthropic(monkeypatch):
    monkeypatch.setenv(
        "TAO_MODEL_MARGOT_CASUAL",
        "anthropic:claude-haiku-4-5",
    )
    pm = PR.select_provider_model("margot.casual")
    assert pm.provider == "anthropic"
    assert pm.model_id == "claude-haiku-4-5"


def test_per_role_override_role_with_dot(monkeypatch):
    """Role names with dots (e.g. 'debate.redteam') become DEBATE_REDTEAM env."""
    monkeypatch.setenv(
        "TAO_MODEL_DEBATE_REDTEAM",
        "openrouter:google/gemma-3-27b-it",
    )
    pm = PR.select_provider_model("debate.redteam")
    assert pm.source == "env_role_override"
    assert pm.provider == "openrouter"


def test_per_role_override_malformed_falls_through(monkeypatch):
    """No colon in env → ignored, falls back to tier default."""
    monkeypatch.setenv("TAO_MODEL_MARGOT_CASUAL", "no-colon-here")
    pm = PR.select_provider_model("margot.casual")
    assert pm.source == "env_tier_default"


def test_per_role_override_unknown_provider_falls_through(monkeypatch):
    monkeypatch.setenv(
        "TAO_MODEL_MARGOT_CASUAL", "google:gemini-pro",  # bogus prefix
    )
    pm = PR.select_provider_model("margot.casual")
    assert pm.source == "env_tier_default"


# ── is_anthropic / is_openrouter helpers ───────────────────────────────────


def test_is_anthropic_helper():
    pm = PR.ProviderModel(provider="anthropic", model_id="x", tier="top",
                            role="r", source="default")
    assert PR.is_anthropic(pm) is True
    assert PR.is_openrouter(pm) is False


def test_is_openrouter_helper():
    pm = PR.ProviderModel(provider="openrouter", model_id="x", tier="cheap",
                            role="r", source="default")
    assert PR.is_openrouter(pm) is True
    assert PR.is_anthropic(pm) is False


# ── run_via_provider dispatch ──────────────────────────────────────────────


def test_run_via_provider_anthropic_path(monkeypatch):
    """role=planner → Anthropic SDK call."""
    captured: dict = {}

    async def fake_anthropic(*, prompt, model, workspace, timeout,
                              session_id, phase, thinking):
        captured.update({
            "model": model, "phase": phase, "thinking": thinking,
        })
        return 0, "anthropic reply", 0.05

    fake_sdk = types.SimpleNamespace(_run_claude_via_sdk=fake_anthropic)
    monkeypatch.setitem(sys.modules, "app.server.session_sdk", fake_sdk)

    rc, text, cost, error = asyncio.run(PR.run_via_provider(
        prompt="hi", role="planner", session_id="s1",
    ))
    assert rc == 0
    assert text == "anthropic reply"
    assert cost == 0.05
    assert error is None
    assert captured["phase"] == "planner"
    assert captured["model"] == PR.DEFAULT_TOP_MODEL


def test_run_via_provider_openrouter_path(monkeypatch):
    """role=margot.casual → OpenRouter call."""
    async def fake_or_call(*, prompt, model_id, timeout_s, max_tokens=4096,
                            role="", session_id=""):
        return 0, "gemma reply", 0.0001, None

    fake_mod = types.SimpleNamespace(call=fake_or_call)
    monkeypatch.setitem(sys.modules, "app.server.provider_openrouter", fake_mod)

    rc, text, cost, error = asyncio.run(PR.run_via_provider(
        prompt="hi", role="margot.casual",
    ))
    assert rc == 0
    assert text == "gemma reply"
    assert cost == 0.0001
    assert error is None


def test_run_via_provider_anthropic_sdk_failure(monkeypatch):
    async def boom(*, prompt, model, workspace, timeout,
                    session_id, phase, thinking):
        raise RuntimeError("anthropic api down")

    fake_sdk = types.SimpleNamespace(_run_claude_via_sdk=boom)
    monkeypatch.setitem(sys.modules, "app.server.session_sdk", fake_sdk)

    rc, text, cost, error = asyncio.run(PR.run_via_provider(
        prompt="hi", role="planner",
    ))
    assert rc == 1
    assert "anthropic_sdk_call_raised" in error


def test_run_via_provider_openrouter_failure_propagates(monkeypatch):
    async def fake_or_call(**kw):
        return 1, "", 0.0, "openrouter_no_api_key"

    fake_mod = types.SimpleNamespace(call=fake_or_call)
    monkeypatch.setitem(sys.modules, "app.server.provider_openrouter", fake_mod)

    rc, text, cost, error = asyncio.run(PR.run_via_provider(
        prompt="hi", role="margot.casual",
    ))
    assert rc == 1
    assert error == "openrouter_no_api_key"
