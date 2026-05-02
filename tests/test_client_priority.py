"""tests/test_client_priority.py — first-client elevation smoke."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import client_priority as CP  # noqa: E402
from swarm import cs as _cs  # noqa: E402
from swarm import six_pager  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for k in [
        "TAO_FIRST_CLIENTS",
        "TAO_FIRST_CLIENT_RESPONSE_ALERT_MIN",
        "TAO_FIRST_CLIENT_RESPONSE_CRITICAL_MIN",
    ]:
        monkeypatch.delenv(k, raising=False)


# ── client_priority defaults ────────────────────────────────────────────────


def test_default_first_clients_includes_ccw():
    """ccw-crm is the default first client, no env required."""
    assert "ccw-crm" in CP.list_first_clients()


def test_is_first_client_recognises_default():
    assert CP.is_first_client("ccw-crm") is True


def test_is_first_client_other_business_false():
    assert CP.is_first_client("restoreassist") is False


def test_env_override_replaces_default(monkeypatch):
    monkeypatch.setenv("TAO_FIRST_CLIENTS", "synthex,carsi")
    assert CP.is_first_client("ccw-crm") is False
    assert CP.is_first_client("synthex") is True
    assert CP.is_first_client("carsi") is True


def test_env_override_handles_whitespace(monkeypatch):
    monkeypatch.setenv("TAO_FIRST_CLIENTS", " ccw-crm , synthex ")
    out = CP.list_first_clients()
    assert out == ["ccw-crm", "synthex"]


# ── Tightened SLA thresholds ────────────────────────────────────────────────


def test_first_client_uses_tighter_alert():
    out = CP.first_client_first_response_alert("ccw-crm")
    assert out == 15.0  # tighter than the cs.py default of 60.0


def test_first_client_uses_tighter_critical():
    out = CP.first_client_first_response_critical("ccw-crm")
    assert out == 60.0  # tighter than the cs.py default of 240.0


def test_non_first_client_uses_module_defaults():
    out_alert = CP.first_client_first_response_alert("restoreassist")
    out_crit = CP.first_client_first_response_critical("restoreassist")
    assert out_alert == _cs.ALERT_FIRST_RESPONSE_MINUTES
    assert out_crit == _cs.CRITICAL_FIRST_RESPONSE_MINUTES


def test_env_overrides_tightened_thresholds(monkeypatch):
    monkeypatch.setenv("TAO_FIRST_CLIENT_RESPONSE_ALERT_MIN", "5")
    monkeypatch.setenv("TAO_FIRST_CLIENT_RESPONSE_CRITICAL_MIN", "20")
    assert CP.first_client_first_response_alert("ccw-crm") == 5.0
    assert CP.first_client_first_response_critical("ccw-crm") == 20.0


def test_garbage_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("TAO_FIRST_CLIENT_RESPONSE_ALERT_MIN", "not-a-number")
    assert CP.first_client_first_response_alert("ccw-crm") == 15.0


# ── CS bot uses tightened thresholds for first clients ─────────────────────


def test_cs_breach_uses_tightened_threshold_for_first_client():
    """CCW with 30min first response is well within standard 60min alert,
    but BREACHES the first-client tightened 15min threshold."""
    m = _cs.CsMetrics(
        ts="x", business_id="ccw-crm", nps=70.0, fcr_pct=0.85,
        grr_pct=0.97, avg_first_response_minutes=30.0,
        open_enterprise_churn_threats=0,
    )
    breaches = _cs.detect_breaches(m)
    fr_breaches = [b for b in breaches
                   if b.metric == "avg_first_response_minutes"]
    assert len(fr_breaches) == 1
    assert fr_breaches[0].severity == "warning"
    assert "FIRST CLIENT" in fr_breaches[0].note


def test_cs_breach_uses_tightened_critical_for_first_client():
    """CCW with 90min first response breaches first-client 60min critical."""
    m = _cs.CsMetrics(
        ts="x", business_id="ccw-crm", nps=70.0, fcr_pct=0.85,
        grr_pct=0.97, avg_first_response_minutes=90.0,
        open_enterprise_churn_threats=0,
    )
    breaches = _cs.detect_breaches(m)
    fr_breaches = [b for b in breaches
                   if b.metric == "avg_first_response_minutes"]
    assert len(fr_breaches) == 1
    assert fr_breaches[0].severity == "critical"
    assert "FIRST CLIENT" in fr_breaches[0].note


def test_cs_breach_standard_threshold_for_other_businesses():
    """RestoreAssist with 30min first response is fine — standard alert is 60m."""
    m = _cs.CsMetrics(
        ts="x", business_id="restoreassist", nps=70.0, fcr_pct=0.85,
        grr_pct=0.97, avg_first_response_minutes=30.0,
        open_enterprise_churn_threats=0,
    )
    breaches = _cs.detect_breaches(m)
    fr_breaches = [b for b in breaches
                   if b.metric == "avg_first_response_minutes"]
    assert fr_breaches == []


def test_cs_breach_standard_alert_still_fires_for_non_first_client():
    """Standard 60min alert still fires for non-first-client."""
    m = _cs.CsMetrics(
        ts="x", business_id="restoreassist", nps=70.0, fcr_pct=0.85,
        grr_pct=0.97, avg_first_response_minutes=70.0,
        open_enterprise_churn_threats=0,
    )
    breaches = _cs.detect_breaches(m)
    fr_breaches = [b for b in breaches
                   if b.metric == "avg_first_response_minutes"]
    assert len(fr_breaches) == 1
    assert "FIRST CLIENT" not in fr_breaches[0].note


# ── 6-pager first-client section ───────────────────────────────────────────


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )


def test_six_pager_includes_first_client_banner_when_present(tmp_path):
    """CCW row in CS ledger → first-client banner appears at top."""
    rr = tmp_path
    _write_jsonl(rr / ".harness/swarm/cs_state.jsonl", [
        {
            "ts": "2026-05-03T06:00Z", "business_id": "ccw-crm",
            "nps": 72.0, "fcr_pct": 0.85, "grr_pct": 0.97,
            "avg_first_response_minutes": 12.0,
            "open_enterprise_churn_threats": 0,
        },
    ])
    _write_jsonl(rr / ".harness/swarm/cfo_state.jsonl", [
        {
            "ts": "2026-05-03T06:00Z", "business_id": "ccw-crm",
            "business_type": "b2b", "mrr": 4500.0, "net_new_arr": 0.0,
            "net_burn": 0.0, "burn_multiple": None, "nrr": 1.05,
            "gross_margin": 0.88, "cac_payback_months": None,
            "runway_months": None, "model_spend_ratio": 0.02,
        },
    ])
    out = six_pager.assemble_six_pager(repo_root=rr, date_str="2026-05-03")
    assert "⭐ FIRST CLIENT — ccw-crm" in out
    # Banner appears before section 1 (CFO)
    assert out.index("⭐ FIRST CLIENT") < out.index("1. ")
    # SLA state shown — 12min is within tightened 15min alert
    assert "✅ within SLA" in out


def test_six_pager_first_client_banner_shows_sla_breach(tmp_path):
    rr = tmp_path
    _write_jsonl(rr / ".harness/swarm/cs_state.jsonl", [
        {
            "ts": "2026-05-03T06:00Z", "business_id": "ccw-crm",
            "nps": 72.0, "fcr_pct": 0.85, "grr_pct": 0.97,
            "avg_first_response_minutes": 90.0,  # > tightened 60m critical
            "open_enterprise_churn_threats": 0,
        },
    ])
    out = six_pager.assemble_six_pager(repo_root=rr, date_str="2026-05-03")
    assert "🔴 SLA BREACH" in out


def test_six_pager_no_banner_when_no_first_client_data(tmp_path):
    """No CCW data anywhere → no first-client banner section."""
    rr = tmp_path
    _write_jsonl(rr / ".harness/swarm/cs_state.jsonl", [
        {
            "ts": "2026-05-03T06:00Z", "business_id": "restoreassist",
            "nps": 50.0, "fcr_pct": 0.80, "grr_pct": 0.95,
            "avg_first_response_minutes": 20.0,
            "open_enterprise_churn_threats": 0,
        },
    ])
    out = six_pager.assemble_six_pager(repo_root=rr, date_str="2026-05-03")
    assert "FIRST CLIENT" not in out


def test_six_pager_first_client_banner_with_partial_data(tmp_path):
    """CCW only in CFO ledger (no CS row) → banner shown with CFO line only."""
    rr = tmp_path
    _write_jsonl(rr / ".harness/swarm/cfo_state.jsonl", [
        {
            "ts": "2026-05-03T06:00Z", "business_id": "ccw-crm",
            "business_type": "b2b", "mrr": 4500.0, "net_new_arr": 0.0,
            "net_burn": 0.0, "burn_multiple": None, "nrr": 1.05,
            "gross_margin": 0.88, "cac_payback_months": None,
            "runway_months": None, "model_spend_ratio": 0.02,
        },
    ])
    out = six_pager.assemble_six_pager(repo_root=rr, date_str="2026-05-03")
    assert "⭐ FIRST CLIENT — ccw-crm" in out
    assert "$4,500 MRR" in out
