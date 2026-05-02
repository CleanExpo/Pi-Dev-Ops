"""tests/test_zendesk_intercom.py — Zendesk + Intercom CS connector smoke."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm.providers import zendesk as ZD  # noqa: E402
from swarm.providers import select_cs_provider  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for k in [
        "TAO_CS_PROVIDER", "ZENDESK_SUBDOMAIN", "ZENDESK_EMAIL",
        "ZENDESK_API_TOKEN", "INTERCOM_ACCESS_TOKEN",
    ]:
        monkeypatch.delenv(k, raising=False)
    for k in list(os.environ.keys()):
        if k.startswith(("ZENDESK_BRAND_", "INTERCOM_BRAND_")):
            monkeypatch.delenv(k, raising=False)


# ── Registry routing ────────────────────────────────────────────────────────


def test_registry_zendesk_selectable(monkeypatch):
    monkeypatch.setenv("TAO_CS_PROVIDER", "zendesk")
    assert select_cs_provider().__name__ == "zendesk_provider"


def test_registry_intercom_selectable(monkeypatch):
    monkeypatch.setenv("TAO_CS_PROVIDER", "intercom")
    assert select_cs_provider().__name__ == "intercom_provider"


def test_registry_unknown_falls_back(monkeypatch):
    monkeypatch.setenv("TAO_CS_PROVIDER", "salesforce")
    assert select_cs_provider().__name__ == "synthetic_cs_provider"


# ── Zendesk no-creds fallback ───────────────────────────────────────────────


def test_zendesk_no_creds_emits_synthetic():
    out = ZD.zendesk_provider()
    from swarm.providers.synthetic_cs import synthetic_cs_provider
    expected = {m.business_id for m in synthetic_cs_provider()}
    assert {m.business_id for m in out} == expected


def test_intercom_no_creds_emits_synthetic():
    out = ZD.intercom_provider()
    from swarm.providers.synthetic_cs import synthetic_cs_provider
    expected = {m.business_id for m in synthetic_cs_provider()}
    assert {m.business_id for m in out} == expected


# ── _zendesk_metrics_for_brand parsing ──────────────────────────────────────


def test_zendesk_metrics_parses_response(monkeypatch):
    fake = {
        "count": 50,
        "results": [
            {"status": "solved", "tags": ["fcr"]},
            {"status": "solved", "tags": []},
            {"status": "open", "tags": [],
             "metric_set": {"reply_time_in_minutes": {"business": 22}}},
            {"status": "solved", "tags": ["first_contact_resolution"],
             "metric_set": {"reply_time_in_minutes": {"business": 8}}},
        ],
    }
    monkeypatch.setattr(ZD, "_zendesk_get", lambda *a, **kw: fake)
    out = ZD._zendesk_metrics_for_brand(
        subdomain="x", email="e", api_token="t", brand_id=None,
    )
    assert out is not None
    assert out["tickets_total"] == 50
    assert out["tickets_resolved_first_contact"] == 2
    # avg of 22 and 8 = 15
    assert out["avg_first_response_minutes"] == 15.0


def test_zendesk_metrics_empty_returns_none(monkeypatch):
    monkeypatch.setattr(ZD, "_zendesk_get",
                         lambda *a, **kw: {"count": 0, "results": []})
    assert ZD._zendesk_metrics_for_brand(
        subdomain="x", email="e", api_token="t", brand_id=None,
    ) is None


def test_zendesk_metrics_search_failure_returns_none(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("zendesk down")
    monkeypatch.setattr(ZD, "_zendesk_get", boom)
    assert ZD._zendesk_metrics_for_brand(
        subdomain="x", email="e", api_token="t", brand_id=None,
    ) is None


def test_zendesk_metrics_no_response_times_uses_none(monkeypatch):
    """When no metric_set on any ticket, avg_first_response_minutes is None."""
    fake = {
        "count": 3,
        "results": [{"status": "solved", "tags": ["fcr"]}] * 3,
    }
    monkeypatch.setattr(ZD, "_zendesk_get", lambda *a, **kw: fake)
    out = ZD._zendesk_metrics_for_brand(
        subdomain="x", email="e", api_token="t", brand_id=None,
    )
    assert out is not None
    assert out["avg_first_response_minutes"] is None


# ── _real_for_business overlays synthetic ───────────────────────────────────


def test_zendesk_overlay_keeps_other_fields_synthetic(monkeypatch):
    monkeypatch.setattr(ZD, "_zendesk_metrics_for_brand",
                         lambda **kw: {
                             "tickets_total": 200,
                             "tickets_resolved_first_contact": 150,
                             "avg_first_response_minutes": 12.3,
                         })
    out = ZD._real_for_business_zendesk(
        "restoreassist", subdomain="x", email="e", api_token="t",
    )
    assert out is not None
    assert out.tickets_total == 200
    assert out.tickets_resolved_first_contact == 150
    assert out.avg_first_response_minutes == 12.3
    # NPS / GRR fields stay synthetic — confirm they're still populated
    assert out.nps_promoters > 0


def test_zendesk_overlay_returns_none_on_no_real_data(monkeypatch):
    monkeypatch.setattr(ZD, "_zendesk_metrics_for_brand",
                         lambda **kw: None)
    out = ZD._real_for_business_zendesk(
        "restoreassist", subdomain="x", email="e", api_token="t",
    )
    assert out is None


# ── Provider end-to-end ─────────────────────────────────────────────────────


def test_zendesk_provider_with_creds(monkeypatch):
    monkeypatch.setenv("ZENDESK_SUBDOMAIN", "test")
    monkeypatch.setenv("ZENDESK_EMAIL", "agent@x.com")
    monkeypatch.setenv("ZENDESK_API_TOKEN", "t")

    monkeypatch.setattr(ZD, "_zendesk_metrics_for_brand",
                         lambda **kw: {
                             "tickets_total": 99,
                             "tickets_resolved_first_contact": 70,
                             "avg_first_response_minutes": 14.0,
                         })

    out = ZD.zendesk_provider()
    assert all(m.tickets_total == 99 for m in out)


def test_intercom_provider_with_creds(monkeypatch):
    monkeypatch.setenv("INTERCOM_ACCESS_TOKEN", "tok")
    monkeypatch.setattr(ZD, "_intercom_metrics",
                         lambda **kw: {
                             "tickets_total": 42,
                             "tickets_resolved_first_contact": 30,
                             "avg_first_response_minutes": 5.5,
                         })
    out = ZD.intercom_provider()
    assert all(m.tickets_total == 42 for m in out)


def test_intercom_metrics_handles_failure(monkeypatch):
    def boom(**kw):
        raise RuntimeError("intercom down")
    monkeypatch.setattr(ZD, "_intercom_search_conversations", boom)
    out = ZD._intercom_metrics(access_token="t", team_id=None)
    assert out is None


def test_intercom_metrics_empty_returns_none(monkeypatch):
    monkeypatch.setattr(
        ZD, "_intercom_search_conversations",
        lambda **kw: {"conversations": [], "total_count": 0},
    )
    out = ZD._intercom_metrics(access_token="t", team_id=None)
    assert out is None
