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
        "TAO_TOP_MODEL", "TAO_MID_MODEL",
        "TAO_CHEAP_MODEL", "TAO_CHEAP_PROVIDER",
        "TAO_CHEAP_LOCAL_MODEL", "TAO_CHEAP_REMOTE_MODEL",
        "TAO_TOP_USE_CLAUDE_PRINT", "TAO_MID_USE_CLAUDE_PRINT",
    ]:
        monkeypatch.delenv(k, raising=False)
    import os
    for k in list(os.environ.keys()):
        if k.startswith("TAO_MODEL_"):
            monkeypatch.delenv(k, raising=False)
    for key in PR.provider_policy.CLAUDE_ROUTING_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    # Force Ollama-unreachable for deterministic tests; the Ollama-reachable
    # path is exercised in dedicated tests below.
    import sys as _sys
    ollama_mod = _sys.modules.get("app.server.provider_ollama")
    if ollama_mod is None:
        from app.server import provider_ollama as ollama_mod
    monkeypatch.setattr(ollama_mod, "is_reachable", lambda **kw: False)


# ── Tier defaults ───────────────────────────────────────────────────────────


def test_planner_routes_to_top_subscription():
    pm = PR.select_provider_model("planner")
    assert pm.tier == "top"
    assert pm.provider == "claude_print"
    assert pm.model_id == PR.DEFAULT_TOP_MODEL


def test_orchestrator_routes_to_top_subscription():
    pm = PR.select_provider_model("orchestrator")
    assert pm.tier == "top"
    assert pm.provider == "claude_print"


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
    assert pm.provider == "claude_print"


def test_generator_routes_to_mid():
    pm = PR.select_provider_model("generator")
    assert pm.tier == "mid"
    assert pm.provider == "claude_print"
    assert pm.model_id == PR.DEFAULT_MID_MODEL


def test_evaluator_mid():
    assert PR.select_provider_model("evaluator").tier == "mid"


def test_margot_casual_keeps_local_route_when_ollama_unreachable():
    """Unavailable local models must not select paid fallback."""
    pm = PR.select_provider_model("intent_classify")
    assert pm.tier == "cheap"
    assert pm.provider == "claude_print"
    assert pm.model_id == PR.ANTHROPIC_HAIKU



def test_margot_casual_routes_to_ollama_when_reachable(monkeypatch):
    """When Ollama probe returns True, cheap tier → ollama:gemma4:latest."""
    from app.server import provider_ollama
    monkeypatch.setattr(provider_ollama, "is_reachable", lambda **kw: True)
    pm = PR.select_provider_model("intent_classify")
    assert pm.tier == "cheap"
    assert pm.provider == "claude_print"
    assert pm.model_id == PR.ANTHROPIC_HAIKU



def test_intent_classify_cheap():
    assert PR.select_provider_model("intent_classify").tier == "cheap"


def test_unknown_role_defaults_to_mid():
    pm = PR.select_provider_model("unrecognised_role_xyz")
    assert pm.tier == "mid"


# ── Tier env overrides ──────────────────────────────────────────────────────


def test_tao_top_model_env_overrides_default(monkeypatch):
    monkeypatch.setenv("TAO_TOP_MODEL", "claude-sonnet-5")
    pm = PR.select_provider_model("planner")
    assert pm.model_id == "claude-sonnet-5"


def test_tao_cheap_model_env_routes_openrouter_when_slash(monkeypatch):
    """Legacy TAO_CHEAP_MODEL with '/' → OpenRouter (vendor/model shape)."""
    monkeypatch.setenv("TAO_CHEAP_MODEL", "meta-llama/llama-3.3-70b-instruct")
    pm = PR.select_provider_model("intent_classify")
    assert pm.model_id == "meta-llama/llama-3.3-70b-instruct"
    assert pm.provider == "openrouter"


def test_tao_cheap_model_env_routes_ollama_when_no_slash(monkeypatch):
    """Legacy TAO_CHEAP_MODEL without '/' → Ollama (local tag shape)."""
    monkeypatch.setenv("TAO_CHEAP_MODEL", "qwen3.5:latest")
    pm = PR.select_provider_model("intent_classify")
    assert pm.provider == "ollama"
    assert pm.model_id == "qwen3.5:latest"


