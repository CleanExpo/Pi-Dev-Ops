"""COST LAW on the default model ladders (founder directive 18/09/2026).

Separate from test_model_router.py, which is over the 300-line file convention.
"""
from __future__ import annotations

import pytest

from swarm.model_router import Tier, get_client


# ============================================================
# COST LAW — default ladders (founder directive 18/09/2026)
# ============================================================

def _default_rungs(tier, monkeypatch):
    monkeypatch.delenv("TAO_OPENROUTER_ENFORCE", raising=False)
    return [(p.name, p._model) for p in get_client(tier)._ladder]


def _is_free(rung):
    kind, model = rung
    return kind == "openrouter" and model.endswith(":free")


@pytest.mark.parametrize("tier", list(Tier))
def test_every_default_ladder_ends_on_a_free_rung(tier, monkeypatch):
    """When every paid provider is down, the last fallback must cost $0."""
    rungs = _default_rungs(tier, monkeypatch)
    assert rungs, f"{tier} has an empty default ladder"
    assert _is_free(rungs[-1]), f"{tier} ends on a paid rung: {rungs[-1]}"


@pytest.mark.parametrize("tier", list(Tier))
def test_no_default_ladder_routes_to_ollama(tier, monkeypatch):
    """ollama was removed estate-wide on 29/08/2026."""
    assert all(kind != "ollama" for kind, _ in _default_rungs(tier, monkeypatch))


@pytest.mark.parametrize("tier", [Tier.REMEDIAL, Tier.LOCAL])
def test_cheap_tiers_are_free_on_every_rung(tier, monkeypatch):
    rungs = _default_rungs(tier, monkeypatch)
    assert all(_is_free(r) for r in rungs), rungs
