"""tests/test_xero_shim.py — Track 1.4 Xero cash + COGS shim smoke."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm.providers import stripe_xero as SX  # noqa: E402


# ── _scrape_xero_value walks the report tree ────────────────────────────────


def test_scrape_xero_value_finds_top_level():
    report = {
        "Reports": [{
            "Rows": [
                {"Title": "Total Bank",
                 "Cells": [{"Value": "12,345.67"}]},
            ]
        }]
    }
    out = SX._scrape_xero_value(report, row_titles=("Total Bank",))
    assert out == 12345.67


def test_scrape_xero_value_walks_nested():
    report = {
        "Reports": [{
            "Rows": [
                {"Title": "Section",
                 "Rows": [
                     {"Title": "Total Cost of Sales",
                      "Cells": [{"Value": "5,000"}]},
                 ]},
            ]
        }]
    }
    out = SX._scrape_xero_value(report, row_titles=("Total Cost of Sales",))
    assert out == 5000.0


def test_scrape_xero_value_case_insensitive():
    report = {"Reports": [{"Rows": [
        {"Title": "  total revenue  ",
         "Cells": [{"Value": "100"}]},
    ]}]}
    out = SX._scrape_xero_value(report, row_titles=("Total Revenue",))
    assert out == 100.0


def test_scrape_xero_value_missing_returns_none():
    report = {"Reports": [{"Rows": [
        {"Title": "Other Row", "Cells": [{"Value": "1"}]},
    ]}]}
    assert SX._scrape_xero_value(report, row_titles=("Total Bank",)) is None


def test_scrape_xero_value_handles_empty_report():
    assert SX._scrape_xero_value({}, row_titles=("Total Bank",)) is None
    assert SX._scrape_xero_value({"Reports": []},
                                  row_titles=("Total Bank",)) is None


def test_scrape_xero_value_skips_unparseable():
    report = {"Reports": [{"Rows": [
        {"Title": "Total Bank", "Cells": [{"Value": "n/a"}, {"Value": "42"}]},
    ]}]}
    out = SX._scrape_xero_value(report, row_titles=("Total Bank",))
    assert out == 42.0


# ── _xero_cash_and_cogs orchestration ───────────────────────────────────────


def test_xero_cash_and_cogs_happy_path(monkeypatch):
    bs = {"Reports": [{"Rows": [
        {"Title": "Total Bank", "Cells": [{"Value": "10000"}]},
    ]}]}
    pl = {"Reports": [{"Rows": [
        {"Title": "Total Cost of Sales", "Cells": [{"Value": "3000"}]},
        {"Title": "Total Revenue", "Cells": [{"Value": "12000"}]},
    ]}]}

    def fake_get(path, *, access_token, tenant_id, params=None):
        return bs if "BalanceSheet" in path else pl

    monkeypatch.setattr(SX, "_xero_get", fake_get)
    out = SX._xero_cash_and_cogs(access_token="t", tenant_id="ten")
    assert out is not None
    cash, cogs, revenue = out
    assert cash == 10000.0
    assert cogs == 3000.0
    assert revenue == 12000.0


def test_xero_cash_and_cogs_balance_sheet_failure_returns_none(monkeypatch):
    def fake_get(path, *, access_token, tenant_id, params=None):
        if "BalanceSheet" in path:
            raise RuntimeError("xero down")
        return {"Reports": []}
    monkeypatch.setattr(SX, "_xero_get", fake_get)
    assert SX._xero_cash_and_cogs(access_token="t", tenant_id="ten") is None


def test_xero_cash_and_cogs_missing_rows_uses_zero(monkeypatch):
    """BalanceSheet returns no rows → cash defaults to 0.0; full call still
    returns a tuple (caller decides whether to keep synthetic)."""
    def fake_get(path, *, access_token, tenant_id, params=None):
        return {"Reports": [{"Rows": []}]}
    monkeypatch.setattr(SX, "_xero_get", fake_get)
    out = SX._xero_cash_and_cogs(access_token="t", tenant_id="ten")
    assert out == (0.0, 0.0, 0.0)


# ── _real_for_business honours XERO env ─────────────────────────────────────


def test_real_for_business_uses_xero_when_env_present(monkeypatch):
    """With STRIPE_API_KEY + XERO_ACCESS_TOKEN + XERO_TENANT_<BID>, the
    Xero values overwrite the synthetic cash/cogs/revenue."""
    monkeypatch.setenv("XERO_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("XERO_TENANT_RESTOREASSIST", "tenant-id")

    # Stripe MRR fake: skip real network
    monkeypatch.setattr(SX, "_stripe_mrr_for_account",
                         lambda key, acct: 5000.0)

    # Xero fake: present specific values
    monkeypatch.setattr(SX, "_xero_cash_and_cogs",
                         lambda *, access_token, tenant_id: (
                             88_000.0, 1_500.0, 9_000.0,
                         ))

    out = SX._real_for_business("restoreassist", "sk_test_xxx")
    assert out is not None
    assert out.cash_on_hand == 88_000.0
    assert out.cogs == 1_500.0
    assert out.revenue == 9_000.0
    assert out.mrr == 5_000.0


def test_real_for_business_skips_xero_when_env_missing(monkeypatch):
    """Without XERO_ACCESS_TOKEN, cash/cogs stay on synthetic."""
    monkeypatch.delenv("XERO_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("XERO_TENANT_RESTOREASSIST", raising=False)

    monkeypatch.setattr(SX, "_stripe_mrr_for_account",
                         lambda key, acct: 5000.0)
    called = [False]

    def boom(*, access_token, tenant_id):
        called[0] = True
        return None

    monkeypatch.setattr(SX, "_xero_cash_and_cogs", boom)

    out = SX._real_for_business("restoreassist", "sk_test_xxx")
    assert out is not None
    # Xero not even attempted
    assert called[0] is False


def test_real_for_business_xero_failure_keeps_synthetic(monkeypatch):
    """With env present but Xero call returning None, cash/cogs stay synthetic."""
    monkeypatch.setenv("XERO_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("XERO_TENANT_RESTOREASSIST", "tenant")
    monkeypatch.setattr(SX, "_stripe_mrr_for_account",
                         lambda key, acct: 5000.0)
    monkeypatch.setattr(SX, "_xero_cash_and_cogs",
                         lambda *, access_token, tenant_id: None)

    out = SX._real_for_business("restoreassist", "sk_test_xxx")
    assert out is not None
    # Cash should be the synthetic-derived value (positive, not 0)
    assert out.cash_on_hand > 0
