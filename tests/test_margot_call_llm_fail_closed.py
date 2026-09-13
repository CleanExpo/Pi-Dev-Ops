"""tests/test_margot_call_llm_fail_closed.py — RA-7490.

_call_llm used to catch any provider_router exception and invoke the
Anthropic SDK as orchestrator. That skipped lane selection, reservation,
and receipt accounting. These tests prove a router throw, a typed
policy/budget denial, and a router import failure all terminate without
touching the direct SDK.
"""
from __future__ import annotations

import asyncio
import builtins
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server import model_policy  # noqa: E402
from app.server import provider_router as PR  # noqa: E402
from app.server import session_sdk  # noqa: E402
from app.server.provider_margot_casual import RefusedModelError  # noqa: E402
from swarm import margot_bot  # noqa: E402


def _ban_direct_sdk(monkeypatch) -> list[object]:
    """Record any attempt to pick or call the direct Anthropic SDK."""
    hits: list[object] = []

    async def sdk(*args, **kwargs):
        hits.append(("sdk", args, kwargs))
        return 0, "SHOULD_NOT_RUN", 9.99

    def select(role: str, *args, **kwargs):
        hits.append(("select", role))
        return "opus"

    monkeypatch.setattr(session_sdk, "_run_claude_via_sdk", sdk)
    monkeypatch.setattr(model_policy, "select_model", select)
    return hits


def _call(**kwargs):
    return asyncio.run(margot_bot._call_llm(**kwargs))


def test_router_success_is_returned_and_never_hits_sdk(monkeypatch):
    hits = _ban_direct_sdk(monkeypatch)

    async def ok(**kwargs):
        return 0, "hello from router", 0.0, None

    monkeypatch.setattr(PR, "run_via_provider", ok)
    rc, text, cost, err = _call(prompt="hi", turn_id="t1", role="margot.casual")
    assert (rc, text, cost, err) == (0, "hello from router", 0.0, None)
    assert hits == []


def test_router_raise_never_hits_direct_sdk(monkeypatch):
    hits = _ban_direct_sdk(monkeypatch)

    async def boom(**kwargs):
        raise RuntimeError("lane reservation failed")

    monkeypatch.setattr(PR, "run_via_provider", boom)
    rc, text, cost, err = _call(prompt="hi", turn_id="t-raise")
    assert rc == 1 and text == "" and cost == 0.0
    assert err is not None and err.startswith("provider_router_raised:")
    assert "lane reservation failed" in err
    assert hits == []


def test_policy_raise_never_hits_direct_sdk(monkeypatch):
    hits = _ban_direct_sdk(monkeypatch)

    async def boom(**kwargs):
        raise RefusedModelError("anthropic:claude-opus-4 via pin")

    monkeypatch.setattr(PR, "run_via_provider", boom)
    rc, text, cost, err = _call(prompt="hi", role="margot.casual")
    assert rc == 1 and text == "" and cost == 0.0
    assert err is not None and err.startswith("provider_router_raised:")
    assert "claude-opus-4" in err
    assert hits == []


@pytest.mark.parametrize(
    "denial",
    (
        "margot_casual_refused: anthropic:claude-opus-4",
        "budget_denied: daily cap reached",
        "margot_casual_ladder_exhausted: openrouter:429",
    ),
)
def test_typed_policy_or_budget_denial_never_hits_direct_sdk(monkeypatch, denial):
    hits = _ban_direct_sdk(monkeypatch)

    async def denied(**kwargs):
        return 1, "", 0.0, denial

    monkeypatch.setattr(PR, "run_via_provider", denied)
    rc, text, cost, err = _call(prompt="hi", role="margot.synthesis")
    assert (rc, text, cost, err) == (1, "", 0.0, denial)
    assert hits == []


def test_router_import_failure_never_hits_direct_sdk(monkeypatch):
    hits = _ban_direct_sdk(monkeypatch)
    monkeypatch.delitem(sys.modules, "app.server.provider_router", raising=False)
    real_import = builtins.__import__

    def _blocked(name, *args, **kwargs):
        if name == "app.server.provider_router":
            raise ImportError("simulated missing router")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked)
    rc, text, cost, err = _call(prompt="hi")
    assert rc == 1 and text == "" and cost == 0.0
    assert err is not None and err.startswith("provider_router_unavailable:")
    assert "simulated missing router" in err
    assert hits == []


@pytest.fixture
def _hermetic_supabase(monkeypatch):
    from app.server import supabase_log

    monkeypatch.setattr(supabase_log, "select_margot_conversations",
                        lambda *a, **k: [])
    monkeypatch.setattr(supabase_log, "insert_margot_conversation",
                        lambda *a, **k: True)


def test_handle_turn_router_raise_is_terminal_and_never_hits_sdk(
    tmp_path, monkeypatch, _hermetic_supabase,
):
    hits = _ban_direct_sdk(monkeypatch)

    async def boom(**kwargs):
        raise RuntimeError("policy denied")

    monkeypatch.setattr(PR, "run_via_provider", boom)
    turn = asyncio.run(margot_bot.handle_turn(
        chat_id="7490", user_text="hi",
        repo_root=tmp_path, _send=False,
    ))
    assert turn.error and "provider_router_raised" in turn.error
    assert "unavailable" in turn.margot_text.lower()
    assert hits == []
