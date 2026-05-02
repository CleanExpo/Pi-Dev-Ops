"""tests/test_google_ads.py — Google Ads CMO provider smoke."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm.providers import google_ads as GA  # noqa: E402
from swarm.providers import select_marketing_provider  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for k in [
        "TAO_CMO_PROVIDER", "GOOGLE_ADS_OAUTH_TOKEN",
        "GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
    ]:
        monkeypatch.delenv(k, raising=False)
    # Clear per-business customer envs from any prior test
    for k in list(__import__("os").environ.keys()):
        if k.startswith("GOOGLE_ADS_CUSTOMER_"):
            monkeypatch.delenv(k, raising=False)


# ── Registry routes to google_ads ───────────────────────────────────────────


def test_registry_google_ads_selectable(monkeypatch):
    monkeypatch.setenv("TAO_CMO_PROVIDER", "google_ads")
    fn = select_marketing_provider()
    assert fn.__name__ == "google_ads_provider"


def test_registry_ad_platforms_alias_routes_to_google_ads(monkeypatch):
    monkeypatch.setenv("TAO_CMO_PROVIDER", "ad_platforms")
    fn = select_marketing_provider()
    assert fn.__name__ == "google_ads_provider"


# ── google_ads_provider falls back without creds ────────────────────────────


def test_provider_no_creds_emits_all_synthetic(monkeypatch):
    """Without OAUTH or DEVELOPER token, every business is synthetic."""
    out = GA.google_ads_provider()
    from swarm.providers.synthetic_marketing import synthetic_marketing_provider
    expected = {m.business_id: m.mrr for m in synthetic_marketing_provider()}
    actual = {m.business_id: m.mrr for m in out}
    assert actual == expected


# ── _query_customer_spend parses searchStream output ────────────────────────


def test_query_customer_spend_sums_micros(monkeypatch):
    fake_response = [{
        "results": [
            {"metrics": {"costMicros": "1500000",  "conversions": "3.0"}},
            {"metrics": {"costMicros": "2000000",  "conversions": "5.5"}},
        ]
    }]
    monkeypatch.setattr(GA, "_ads_post",
                         lambda path, **kw: fake_response)

    out = GA._query_customer_spend(
        customer_id="123-456-7890",
        oauth_token="o", developer_token="d", login_customer_id="9990",
    )
    # Spend: (1,500,000 + 2,000,000) micros = 3.5 USD
    # Conversions: round(3.0 + 5.5) = 8 (banker's rounding on .5)
    assert out == (3.50, 8)


def test_query_customer_spend_handles_dict_response(monkeypatch):
    """Some Google Ads stream responses come back as a single dict."""
    monkeypatch.setattr(GA, "_ads_post",
                         lambda path, **kw: {
                             "results": [
                                 {"metrics": {"costMicros": "500000",
                                              "conversions": "1"}}
                             ]
                         })
    out = GA._query_customer_spend(
        customer_id="x", oauth_token="o",
        developer_token="d", login_customer_id=None,
    )
    assert out == (0.50, 1)


def test_query_customer_spend_handles_empty_results(monkeypatch):
    monkeypatch.setattr(GA, "_ads_post",
                         lambda path, **kw: [{"results": []}])
    out = GA._query_customer_spend(
        customer_id="x", oauth_token="o",
        developer_token="d", login_customer_id=None,
    )
    assert out == (0.0, 0)


def test_query_customer_spend_swallows_http_error(monkeypatch):
    def boom(path, **kw):
        raise RuntimeError("ads down")
    monkeypatch.setattr(GA, "_ads_post", boom)
    out = GA._query_customer_spend(
        customer_id="x", oauth_token="o",
        developer_token="d", login_customer_id=None,
    )
    assert out is None


def test_query_customer_spend_skips_unparseable(monkeypatch):
    """Non-numeric costMicros / conversions don't crash the sum."""
    fake_response = [{
        "results": [
            {"metrics": {"costMicros": "not-a-number",
                         "conversions": "x"}},
            {"metrics": {"costMicros": "1000000",
                         "conversions": "2"}},
        ]
    }]
    monkeypatch.setattr(GA, "_ads_post",
                         lambda path, **kw: fake_response)
    out = GA._query_customer_spend(
        customer_id="x", oauth_token="o",
        developer_token="d", login_customer_id=None,
    )
    assert out == (1.0, 2)


