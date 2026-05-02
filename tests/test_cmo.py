"""tests/test_cmo.py — RA-1860 (A2) CMO/Growth engine + bot smoke.

Covers:
1. Synthetic marketing provider returns one per business in projects.json
2. Synthetic output is deterministic
3. compute_metrics: LTV:CAC + HHI + top-channel + attr_decay correct
4. detect_breaches: critical channel concentration fires
5. detect_breaches: low LTV:CAC fires warning
6. detect_breaches: high CPA fires warning
7. assemble_daily_brief contains expected scaffold
8. approve_adspend: <= ceiling auto-approves
9. approve_adspend: > ceiling + draft routes to pending
10. approve_adspend: > ceiling + no draft blocks
11. Registry: select_marketing_provider default is synthetic
12. Bot _default_marketing_provider non-empty under default env
13. Bot degrades to [] on provider crash
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import cmo as _cmo  # noqa: E402
from swarm.bots import cmo as cmo_bot  # noqa: E402
from swarm.providers import select_marketing_provider  # noqa: E402
from swarm.providers.synthetic_marketing import (  # noqa: E402
    synthetic_marketing_one,
    synthetic_marketing_provider,
)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("TAO_CMO_PROVIDER", raising=False)
    monkeypatch.delenv("TAO_CMO_ADSPEND_CEILING", raising=False)


def _expected_business_ids() -> list[str]:
    p = REPO_ROOT / ".harness/projects.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    return [proj["id"] for proj in data["projects"] if proj.get("id")]


# ── Synthetic provider ──────────────────────────────────────────────────────


def test_synthetic_marketing_one_per_business():
    out = synthetic_marketing_provider()
    assert len(out) == len(_expected_business_ids())
    assert {m.business_id for m in out} == set(_expected_business_ids())


def test_synthetic_marketing_deterministic():
    a = synthetic_marketing_provider()
    b = synthetic_marketing_provider()
    assert all(ma.mrr == mb.mrr for ma, mb in zip(a, b))
    for ma, mb in zip(a, b):
        chans_a = [(c.channel, c.spend_usd) for c in ma.channel_breakdown]
        chans_b = [(c.channel, c.spend_usd) for c in mb.channel_breakdown]
        assert chans_a == chans_b


# ── Engine compute_metrics ──────────────────────────────────────────────────


def test_compute_metrics_ltv_cac_hand_calc():
    raw = synthetic_marketing_one("restoreassist")
    m = _cmo.compute_metrics(raw)
    expected_ltv = (raw.avg_ltv_months * raw.arpu_monthly
                    * max(raw.gross_margin, 0.0))
    expected_cpa = raw.total_marketing_spend_usd / max(
        raw.total_customers_acquired, 1)
    expected_ratio = expected_ltv / expected_cpa if expected_cpa else None
    assert abs(m.ltv_usd - round(expected_ltv, 2)) < 0.01
    assert (m.blended_cpa_usd is None
            or abs(m.blended_cpa_usd - round(expected_cpa, 2)) < 0.01)
    if expected_ratio is not None and m.ltv_cac_ratio is not None:
        assert abs(m.ltv_cac_ratio - round(expected_ratio, 3)) < 0.05


def test_compute_metrics_hhi_and_top_channel():
    raw = _cmo.RawMarketingMetrics(
        business_id="bid", mrr=1000.0, avg_ltv_months=24, arpu_monthly=50,
        total_marketing_spend_usd=1000.0, total_customers_acquired=10,
        gross_margin=0.8,
        channel_breakdown=[
            _cmo.ChannelSpend("google-ads", 800.0, 8),
            _cmo.ChannelSpend("linkedin", 200.0, 2),
        ],
        attr_signal_count=2, attr_baseline_count=2,
    )
    m = _cmo.compute_metrics(raw)
    assert m.top_channel == "google-ads"
    assert m.top_channel_share == 0.8
    # HHI = 0.8^2 + 0.2^2 = 0.64 + 0.04 = 0.68
    assert abs(m.channel_concentration_hhi - 0.68) < 0.001
    assert m.attr_decay == 0.0


def test_compute_metrics_attr_decay():
    raw = _cmo.RawMarketingMetrics(
        business_id="bid", mrr=1000.0, avg_ltv_months=24, arpu_monthly=50,
        total_marketing_spend_usd=1000.0, total_customers_acquired=10,
        gross_margin=0.8, channel_breakdown=[],
        attr_signal_count=2, attr_baseline_count=10,  # 80% decay
    )
    m = _cmo.compute_metrics(raw)
    assert abs(m.attr_decay - 0.8) < 0.001


# ── Breach detection ────────────────────────────────────────────────────────


def test_detect_breaches_channel_concentration_critical():
    m = _cmo.MarketingMetrics(
        ts="x", business_id="bid", mrr=1000.0, blended_cpa_usd=50.0,
        ltv_usd=2000.0, ltv_cac_ratio=40.0,
        channel_concentration_hhi=0.85,
        top_channel="google-ads", top_channel_share=0.92,
        attr_decay=0.10, total_spend_usd=1000.0,
    )
    breaches = _cmo.detect_breaches(m)
    crit = [b for b in breaches if b.severity == "critical"]
    assert any(b.metric == "channel_concentration" for b in crit)


def test_detect_breaches_low_ltv_cac():
    m = _cmo.MarketingMetrics(
        ts="x", business_id="bid", mrr=1000.0, blended_cpa_usd=200.0,
        ltv_usd=400.0, ltv_cac_ratio=2.0,
        channel_concentration_hhi=0.30,
        top_channel="seo", top_channel_share=0.40,
        attr_decay=0.10, total_spend_usd=1000.0,
    )
    breaches = _cmo.detect_breaches(m)
    assert any(b.metric == "ltv_cac_ratio" and b.severity == "warning"
               for b in breaches)


def test_detect_breaches_high_cpa():
    m = _cmo.MarketingMetrics(
        ts="x", business_id="bid", mrr=1000.0, blended_cpa_usd=300.0,
        ltv_usd=2000.0, ltv_cac_ratio=6.7,
        channel_concentration_hhi=0.30,
        top_channel="seo", top_channel_share=0.40,
        attr_decay=0.10, total_spend_usd=1000.0,
    )
    breaches = _cmo.detect_breaches(m)
    assert any(b.metric == "blended_cpa" for b in breaches)


# ── Daily brief ─────────────────────────────────────────────────────────────


def test_assemble_daily_brief_renders():
    raws = synthetic_marketing_provider()
    snaps = [_cmo.compute_metrics(r) for r in raws]
    breaches: list[_cmo.MarketingBreach] = []
    for s in snaps:
        breaches.extend(_cmo.detect_breaches(s))
    brief = _cmo.assemble_daily_brief(snaps, breaches, pending_adspend_count=2)
    assert "📈 CMO daily" in brief
    assert "Per-business:" in brief
    assert "ad-spend approval" in brief


# ── Ad-spend approval ───────────────────────────────────────────────────────


def test_approve_adspend_under_ceiling_auto_approves():
    d = _cmo.approve_adspend(
        amount_usd_per_day=4500.0, channel="google-ads",
        business_id="bid", justification="hit Q2 NRR target",
    )
    assert d.status == "approved"
    assert d.draft_id is None


def test_approve_adspend_over_ceiling_with_draft_pends():
    captured = {}

    def fake_post_draft(**kwargs):
        captured.update(kwargs)
        return {"draft_id": "drft-cmo-001"}

    d = _cmo.approve_adspend(
        amount_usd_per_day=7500.0, channel="linkedin",
        business_id="bid", justification="enterprise pipeline build",
        post_draft=fake_post_draft, review_chat_id="review",
    )
    assert d.status == "pending"
    assert d.draft_id == "drft-cmo-001"
    assert "7,500.00" in captured["draft_text"]
    assert captured["drafted_by_role"] == "CMO"


def test_approve_adspend_over_ceiling_no_draft_blocks():
    d = _cmo.approve_adspend(
        amount_usd_per_day=7500.0, channel="meta",
        business_id="bid", justification="...",
    )
    assert d.status == "blocked"


# ── Registry + bot wire-up ──────────────────────────────────────────────────


def test_registry_marketing_default_is_synthetic(monkeypatch):
    monkeypatch.delenv("TAO_CMO_PROVIDER", raising=False)
    fn = select_marketing_provider()
    assert fn.__name__ == "synthetic_marketing_provider"


def test_bot_default_marketing_provider_non_empty(monkeypatch):
    monkeypatch.delenv("TAO_CMO_PROVIDER", raising=False)
    out = cmo_bot._default_marketing_provider()
    assert len(out) > 0
    assert all(m.mrr > 0 for m in out)


def test_bot_default_marketing_provider_handles_crash(monkeypatch):
    import swarm.providers
    orig = swarm.providers.select_marketing_provider
    monkeypatch.setattr(
        swarm.providers, "select_marketing_provider",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    try:
        out = cmo_bot._default_marketing_provider()
        assert out == []
    finally:
        monkeypatch.setattr(swarm.providers, "select_marketing_provider", orig)
