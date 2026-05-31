"""tests/test_cfo_provider.py — RA-1859 (A1-wire) provider smoke.

Covers:
1. Synthetic provider returns one RawMetrics per business in projects.json
2. Synthetic output is deterministic (same input → same output)
3. Burn multiple round-trips through compute_metrics within ±0.01x of hand-calc
4. Registry returns synthetic by default
5. Registry returns stripe_xero when env says so
6. stripe_xero falls back to synthetic per-business when STRIPE_API_KEY missing
7. _default_metrics_provider in cfo bot is non-empty under default env
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from swarm import cfo as _cfo
from swarm.bots import cfo as cfo_bot
from swarm.providers import select_provider


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clear_provider_env(monkeypatch):
    """Each test starts with a clean TAO_CFO_PROVIDER + STRIPE_API_KEY."""
    monkeypatch.delenv("TAO_CFO_PROVIDER", raising=False)
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)


def _expected_business_ids() -> list[str]:
    p = REPO_ROOT / ".harness/projects.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    return [proj["id"] for proj in data["projects"] if proj.get("id")]


# ── Synthetic provider ──────────────────────────────────────────────────────


def test_synthetic_returns_one_per_business():
    from swarm.providers.synthetic import synthetic_provider
    out = synthetic_provider()
    assert len(out) == len(_expected_business_ids())
    assert {m.business_id for m in out} == set(_expected_business_ids())


def test_synthetic_is_deterministic():
    from swarm.providers.synthetic import synthetic_provider
    a = synthetic_provider()
    b = synthetic_provider()
    assert [m.business_id for m in a] == [m.business_id for m in b]
    for ma, mb in zip(a, b):
        assert ma.mrr == mb.mrr
        assert ma.starting_mrr == mb.starting_mrr
        assert ma.churn_mrr == mb.churn_mrr


def test_synthetic_burn_multiple_matches_hand_calc():
    """compute_metrics(synthetic) burn_multiple == net_burn*12 / net_new_arr."""
    from swarm.providers.synthetic import synthetic_provider
    raws = synthetic_provider()
    assert raws, "expected at least one business"
    for raw in raws:
        m = _cfo.compute_metrics(raw)
        net_new_mrr = (raw.new_mrr + raw.expansion_mrr
                       - raw.contraction_mrr - raw.churn_mrr)
        net_new_arr = net_new_mrr * 12.0
        if net_new_arr <= 0:
            assert m.burn_multiple is None
            continue
        expected = (raw.monthly_burn * 12.0) / net_new_arr
        assert abs((m.burn_multiple or 0) - expected) < 0.01, (
            f"{raw.business_id}: bm {m.burn_multiple} vs expected {expected}"
        )


def test_synthetic_business_types_split():
    """prosumer ids stay prosumer; everyone else b2b."""
    from swarm.providers.synthetic import synthetic_provider
    out = synthetic_provider()
    by_id = {m.business_id: m.business_type for m in out}
    if "synthex" in by_id:
        assert by_id["synthex"] == "prosumer"
    if "restoreassist" in by_id:
        assert by_id["restoreassist"] == "b2b"


# ── Registry ────────────────────────────────────────────────────────────────


def test_registry_default_is_synthetic(monkeypatch):
    monkeypatch.delenv("TAO_CFO_PROVIDER", raising=False)
    fn = select_provider()
    assert fn.__name__ == "synthetic_provider"


def test_registry_synthetic_explicit(monkeypatch):
    monkeypatch.setenv("TAO_CFO_PROVIDER", "synthetic")
    fn = select_provider()
    assert fn.__name__ == "synthetic_provider"


def test_registry_stripe_xero_explicit(monkeypatch):
    monkeypatch.setenv("TAO_CFO_PROVIDER", "stripe_xero")
    fn = select_provider()
    assert fn.__name__ == "stripe_xero_provider"


def test_registry_unknown_falls_back_to_synthetic(monkeypatch):
    monkeypatch.setenv("TAO_CFO_PROVIDER", "nope-not-a-real-provider")
    fn = select_provider()
    assert fn.__name__ == "synthetic_provider"


# ── Stripe-Xero provider ────────────────────────────────────────────────────


def test_stripe_xero_no_key_falls_back_to_synthetic(monkeypatch):
    """Without STRIPE_API_KEY, stripe_xero degrades to all-synthetic."""
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    from swarm.providers.stripe_xero import stripe_xero_provider
    out = stripe_xero_provider()
    assert len(out) == len(_expected_business_ids())
    # Should match the synthetic output exactly (same seed math).
    from swarm.providers.synthetic import synthetic_provider
    expected = {m.business_id: m.mrr for m in synthetic_provider()}
    actual = {m.business_id: m.mrr for m in out}
    assert actual == expected


# ── Bot wire-up ─────────────────────────────────────────────────────────────


def test_bot_default_provider_is_non_empty(monkeypatch):
    """RA-1859 acceptance: _default_metrics_provider no longer returns []."""
    monkeypatch.delenv("TAO_CFO_PROVIDER", raising=False)
    out = cfo_bot._default_metrics_provider()
    assert len(out) > 0, "default provider returned empty — Wave 4.1b regression"
    assert all(m.mrr > 0 for m in out)


def test_bot_default_provider_handles_provider_failure(monkeypatch):
    """When the registry is broken, default returns [] not crash."""
    import swarm.providers
    orig = swarm.providers.select_provider

    def boom():
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(swarm.providers, "select_provider", lambda: boom)
    try:
        out = cfo_bot._default_metrics_provider()
        assert out == []
    finally:
        monkeypatch.setattr(swarm.providers, "select_provider", orig)