# ── _real_for_business overlays google-ads channel ──────────────────────────


def test_real_for_business_overlays_google_ads_channel(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_CUSTOMER_RESTOREASSIST", "1234567890")
    monkeypatch.setattr(GA, "_query_customer_spend",
                         lambda **kw: (4242.42, 17))

    out = GA._real_for_business(
        "restoreassist",
        oauth_token="o", developer_token="d", login_customer_id=None,
    )
    assert out is not None
    google_row = next(
        (c for c in out.channel_breakdown if c.channel == "google-ads"),
        None,
    )
    assert google_row is not None
    assert google_row.spend_usd == 4242.42
    assert google_row.customers_acquired == 17
    # Total spend reflects the overlay
    assert out.total_marketing_spend_usd == round(
        sum(c.spend_usd for c in out.channel_breakdown), 2,
    )


def test_real_for_business_skips_when_customer_id_missing(monkeypatch):
    """Without GOOGLE_ADS_CUSTOMER_<BID>, returns None so caller falls back."""
    out = GA._real_for_business(
        "restoreassist",
        oauth_token="o", developer_token="d", login_customer_id=None,
    )
    assert out is None


def test_real_for_business_appends_google_when_not_in_synthetic_mix(monkeypatch):
    """If a business's synthetic mix happened to omit google-ads, the real
    spend is appended so it surfaces in the brief."""
    monkeypatch.setenv("GOOGLE_ADS_CUSTOMER_BID", "1234567890")
    monkeypatch.setattr(GA, "_query_customer_spend",
                         lambda **kw: (100.0, 1))

    # Patch synthetic_marketing_one to return a fixture without google-ads
    from swarm.cmo import ChannelSpend, RawMarketingMetrics

    def fake_synth_one(bid):
        return RawMarketingMetrics(
            business_id=bid, mrr=1000.0,
            avg_ltv_months=12, arpu_monthly=50,
            total_marketing_spend_usd=200.0,
            total_customers_acquired=4, gross_margin=0.8,
            channel_breakdown=[
                ChannelSpend("linkedin", 200.0, 4),
            ],
            attr_signal_count=1, attr_baseline_count=1,
        )

    monkeypatch.setattr(GA, "synthetic_marketing_one", fake_synth_one)

    out = GA._real_for_business(
        "bid",
        oauth_token="o", developer_token="d", login_customer_id=None,
    )
    assert out is not None
    channels = {c.channel for c in out.channel_breakdown}
    assert "google-ads" in channels
    assert "linkedin" in channels


# ── google_ads_provider end-to-end with mock ────────────────────────────────


def test_provider_with_creds_calls_real_path(monkeypatch):
    """With creds + a customer ID for one business, that business gets the
    real-data overlay; others remain synthetic."""
    monkeypatch.setenv("GOOGLE_ADS_OAUTH_TOKEN", "tok")
    monkeypatch.setenv("GOOGLE_ADS_DEVELOPER_TOKEN", "dev")
    monkeypatch.setenv("GOOGLE_ADS_CUSTOMER_RESTOREASSIST", "111")

    monkeypatch.setattr(GA, "_query_customer_spend",
                         lambda **kw: (999.99, 7))

    out = GA.google_ads_provider()
    by_bid = {m.business_id: m for m in out}
    assert "restoreassist" in by_bid
    google_row = next(
        (c for c in by_bid["restoreassist"].channel_breakdown
         if c.channel == "google-ads"),
        None,
    )
    assert google_row is not None
    assert google_row.spend_usd == 999.99
    assert google_row.customers_acquired == 7

    # A business without a customer ID stays purely synthetic
    other_bid = next(b for b in by_bid if b != "restoreassist")
    from swarm.providers.synthetic_marketing import synthetic_marketing_one
    expected = synthetic_marketing_one(other_bid)
    assert by_bid[other_bid].mrr == expected.mrr
