"""tests/test_provider_router_margot_casual_run.py — RA-7434, call side.

Split out of test_provider_router_margot_casual_ladder.py, which reached 323
lines against the repo's 300-line convention. That file now covers RESOLUTION
(which model the ladder picks); this one covers the CALL (what run_via_provider
does with the pick, and that a refusal comes back as a tuple rather than a
raise). The shared env-scrubbing fixture is duplicated rather than moved to a
conftest: it monkeypatches provider_router internals, and a conftest would
apply it to every test in tests/.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server import provider_router as PR  # noqa: E402


_ROUTER_ENV = (
    "TAO_TOP_MODEL", "TAO_MID_MODEL",
    "TAO_CHEAP_MODEL", "TAO_CHEAP_PROVIDER",
    "TAO_CHEAP_LOCAL_MODEL", "TAO_CHEAP_REMOTE_MODEL",
    "TAO_TOP_USE_CLAUDE_PRINT", "TAO_MID_USE_CLAUDE_PRINT",
    "OLLAMA_BASE_URL", "MARGOT_OLLAMA_BASE_URL",
)


def _ollama_module():
    mod = sys.modules.get("app.server.provider_ollama")
    if mod is None:
        from app.server import provider_ollama as mod  # noqa: PLC0415
    return mod


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in _ROUTER_ENV:
        monkeypatch.delenv(k, raising=False)
    for k in list(os.environ):
        if k.startswith("TAO_MODEL_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(_ollama_module(), "is_reachable", lambda **kw: False)
    # The downgrade recorder appends to a violations file; keep the test inert.
    monkeypatch.setattr(PR, "_record_tier_downgrade", lambda *a, **kw: None)


# ── run_via_provider: refusal is an error tuple, never a raise ──────────────
#
# RA-7490: _call_llm fail-closes on a router raise and never opens the
# Anthropic SDK. The refusal must still come back as (rc=1, error) so the
# bot reports "unavailable" and so a future fallback cannot be fed a raise.


def _fake_provider(name: str, calls: list, responses: list):
    import types  # noqa: PLC0415

    async def call(*, prompt, model_id, timeout_s=120, role="", session_id="", **kw):
        calls.append((name, model_id))
        return responses.pop(0)

    return types.SimpleNamespace(call=call)


@pytest.fixture
def cost_log(monkeypatch, tmp_path):
    monkeypatch.setenv("BUDGET_TRACKER_LOG_PATH", str(tmp_path / "llm-cost.jsonl"))
    return tmp_path / "llm-cost.jsonl"


def test_run_via_provider_refusal_returns_error_tuple(monkeypatch, cost_log):
    import asyncio  # noqa: PLC0415
    monkeypatch.setenv("TAO_MODEL_MARGOT_CASUAL", "openrouter:~moonshotai/kimi-latest")
    calls: list = []
    monkeypatch.setitem(sys.modules, "app.server.provider_openrouter", _fake_provider("openrouter", calls, []))
    monkeypatch.setitem(sys.modules, "app.server.session_sdk", _fake_provider("anthropic", calls, []))
    rc, text, cost, err = asyncio.run(PR.run_via_provider("hi", role="margot.casual"))
    assert rc == 1 and text == "" and cost == 0.0
    assert err.startswith("margot_casual_refused:")
    assert "kimi" in err
    assert calls == [], "a refused model must never be called, nor any fallback"
    assert not cost_log.exists()


def test_run_via_provider_walks_the_ladder_on_failure(monkeypatch, cost_log, isolated_policy):
    import asyncio  # noqa: PLC0415
    calls: list = []
    monkeypatch.setitem(sys.modules, "app.server.provider_ollama", _fake_provider("ollama", calls, []))
    monkeypatch.setitem(sys.modules, "app.server.provider_openrouter", _fake_provider(
        "openrouter", calls, [(1, "", 0.0, "openrouter_http_429: free pool"), (0, "hello", 0.0, None)]))
    rc, text, cost, err = asyncio.run(PR.run_via_provider("hi", role="margot.casual"))
    assert (rc, text, cost, err) == (0, "hello", 0.0, None)
    assert calls == [
        ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
        ("openrouter", "minimax/minimax-m3.1-flash:free"),
    ]
    row = json.loads(cost_log.read_text().splitlines()[-1])
    assert (row["provider"], row["role"], row["model"], row["cost_usd"]) == (
        "openrouter", "margot.casual", "minimax/minimax-m3.1-flash:free", 0.0)


def test_run_via_provider_ladder_exhausted_is_an_error_not_a_paid_fallback(monkeypatch, cost_log, isolated_policy):
    import asyncio  # noqa: PLC0415
    calls: list = []
    monkeypatch.setitem(sys.modules, "app.server.provider_openrouter", _fake_provider(
        "openrouter", calls, [(1, "", 0.0, "openrouter_http_429"), (1, "", 0.0, "openrouter_http_502")]))
    monkeypatch.setitem(sys.modules, "app.server.session_sdk", _fake_provider("anthropic", calls, []))
    rc, text, cost, err = asyncio.run(PR.run_via_provider("hi", role="margot.casual"))
    assert rc == 1
    assert err.startswith("margot_casual_ladder_exhausted:")
    assert calls == [
        ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
        ("openrouter", "minimax/minimax-m3.1-flash:free"),
    ], "two free steps, then an error: no third step and no paid fallback"


def test_run_via_provider_override_is_a_single_attempt(monkeypatch, cost_log, isolated_policy):
    import asyncio  # noqa: PLC0415
    monkeypatch.setenv("TAO_MODEL_MARGOT_CASUAL", "openrouter:nvidia/nemotron-3-super-120b-a12b:free")
    calls: list = []
    monkeypatch.setitem(sys.modules, "app.server.provider_openrouter", _fake_provider(
        "openrouter", calls, [(1, "", 0.0, "openrouter_http_429")]))
    rc, _text, _cost, err = asyncio.run(PR.run_via_provider("hi", role="margot.casual"))
    assert rc == 1
    assert calls == [("openrouter", "nvidia/nemotron-3-super-120b-a12b:free")]


@pytest.fixture
def isolated_policy(monkeypatch):
    """Isolate historical ladder control flow from the production transport policy."""
    from app.server import provider_policy
    monkeypatch.setattr(provider_policy, "require_transport", lambda *a, **kw: {})


def test_ladder_passes_the_real_policy_and_reaches_openrouter(monkeypatch, cost_log):
    """No isolated_policy here: the production transport policy must admit the
    margot.casual ':free' ladder, or every Telegram turn fails closed."""
    import asyncio  # noqa: PLC0415
    calls: list = []
    monkeypatch.setitem(sys.modules, "app.server.provider_openrouter", _fake_provider(
        "openrouter", calls, [(0, "hello", 0.0, None)]))
    rc, text, _cost, err = asyncio.run(PR.run_via_provider("hi", role="margot.casual"))
    assert (rc, text, err) == (0, "hello", None)
    assert calls == [("openrouter", "nvidia/nemotron-3-super-120b-a12b:free")]


@pytest.mark.parametrize("model", [
    "z-ai/glm-4.7-flash",
    "minimax/minimax-m3.1-flash",
    "nvidia/nemotron-3-super-120b-a12b:free:x",
])
def test_real_policy_blocks_a_paid_id_at_dispatch(monkeypatch, model):
    """Second line of defence: even if a non-':free' id reached the dispatch
    step, the transport policy refuses it before the adapter is called."""
    import asyncio  # noqa: PLC0415
    from app.server import provider_margot_casual as MC  # noqa: PLC0415
    calls: list = []
    monkeypatch.setitem(sys.modules, "app.server.provider_openrouter",
                        _fake_provider("openrouter", calls, []))
    rc, _, _, error = asyncio.run(
        MC._call_ladder_step("openrouter", model, "hi", timeout_s=5, session_id=""))
    assert rc == 1
    assert "subscription_only" in error
    assert calls == []