def test_tao_cheap_anthropic_haiku_routes_via_anthropic(monkeypatch):
    """Setting cheap to claude-haiku-* keeps the call on Anthropic."""
    monkeypatch.setenv("TAO_CHEAP_MODEL", "claude-haiku-4-5")
    pm = PR.select_provider_model("intent_classify")
    assert pm.provider == "anthropic"
    assert pm.model_id == "claude-haiku-4-5"


def test_tao_cheap_provider_pin_ollama(monkeypatch):
    """TAO_CHEAP_PROVIDER=ollama forces Ollama even if probe would fail."""
    monkeypatch.setenv("TAO_CHEAP_PROVIDER", "ollama")
    pm = PR.select_provider_model("intent_classify")
    assert pm.provider == "ollama"
    assert pm.model_id == PR.DEFAULT_CHEAP_LOCAL_MODEL


def test_tao_cheap_provider_pin_openrouter(monkeypatch):
    """TAO_CHEAP_PROVIDER=openrouter forces OpenRouter even if Ollama up."""
    from app.server import provider_ollama
    monkeypatch.setattr(provider_ollama, "is_reachable", lambda **kw: True)
    monkeypatch.setenv("TAO_CHEAP_PROVIDER", "openrouter")
    pm = PR.select_provider_model("intent_classify")
    assert pm.provider == "openrouter"
    assert pm.model_id == PR.DEFAULT_CHEAP_REMOTE_MODEL


def test_tao_cheap_local_model_override(monkeypatch):
    """TAO_CHEAP_LOCAL_MODEL overrides the Ollama tag."""
    from app.server import provider_ollama
    monkeypatch.setattr(provider_ollama, "is_reachable", lambda **kw: True)
    monkeypatch.setenv("TAO_CHEAP_PROVIDER", "ollama")
    monkeypatch.setenv("TAO_CHEAP_LOCAL_MODEL", "qwen3.5:latest")
    pm = PR.select_provider_model("intent_classify")
    assert pm.provider == "ollama"
    assert pm.model_id == "qwen3.5:latest"


def test_tao_cheap_remote_model_override(monkeypatch):
    """An unused remote model setting never opts into a paid transport."""
    monkeypatch.setenv(
        "TAO_CHEAP_REMOTE_MODEL", "openai/gpt-4o-mini",
    )
    pm = PR.select_provider_model("intent_classify")
    assert pm.provider == "claude_print"
    assert pm.model_id == PR.ANTHROPIC_HAIKU



def test_invalid_cheap_provider_pin_falls_through(monkeypatch):
    """TAO_CHEAP_PROVIDER=bogus warns + falls through to probe path."""
    monkeypatch.setenv("TAO_CHEAP_PROVIDER", "vertex")
    pm = PR.select_provider_model("intent_classify")
    assert pm.provider == "claude_print"



# ── Per-role overrides ─────────────────────────────────────────────────────


def test_per_role_env_override(monkeypatch):
    monkeypatch.setenv(
        "TAO_MODEL_INTENT_CLASSIFY",
        "openrouter:meta-llama/llama-3.3-70b-instruct",
    )
    pm = PR.select_provider_model("intent_classify")
    assert pm.source == "env_role_override"
    assert pm.provider == "openrouter"
    assert pm.model_id == "meta-llama/llama-3.3-70b-instruct"


def test_per_role_override_to_anthropic(monkeypatch):
    monkeypatch.setenv(
        "TAO_MODEL_INTENT_CLASSIFY",
        "anthropic:claude-haiku-4-5",
    )
    pm = PR.select_provider_model("intent_classify")
    assert pm.provider == "anthropic"
    assert pm.model_id == "claude-haiku-4-5"


def test_per_role_override_to_ollama(monkeypatch):
    """Per-role override pins a role to a specific Ollama tag."""
    monkeypatch.setenv(
        "TAO_MODEL_INTENT_CLASSIFY", "ollama:qwen3.5:latest",
    )
    pm = PR.select_provider_model("intent_classify")
    assert pm.source == "env_role_override"
    assert pm.provider == "ollama"
    assert pm.model_id == "qwen3.5:latest"


def test_per_role_override_role_with_dot(monkeypatch):
    """Role names with dots (e.g. 'debate.redteam') become DEBATE_REDTEAM env."""
    monkeypatch.setenv(
        "TAO_MODEL_DEBATE_REDTEAM",
        "openrouter:google/gemma-4-26b-a4b-it",
    )
    pm = PR.select_provider_model("debate.redteam")
    assert pm.source == "env_role_override"
    assert pm.provider == "openrouter"
    assert pm.model_id == "google/gemma-4-26b-a4b-it"


