"""tests/test_cs.py — RA-1862 (A4) CS-tier1 + refund-gate smoke."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import cs as _cs  # noqa: E402
from swarm.bots import cs as cs_bot  # noqa: E402
from swarm.providers import select_cs_provider  # noqa: E402
from swarm.providers.synthetic_cs import (  # noqa: E402
    synthetic_cs_one,
    synthetic_cs_provider,
)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("TAO_CS_PROVIDER", raising=False)
    monkeypatch.delenv("TAO_CS_REFUND_CEILING", raising=False)


def _expected_business_ids() -> list[str]:
    p = REPO_ROOT / ".harness/projects.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    return [proj["id"] for proj in data["projects"] if proj.get("id")]


# ── Synthetic + determinism ─────────────────────────────────────────────────


def test_synthetic_cs_one_per_business():
    out = synthetic_cs_provider()
    assert len(out) == len(_expected_business_ids())


def test_synthetic_cs_deterministic():
    a = synthetic_cs_provider()
    b = synthetic_cs_provider()
    for ma, mb in zip(a, b):
        assert ma.nps_promoters == mb.nps_promoters
        assert ma.tickets_total == mb.tickets_total


# ── compute_metrics ─────────────────────────────────────────────────────────


def test_compute_metrics_nps_hand_calc():
    raw = _cs.RawCsMetrics(
        business_id="bid", nps_promoters=60, nps_passives=20,
        nps_detractors=20,
        tickets_total=100, tickets_resolved_first_contact=80,
        customers_at_period_start=200, customers_lost_in_period=10,
        avg_first_response_minutes=15.0,
    )
    m = _cs.compute_metrics(raw)
    # NPS = 60% - 20% = 40
    assert abs(m.nps - 40.0) < 0.01
    # FCR = 0.80
    assert abs(m.fcr_pct - 0.80) < 0.001
    # GRR = (200 - 10) / 200 = 0.95
    assert abs(m.grr_pct - 0.95) < 0.001


def test_compute_metrics_zero_tickets_handled():
    raw = _cs.RawCsMetrics(
        business_id="bid", nps_promoters=0, nps_passives=0,
        nps_detractors=0,
        tickets_total=0, tickets_resolved_first_contact=0,
        customers_at_period_start=0, customers_lost_in_period=0,
        avg_first_response_minutes=0.0,
    )
    m = _cs.compute_metrics(raw)
    assert m.nps == 0.0
    assert m.fcr_pct == 0.0
    assert m.grr_pct == 1.0  # no customers → no churn → vacuously 100%


# ── Breach detection ────────────────────────────────────────────────────────


def test_detect_breaches_critical_grr():
    m = _cs.CsMetrics(
        ts="x", business_id="bid", nps=50.0, fcr_pct=0.80,
        grr_pct=0.84, avg_first_response_minutes=20.0,
        open_enterprise_churn_threats=0,
    )
    breaches = _cs.detect_breaches(m)
    assert any(b.metric == "grr_pct" and b.severity == "critical"
               for b in breaches)


def test_detect_breaches_critical_response_time():
    m = _cs.CsMetrics(
        ts="x", business_id="bid", nps=50.0, fcr_pct=0.80,
        grr_pct=0.95, avg_first_response_minutes=300.0,
        open_enterprise_churn_threats=0,
    )
    breaches = _cs.detect_breaches(m)
    assert any(b.metric == "avg_first_response_minutes"
               and b.severity == "critical" for b in breaches)


def test_detect_breaches_three_enterprise_threats_critical():
    m = _cs.CsMetrics(
        ts="x", business_id="bid", nps=50.0, fcr_pct=0.80,
        grr_pct=0.95, avg_first_response_minutes=20.0,
        open_enterprise_churn_threats=3,
    )
    breaches = _cs.detect_breaches(m)
    assert any(b.metric == "open_enterprise_churn_threats"
               and b.severity == "critical" for b in breaches)


def test_detect_breaches_low_nps_warning():
    m = _cs.CsMetrics(
        ts="x", business_id="bid", nps=20.0, fcr_pct=0.80,
        grr_pct=0.95, avg_first_response_minutes=20.0,
        open_enterprise_churn_threats=0,
    )
    breaches = _cs.detect_breaches(m)
    assert any(b.metric == "nps" and b.severity == "warning"
               for b in breaches)


# ── Daily brief ─────────────────────────────────────────────────────────────


def test_assemble_daily_brief_renders():
    raws = synthetic_cs_provider()
    snaps = [_cs.compute_metrics(r) for r in raws]
    breaches: list[_cs.CsBreach] = []
    for s in snaps:
        breaches.extend(_cs.detect_breaches(s))
    brief = _cs.assemble_daily_brief(snaps, breaches, pending_refund_count=2)
    assert "💬 CS daily" in brief
    assert "Per-business:" in brief
    assert "refund approval" in brief


# ── Refund gate ─────────────────────────────────────────────────────────────


def test_approve_refund_under_ceiling_auto():
    d = _cs.approve_refund(
        amount_usd=50.0, customer_id="cust-1",
        business_id="bid", justification="...",
    )
    assert d.status == "approved"


def test_approve_refund_over_ceiling_no_draft_blocks():
    d = _cs.approve_refund(
        amount_usd=200.0, customer_id="cust-1",
        business_id="bid", justification="...",
    )
    assert d.status == "blocked"


def test_approve_refund_over_ceiling_with_draft_pends():
    captured = {}

    def fake_post_draft(**kwargs):
        captured.update(kwargs)
        return {"draft_id": "drft-cs-001"}

    d = _cs.approve_refund(
        amount_usd=200.0, customer_id="cust-1",
        business_id="bid", justification="enterprise churn save",
        post_draft=fake_post_draft, review_chat_id="review",
    )
    assert d.status == "pending"
    assert d.draft_id == "drft-cs-001"
    assert "200.00" in captured["draft_text"]
    assert captured["drafted_by_role"] == "CS"


# ── Registry + bot ──────────────────────────────────────────────────────────


def test_registry_cs_default_synthetic(monkeypatch):
    monkeypatch.delenv("TAO_CS_PROVIDER", raising=False)
    fn = select_cs_provider()
    assert fn.__name__ == "synthetic_cs_provider"


def test_bot_default_cs_provider_non_empty():
    out = cs_bot._default_cs_provider()
    assert len(out) > 0


def test_bot_default_cs_provider_handles_crash(monkeypatch):
    import swarm.providers
    orig = swarm.providers.select_cs_provider
    monkeypatch.setattr(
        swarm.providers, "select_cs_provider",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    try:
        out = cs_bot._default_cs_provider()
        assert out == []
    finally:
        monkeypatch.setattr(swarm.providers, "select_cs_provider", orig)
