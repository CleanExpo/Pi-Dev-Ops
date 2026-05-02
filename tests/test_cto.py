"""tests/test_cto.py — RA-1861 (A3) CTO + DORA aggregator smoke."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import cto as _cto  # noqa: E402
from swarm.bots import cto as cto_bot  # noqa: E402
from swarm.providers import select_platform_provider  # noqa: E402
from swarm.providers.synthetic_platform import (  # noqa: E402
    synthetic_platform_one,
    synthetic_platform_provider,
)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("TAO_CTO_PROVIDER", raising=False)


def _expected_business_ids() -> list[str]:
    p = REPO_ROOT / ".harness/projects.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    return [proj["id"] for proj in data["projects"] if proj.get("id")]


# ── Synthetic provider ──────────────────────────────────────────────────────


def test_synthetic_platform_one_per_business():
    out = synthetic_platform_provider()
    assert len(out) == len(_expected_business_ids())


def test_synthetic_platform_deterministic():
    a = synthetic_platform_provider()
    b = synthetic_platform_provider()
    for ma, mb in zip(a, b):
        assert ma.deploys_last_week == mb.deploys_last_week
        assert ma.mttr_hours == mb.mttr_hours
        assert ma.uptime_pct == mb.uptime_pct


# ── compute_metrics + DORA classifier ───────────────────────────────────────


def test_compute_metrics_dora_elite():
    raw = _cto.RawPlatformMetrics(
        business_id="bid", deploys_last_week=10,
        lead_time_hours_p50=0.5, mttr_hours=0.5,
        change_failure_count=1, change_total_count=20,
        p99_latency_ms=200.0, uptime_pct=0.9999,
        cost_per_request_usd=0.001,
    )
    m = _cto.compute_metrics(raw)
    assert m.dora_band == "elite"
    assert abs(m.change_failure_rate - 0.05) < 0.001


def test_compute_metrics_dora_low():
    raw = _cto.RawPlatformMetrics(
        business_id="bid", deploys_last_week=0,
        lead_time_hours_p50=200.0, mttr_hours=48.0,
        change_failure_count=15, change_total_count=20,
        p99_latency_ms=2500.0, uptime_pct=0.985,
        cost_per_request_usd=0.01,
    )
    m = _cto.compute_metrics(raw)
    assert m.dora_band == "low"


# ── Breach detection ────────────────────────────────────────────────────────


def test_detect_breaches_critical_mttr():
    m = _cto.PlatformMetrics(
        ts="x", business_id="bid",
        deploy_freq_per_week=5.0, lead_time_hours_p50=2.0,
        mttr_hours=30.0, change_failure_rate=0.10,
        p99_latency_ms=200.0, uptime_pct=0.9999,
        cost_per_request_usd=0.001, dora_band="medium",
    )
    breaches = _cto.detect_breaches(m)
    crits = [b for b in breaches if b.severity == "critical"]
    assert any(b.metric == "mttr_hours" for b in crits)


def test_detect_breaches_critical_uptime():
    m = _cto.PlatformMetrics(
        ts="x", business_id="bid",
        deploy_freq_per_week=5.0, lead_time_hours_p50=2.0,
        mttr_hours=2.0, change_failure_rate=0.10,
        p99_latency_ms=200.0, uptime_pct=0.985,
        cost_per_request_usd=0.001, dora_band="medium",
    )
    breaches = _cto.detect_breaches(m)
    assert any(b.metric == "uptime_pct" and b.severity == "critical"
               for b in breaches)


def test_detect_breaches_critical_cfr():
    m = _cto.PlatformMetrics(
        ts="x", business_id="bid",
        deploy_freq_per_week=5.0, lead_time_hours_p50=2.0,
        mttr_hours=2.0, change_failure_rate=0.40,
        p99_latency_ms=200.0, uptime_pct=0.9999,
        cost_per_request_usd=0.001, dora_band="medium",
    )
    breaches = _cto.detect_breaches(m)
    assert any(b.metric == "change_failure_rate" and b.severity == "critical"
               for b in breaches)


def test_detect_breaches_low_deploy_freq():
    m = _cto.PlatformMetrics(
        ts="x", business_id="bid",
        deploy_freq_per_week=1.0, lead_time_hours_p50=2.0,
        mttr_hours=2.0, change_failure_rate=0.10,
        p99_latency_ms=200.0, uptime_pct=0.9999,
        cost_per_request_usd=0.001, dora_band="medium",
    )
    breaches = _cto.detect_breaches(m)
    assert any(b.metric == "deploy_freq_per_week" for b in breaches)


# ── Daily brief ─────────────────────────────────────────────────────────────


def test_assemble_daily_brief_renders():
    raws = synthetic_platform_provider()
    snaps = [_cto.compute_metrics(r) for r in raws]
    breaches: list[_cto.PlatformBreach] = []
    for s in snaps:
        breaches.extend(_cto.detect_breaches(s))
    brief = _cto.assemble_daily_brief(snaps, breaches, pending_pr_count=2)
    assert "⚙️ CTO daily" in brief
    assert "DORA distribution:" in brief
    assert "production PR merge" in brief


# ── PR merge approval ──────────────────────────────────────────────────────


def test_approve_pr_merge_feature_branch_auto_approves():
    d = _cto.approve_pr_merge(
        repo="restoreassist", pr_number=42,
        target_branch="feature/x", title="add x",
        is_production=False,
    )
    assert d.status == "approved"


def test_approve_pr_merge_production_no_draft_blocks():
    d = _cto.approve_pr_merge(
        repo="restoreassist", pr_number=42,
        target_branch="main", title="ship x",
        is_production=True,
    )
    assert d.status == "blocked"


def test_approve_pr_merge_production_with_draft_pends():
    captured = {}

    def fake_post_draft(**kwargs):
        captured.update(kwargs)
        return {"draft_id": "drft-cto-001"}

    d = _cto.approve_pr_merge(
        repo="restoreassist", pr_number=42,
        target_branch="main", title="ship x",
        is_production=True, post_draft=fake_post_draft,
        review_chat_id="review",
    )
    assert d.status == "pending"
    assert d.draft_id == "drft-cto-001"
    assert "restoreassist#42" in captured["draft_text"]
    assert captured["drafted_by_role"] == "CTO"


# ── Registry + bot wire-up ──────────────────────────────────────────────────


def test_registry_platform_default_is_synthetic(monkeypatch):
    monkeypatch.delenv("TAO_CTO_PROVIDER", raising=False)
    fn = select_platform_provider()
    assert fn.__name__ == "synthetic_platform_provider"


def test_bot_default_platform_provider_non_empty():
    out = cto_bot._default_platform_provider()
    assert len(out) > 0


def test_bot_default_platform_provider_handles_crash(monkeypatch):
    import swarm.providers
    orig = swarm.providers.select_platform_provider
    monkeypatch.setattr(
        swarm.providers, "select_platform_provider",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    try:
        out = cto_bot._default_platform_provider()
        assert out == []
    finally:
        monkeypatch.setattr(swarm.providers, "select_platform_provider", orig)