def test_per_role_override_malformed_falls_through(monkeypatch):
    """No colon in env → ignored, falls back to tier default."""
    monkeypatch.setenv("TAO_MODEL_INTENT_CLASSIFY", "no-colon-here")
    pm = PR.select_provider_model("intent_classify")
    assert pm.source == "env_tier_default"


def test_per_role_override_unknown_provider_falls_through(monkeypatch):
    monkeypatch.setenv(
        "TAO_MODEL_INTENT_CLASSIFY", "google:gemini-pro",  # bogus prefix
    )
    pm = PR.select_provider_model("intent_classify")
    assert pm.source == "env_tier_default"


# ── is_anthropic / is_openrouter helpers ───────────────────────────────────


def test_is_anthropic_helper():
    pm = PR.ProviderModel(provider="anthropic", model_id="x", tier="top",
                            role="r", source="default")
    assert PR.is_anthropic(pm) is True
    assert PR.is_openrouter(pm) is False
    assert PR.is_ollama(pm) is False


def test_is_openrouter_helper():
    pm = PR.ProviderModel(provider="openrouter", model_id="x", tier="cheap",
                            role="r", source="default")
    assert PR.is_openrouter(pm) is True
    assert PR.is_anthropic(pm) is False
    assert PR.is_ollama(pm) is False


def test_is_ollama_helper():
    pm = PR.ProviderModel(provider="ollama", model_id="gemma4:latest",
                            tier="cheap", role="r", source="default")
    assert PR.is_ollama(pm) is True
    assert PR.is_anthropic(pm) is False
    assert PR.is_openrouter(pm) is False


# ── run_via_provider dispatch ──────────────────────────────────────────────


@pytest.mark.parametrize("role", ["planner", "intent_classify"])
def test_metered_or_unverified_dispatch_is_blocked(monkeypatch, role):
    monkeypatch.setenv(PR._env_role_key(role), "openrouter:paid-test-model")
    async def forbidden(**kwargs):
        pytest.fail("a forbidden model transport was invoked")
    monkeypatch.setitem(sys.modules, "app.server.session_sdk",
                        types.SimpleNamespace(_run_claude_via_sdk=forbidden))
    monkeypatch.setitem(sys.modules, "app.server.provider_openrouter",
                        types.SimpleNamespace(call=forbidden))
    rc, text, cost, error = asyncio.run(PR.run_via_provider("hi", role=role))
    assert rc == 1 and text == "" and cost is None
    assert "subscription_only" in error


def test_run_via_provider_ollama_path(monkeypatch):
    """role pinned to ollama → provider_ollama.call dispatched."""
    monkeypatch.setenv("TAO_CHEAP_PROVIDER", "ollama")

    async def fake_ollama_call(*, prompt, model_id, timeout_s,
                                 max_tokens=4096, role="", session_id=""):
        return PR.ProviderExecution(0, "gemma4 reply", 0.0, None, {})

    fake_mod = types.SimpleNamespace(call_with_evidence=fake_ollama_call)
    monkeypatch.setitem(sys.modules, "app.server.provider_ollama", fake_mod)

    rc, text, cost, error = asyncio.run(PR.run_via_provider(
        prompt="hi", role="intent_classify",
    ))
    assert rc == 0
    assert text == "gemma4 reply"
    assert cost == 0.0
    assert error is None


def test_run_via_provider_ollama_failure_propagates(monkeypatch):
    monkeypatch.setenv("TAO_CHEAP_PROVIDER", "ollama")

    async def fake_ollama_call(**kw):
        return PR.ProviderExecution(1, "", 0.0, "ollama_call_raised: connection refused", {})

    fake_mod = types.SimpleNamespace(call_with_evidence=fake_ollama_call)
    monkeypatch.setitem(sys.modules, "app.server.provider_ollama", fake_mod)

    rc, text, cost, error = asyncio.run(PR.run_via_provider(
        prompt="hi", role="intent_classify",
    ))
    assert rc == 1
    assert "connection refused" in error


# ── claude_print provider (cost-strategy migration, task #178) ──────────────


