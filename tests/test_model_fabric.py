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


def test_listed_role_enabled_explicitly(monkeypatch):
    monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
    monkeypatch.setenv("OMNIROUTE_ROLES", "planner")
    assert MF.role_allowed("planner") is True
    assert MF.role_allowed("generator") is False


def test_default_roles_are_empty(monkeypatch):
    monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
    monkeypatch.delenv("OMNIROUTE_ROLES", raising=False)
    assert MF.allowed_roles() == set()


def test_margot_casual_is_never_routed_even_when_listed(monkeypatch):
    """Founder ruling 21/10/2026: margot.casual runs only on its ':free' ladder.
    The Dockerfile still sets OMNIROUTE_ROLES=margot.casual and
    OMNIROUTE_STRENGTHEN_MARGOT=smart; neither may reach a paid model."""
    monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
    monkeypatch.setenv("OMNIROUTE_ROLES", "margot.casual,planner")
    monkeypatch.setenv("OMNIROUTE_STRENGTHEN_MARGOT", "always")
    assert MF.role_allowed("margot.casual") is False
    assert "margot.casual" not in MF.allowed_roles()
    monkeypatch.setattr(MF, "_get_json", lambda *a, **kw: (False, "offline"))
    assert "margot.casual" not in MF.status_snapshot()["allowed_roles"]

    def no_call(**kw):
        raise AssertionError("margot.casual must not reach the fabric")

    monkeypatch.setattr(MF, "_chat_once", no_call)
    rc, text, _cost, error = MF.complete(prompt="fix the production issue", role="margot.casual")
    assert (rc, text, error) == (1, "", "omniroute_role_not_enabled")


def test_openrouter_adapter_never_hands_margot_casual_to_the_fabric(monkeypatch):
    """The only caller of the fabric is provider_openrouter._try_model_fabric."""
    import asyncio  # noqa: PLC0415
    from app.server import provider_openrouter  # noqa: PLC0415

    monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
    monkeypatch.setenv("OMNIROUTE_ROLES", "margot.casual")
    reached: list = []
    # Record rather than raise: _try_model_fabric swallows exceptions, so a
    # raising fake would pass even when the fabric IS reached.
    monkeypatch.setattr(MF, "complete", lambda **kw: reached.append(kw) or (0, "paid", 0.0, None))
    assert asyncio.run(provider_openrouter._try_model_fabric(
        "hi", "margot.casual", "", 5, 64)) is None
    assert reached == []


def test_default_founder_ladder_blocks_ollama_and_gemma(monkeypatch):
    monkeypatch.delenv("OMNIROUTE_MODELS_FOUNDER_CHAT", raising=False)
    models = MF.models_for_lane("founder-chat")
    assert models
    assert all("ollama" not in model.lower() for model in models)
    assert all("gemma" not in model.lower() for model in models)


def test_env_ladder_filters_banned_models(monkeypatch):
    monkeypatch.setenv(
        "OMNIROUTE_MODELS_FOUNDER_CHAT",
        "ollama:bad,openrouter/nvidia/nemotron-3-super-120b-a12b:free,"
        "google/gemma-4",
    )
    assert MF.models_for_lane("founder-chat") == [
        "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
    ]


def test_ladder_falls_back_for_a_listed_role(monkeypatch):
    monkeypatch.setenv("OMNIROUTE_ENABLED", "1")
    monkeypatch.setenv("OMNIROUTE_ROLES", "planner")
    monkeypatch.setenv(
        "OMNIROUTE_MODELS_INTERNAL_WORK",
        "openrouter/free-one,openrouter/cheap-two",
    )
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)

    calls: list[str] = []

    def fake_chat_once(*, prompt, model, session_id, timeout_s, max_tokens):
        calls.append(model)
        if model == "openrouter/free-one":
            return False, "", model, "openrouter", 10, "rate_limited"
        if model == "openrouter/cheap-two":
            return True, "draft answer", model, "openrouter", 20, None
        raise AssertionError(model)

    monkeypatch.setattr(MF, "_chat_once", fake_chat_once)

    rc, text, cost, error = MF.complete(
        prompt="Please fix and finalise the production issue",
        role="planner",
        session_id="test",
    )
    assert (rc, text, cost, error) == (0, "draft answer", 0.0, None)
    assert calls == ["openrouter/free-one", "openrouter/cheap-two"]


def test_banned_strength_model_is_disabled(monkeypatch):
    monkeypatch.setenv("OMNIROUTE_MODEL_STRENGTHEN", "google/gemma-4")
    assert MF.strength_model() == ""
