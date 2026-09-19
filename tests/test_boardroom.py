"""Tests for boardroom Jaccard + query survival."""
from __future__ import annotations

import pytest

from app.server.spec_pipeline.boardroom import (
    boardroom_query,
    compute_min_pairwise_jaccard,
    jaccard,
    tokenise,
)


def test_jaccard_identical():
    a = tokenise("build a small reversible api endpoint")
    assert jaccard(a, a) == 1.0


def test_compute_min_pairwise_single():
    assert compute_min_pairwise_jaccard(["only one"]) == 1.0


def test_compute_min_pairwise_divergent():
    a = "kubernetes mesh service discovery autoscaling"
    b = "marketing email sequence copywriting brand voice"
    assert compute_min_pairwise_jaccard([a, b]) < 0.25


@pytest.mark.parametrize("answer", [
    "Do not APPROVE_BUILD", "APPROVE BUILD", '{"decision":"APPROVE_BUILD"}',
    '{"decision":"APPROVE_BUILD","confidence":true}',
    '{"decision":"APPROVE_BUILD","confidence":NaN}',
    '{"decision":"APPROVE_BUILD","confidence":Infinity}',
    '{"decision":"APPROVE_BUILD","confidence":-0.1}',
    '{"decision":"APPROVE_BUILD","confidence":1.1}',
    '{"decision":"APPROVE_BUILD","confidence":"0.9"}',
    '{"decision":"APPROVE_BUILD","confidence":' + "9" * 400 + '}',
    '{"decision":"not APPROVE_BUILD","confidence":0.9}',
])
def test_boardroom_malformed_decision_cannot_approve(answer):
    from app.server.spec_pipeline.boardroom import _parse_decision
    assert _parse_decision(answer) == ("REJECT", 0.0)


@pytest.mark.parametrize("decision", ["APPROVE_BUILD", "REJECT", "REDUCE_SCOPE"])
def test_boardroom_preserves_valid_structured_decisions(decision):
    import json
    from app.server.spec_pipeline.boardroom import _parse_decision
    assert _parse_decision(json.dumps({"decision": decision, "confidence": 0.9})) == (decision, 0.9)


def _execution(provider, model, text="Approve small reversible scope."):
    from app.server.provider_router import ProviderExecution
    return ProviderExecution(0, text, None, None, {
        "provider": provider, "actual_model": model, "requested_model": model,
        "model_verified": True, "auth_verified": True, "source": "test_transport",
    })


@pytest.mark.asyncio
@pytest.mark.parametrize("problem", ["missing", "same_vendor", "same_model", "unverified"])
async def test_boardroom_blocks_without_independent_verified_panel(monkeypatch, problem):
    from app.server import provider_router
    from unittest.mock import AsyncMock

    first = _execution("anthropic", "claude-test")
    second = _execution("openai", "gpt-test")
    if problem == "missing":
        second.rc, second.error = 1, "subscription_only: unavailable"
    elif problem == "same_vendor":
        second.provenance["provider"] = "anthropic"
    elif problem == "same_model":
        second.provenance["actual_model"] = "claude-test"
    else:
        second.provenance["model_verified"] = False
    route = AsyncMock(side_effect=[first, second])
    monkeypatch.setattr(provider_router, "run_via_provider_with_evidence", route)
    with pytest.raises(RuntimeError, match="independent"):
        await boardroom_query(prompt="Should we add a dry-run panel?")
    assert route.await_count == 2


@pytest.mark.asyncio
async def test_boardroom_uses_observed_panel_and_synthesis_identities(monkeypatch):
    from app.server import provider_router
    from unittest.mock import AsyncMock

    route = AsyncMock(side_effect=[
        _execution("anthropic", "claude-served"),
        _execution("openai", "gpt-served"),
        _execution("anthropic", "synthesis-served", '{"decision":"APPROVE_BUILD","confidence":0.9}'),
    ])
    monkeypatch.setattr(provider_router, "run_via_provider_with_evidence", route)
    result = await boardroom_query(prompt="Should we add a dry-run panel?")
    assert result.decision == "APPROVE_BUILD"
    assert [seat.model_id for seat in result.panel] == ["claude-served", "gpt-served"]
    assert result.synthesised_by == "synthesis-served"
    assert result.panel[1].provenance["provider"] == "openai"
    roles = [call.kwargs["role"] for call in route.call_args_list]
    assert roles == ["boardroom_panellist_primary", "boardroom_panellist_secondary", "boardroom_synthesis"]


@pytest.mark.asyncio
async def test_boardroom_explicit_paid_panel_cannot_silently_reroute(monkeypatch):
    from app.server import provider_router
    from unittest.mock import AsyncMock

    route = AsyncMock(return_value=_execution("anthropic", "claude-served"))
    monkeypatch.setattr(provider_router, "run_via_provider_with_evidence", route)
    with pytest.raises(RuntimeError, match="independent"):
        await boardroom_query(prompt="task", panel=(
            {"provider": "openrouter", "model_id": "deepseek/requested"},
            {"provider": "openrouter", "model_id": "anthropic/requested"},
        ))
    route.assert_not_called()