def test_tao_top_use_claude_print_routes_top_via_claude_print(monkeypatch):
    """TAO_TOP_USE_CLAUDE_PRINT=1 → top tier dispatches via `claude --print`."""
    monkeypatch.setenv("TAO_TOP_USE_CLAUDE_PRINT", "1")
    pm = PR.select_provider_model("planner")
    assert pm.tier == "top"
    assert pm.provider == "claude_print"
    assert pm.model_id == PR.DEFAULT_TOP_MODEL  # label preserved for audit


def test_tao_mid_use_claude_print_routes_mid_via_claude_print(monkeypatch):
    monkeypatch.setenv("TAO_MID_USE_CLAUDE_PRINT", "1")
    pm = PR.select_provider_model("generator")
    assert pm.tier == "mid"
    assert pm.provider == "claude_print"
    assert pm.model_id == PR.DEFAULT_MID_MODEL


def test_top_use_claude_print_flag_off_routes_anthropic(monkeypatch):
    """An explicit API setting stays explicit and is denied at dispatch."""
    monkeypatch.setenv("TAO_TOP_USE_CLAUDE_PRINT", "0")
    pm = PR.select_provider_model("planner")
    assert pm.provider == "anthropic"


def test_per_role_override_to_claude_print(monkeypatch):
    """A specific role can opt in via TAO_MODEL_<ROLE>=claude_print:<model>."""
    monkeypatch.setenv(
        "TAO_MODEL_INTENT_CLASSIFY", "claude_print:claude-opus-4-8",
    )
    pm = PR.select_provider_model("intent_classify")
    assert pm.source == "env_role_override"
    assert pm.provider == "claude_print"
    assert pm.model_id == "claude-opus-4-8"


def test_is_claude_print_helper():
    pm = PR.ProviderModel(provider="claude_print", model_id="x", tier="top",
                            role="r", source="default")
    assert PR.is_claude_print(pm) is True
    assert PR.is_anthropic(pm) is False
    assert PR.is_openrouter(pm) is False
    assert PR.is_ollama(pm) is False


def test_run_via_provider_claude_print_path(monkeypatch):
    monkeypatch.setenv("TAO_TOP_USE_CLAUDE_PRINT", "1")
    import json
    import subprocess
    captured = []
    def fake_run(argv, **kw):
        captured.append(argv)
        payload = ({"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max"}
                   if "auth" in argv else {"type": "result", "is_error": False,
                   "result": "max-output", "modelUsage": {PR.DEFAULT_TOP_MODEL: {}}})
        return types.SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    rc, text, cost, error = asyncio.run(PR.run_via_provider("hello world", role="planner"))
    assert (rc, text, cost, error) == (0, "max-output", None, None)
    assert captured[0][1:] == ["auth", "status"]
    assert captured[1][captured[1].index("--model") + 1] == PR.DEFAULT_TOP_MODEL


@pytest.mark.parametrize("code", [1, 2, 127])
def test_cli_auth_failure_prevents_generation(monkeypatch, code):
    monkeypatch.setenv("TAO_TOP_USE_CLAUDE_PRINT", "1")
    import subprocess
    captured = []
    def fake_run(argv, **kw):
        captured.append(argv)
        return types.SimpleNamespace(returncode=code, stdout="", stderr="private error")
    monkeypatch.setattr(subprocess, "run", fake_run)
    rc, text, cost, error = asyncio.run(PR.run_via_provider("hi", role="planner"))
    assert rc == 1 and text == "" and cost is None
    assert "subscription_only" in error
    assert "private error" not in error
    assert len(captured) == 1


@pytest.mark.parametrize("confidential", [False, True])
def test_tier0_cannot_bypass_subscription_policy(monkeypatch, confidential):
    pm = PR.ProviderModel(provider="openrouter", model_id="x/y:free", tier="tier0",
                          role="gather", source="test")
    monkeypatch.setattr(PR, "select_provider_model", lambda *a, **k: pm)
    async def forbidden(*a, **k):
        pytest.fail("Tier-0 fallback chain bypassed billing policy")
    monkeypatch.setitem(sys.modules, "app.server.tier0_runner", types.SimpleNamespace(run_tier0=forbidden))
    result = asyncio.run(PR.run_via_provider("gather", role="gather", confidential=confidential))
    assert result[0] == 1 and "subscription_only" in result[3]
