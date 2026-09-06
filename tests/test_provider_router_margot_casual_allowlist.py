"""tests/test_provider_router_margot_casual_allowlist.py — RA-7434, the guard.

The independent review of 1ab35716 raised two P1 findings against the refusal
list. It was a DENYLIST of five markers, so any paid model whose name contained
none of them reached a role the founder ruling puts on $0 only, and the ladder
dispatched every non-ollama provider to OpenRouter. These tests were watched
failing on both defects before either was fixed: 5 failed, 21 passed.

Split from test_provider_router_margot_casual_ladder.py, which reached 313
lines against the repo's 300-line convention once they were added.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server import provider_margot_casual as MC  # noqa: E402
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


# ── The refusal list must be an ALLOWLIST ───────────────────────────────────
#
# Raised as two P1 findings by the independent review of 1ab35716. The refusal
# list was a DENYLIST of five markers, so every paid model whose name contains
# none of them reached this role: `openrouter:openai/gpt-4o` is a paid model
# and matched nothing. A $0-only role guarded by a list of forbidden names is
# only as good as the list. These cases are the ones a denylist misses.


@pytest.mark.parametrize("spec", [
    "openrouter:openai/gpt-4o",              # paid, matches no refused marker
    "openrouter:google/gemini-1.5-pro",      # paid, matches no refused marker
    "openrouter:meta-llama/llama-3.3-70b-instruct",
    "openrouter:z-ai/glm-4.7",               # near-miss on a ladder entry
    "claude_print:gpt-x",                    # provider the ladder cannot dispatch
])
def test_paid_override_outside_the_ladder_fails_closed(monkeypatch, spec):
    """A model that is not on the ladder, not ollama and not ':free' is refused."""
    monkeypatch.setenv("TAO_MODEL_MARGOT_CASUAL", spec)
    with pytest.raises(MC.RefusedModelError) as exc_info:
        PR.select_provider_model("margot.casual")
    msg = str(exc_info.value)
    assert "RA-7434" in msg
    assert spec.split(":", 1)[1] in msg


@pytest.mark.parametrize("spec", [
    "openrouter:google/gemma-4-26b-a4b-it:free",   # ladder step 2
    "openrouter:z-ai/glm-4.7-flash",               # ladder step 3
    "openrouter:nvidia/nemotron-3-super-120b-a12b:free",
    "ollama:qwen3.5:latest",                       # local, costs nothing
])
def test_free_override_is_still_honoured(monkeypatch, spec):
    """The allowlist must not refuse the things the ruling actually permits.

    Without this leg the previous test passes on a checker that refuses
    everything, which would prove nothing about the allowlist.
    """
    monkeypatch.setenv("TAO_MODEL_MARGOT_CASUAL", spec)
    pm = PR.select_provider_model("margot.casual")
    assert pm.source == "env:TAO_MODEL_MARGOT_CASUAL"
    assert f"{pm.provider}:{pm.model_id}" == spec


def test_run_via_provider_never_dispatches_an_unsupported_provider(monkeypatch):
    """_call_ladder_step sends everything non-ollama to OpenRouter.

    The second P1: a claude_print or anthropic override that slipped the refusal
    list would have been executed by provider_openrouter under a model id that
    module never issued. The guard above refuses it first; this asserts the
    dispatch itself also refuses rather than mis-routing.
    """
    import asyncio  # noqa: PLC0415
    calls: list = []

    def _record(name):
        import types  # noqa: PLC0415

        async def call(*, prompt, model_id, timeout_s=120, role="", session_id="", **kw):
            calls.append((name, model_id))
            return 0, "should not happen", 0.0, None

        return types.SimpleNamespace(call=call)

    monkeypatch.setitem(sys.modules, "app.server.provider_openrouter", _record("openrouter"))
    monkeypatch.setitem(sys.modules, "app.server.provider_ollama", _record("ollama"))
    rc, text, cost, err = asyncio.run(
        MC._call_ladder_step("claude_print", "gpt-x", "hi", timeout_s=5, session_id=""))
    assert rc == 1
    assert calls == [], "an unsupported provider must not reach any provider module"
    assert "claude_print" in (err or "")
