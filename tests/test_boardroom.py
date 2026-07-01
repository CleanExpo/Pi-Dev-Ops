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


@pytest.mark.asyncio
async def test_boardroom_survives_panellist_failure(monkeypatch):
    from app.server.spec_pipeline import boardroom as br

    calls = {"n": 0}

    async def fake_panellist(model_id, prompt, system, max_tokens):
        calls["n"] += 1
        if calls["n"] == 1:
            from app.server.spec_pipeline.boardroom import PanellistOutcome
            return PanellistOutcome(model_id=model_id, response=None, error="down")
        from app.server.spec_pipeline.boardroom import PanellistOutcome
        return PanellistOutcome(model_id=model_id, response="Approve small reversible scope.")

    async def fake_complete(**_kwargs):
        return (
            'Ship the smallest slice.\n{"decision":"APPROVE_BUILD","confidence":0.9}',
            0.01,
        )

    monkeypatch.setattr(br, "_call_panellist", fake_panellist)
    monkeypatch.setattr(br, "complete", fake_complete)

    result = await boardroom_query(
        prompt="Should we add a dry-run panel?",
        panel=(
            {"provider": "openrouter", "model_id": "a"},
            {"provider": "openrouter", "model_id": "b"},
        ),
    )
    assert result.decision == "APPROVE_BUILD"
    assert len(result.panel) == 2
