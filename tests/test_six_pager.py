"""tests/test_six_pager.py — RA-1863 (A5) daily-6-pager assembler smoke."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import six_pager  # noqa: E402


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )


def test_assemble_with_all_ledgers(tmp_path):
    """All four ledgers populated → brief contains all six sections."""
    rr = tmp_path
    _write_jsonl(rr / ".harness/swarm/cfo_state.jsonl", [
        {
            "ts": "2026-05-02T06:00Z", "business_id": "restoreassist",
            "business_type": "b2b", "mrr": 12500.0, "net_new_arr": 1500.0,
            "net_burn": 800.0, "burn_multiple": 0.53, "nrr": 1.18,
            "gross_margin": 0.87, "cac_payback_months": 9.5,
            "runway_months": 22.4, "model_spend_ratio": 0.034,
        },
    ])
    _write_jsonl(rr / ".harness/swarm/cmo_state.jsonl", [
        {
            "ts": "2026-05-02T06:00Z", "business_id": "restoreassist",
            "mrr": 12500.0, "blended_cpa_usd": 87.40, "ltv_usd": 1860.0,
            "ltv_cac_ratio": 21.28, "channel_concentration_hhi": 0.46,
            "top_channel": "google-ads", "top_channel_share": 0.64,
            "attr_decay": 0.18, "total_spend_usd": 4200.0,
        },
    ])
    _write_jsonl(rr / ".harness/swarm/cto_state.jsonl", [
        {
            "ts": "2026-05-02T06:00Z", "business_id": "restoreassist",
            "deploy_freq_per_week": 5.0, "lead_time_hours_p50": 2.0,
            "mttr_hours": 1.0, "change_failure_rate": 0.10,
            "p99_latency_ms": 320.0, "uptime_pct": 0.9995,
            "cost_per_request_usd": 0.0014, "dora_band": "high",
        },
    ])
    _write_jsonl(rr / ".harness/swarm/cs_state.jsonl", [
        {
            "ts": "2026-05-02T06:00Z", "business_id": "restoreassist",
            "nps": 42.0, "fcr_pct": 0.78, "grr_pct": 0.96,
            "avg_first_response_minutes": 18.0,
            "open_enterprise_churn_threats": 0,
        },
    ])
    _write_jsonl(rr / ".harness/margot/insights.jsonl", [
        {"ts": "2026-05-02T05:30Z", "topic": "DR-NRPG insurance vertical",
         "summary": "EU AI Act class-2 risk likely; file 6-week prep ticket."},
    ])
    (rr / ".harness/ra-1842-status.json").write_text(
        json.dumps({"state": "TestFlight 1.4.0",
                    "last_update": "2026-05-01",
                    "note": "Awaiting reviewer decision."}),
        encoding="utf-8",
    )

    out = six_pager.assemble_six_pager(repo_root=rr,
                                       date_str="2026-05-02")
    assert "Pi-CEO daily 6-pager — 2026-05-02" in out
    assert "💰 CFO daily" in out
    assert "📈 CMO daily" in out
    assert "⚙️ CTO daily" in out
    assert "💬 CS daily" in out
    assert "🧠 Margot insight" in out
    assert "📱 RA-1842" in out
    assert "DR-NRPG insurance vertical" in out
    assert "TestFlight 1.4.0" in out


def test_assemble_with_missing_ledgers_degrades_gracefully(tmp_path):
    """No ledgers anywhere → still produces a brief, no exceptions."""
    out = six_pager.assemble_six_pager(repo_root=tmp_path,
                                       date_str="2026-05-02")
    assert "Pi-CEO daily 6-pager" in out
    assert "no recent snapshots" in out  # at least one section
    assert "Margot insight" in out
    assert "RA-1842" in out


def test_assemble_partial_ledgers(tmp_path):
    """Only CFO + Margot populated — CMO/CTO/CS sections placeholder."""
    rr = tmp_path
    _write_jsonl(rr / ".harness/swarm/cfo_state.jsonl", [
        {
            "ts": "2026-05-02T06:00Z", "business_id": "synthex",
            "business_type": "prosumer", "mrr": 800.0, "net_new_arr": 0.0,
            "net_burn": 1200.0, "burn_multiple": None, "nrr": 1.05,
            "gross_margin": 0.78, "cac_payback_months": None,
            "runway_months": 8.0, "model_spend_ratio": 0.06,
        },
    ])
    _write_jsonl(rr / ".harness/margot/insights.jsonl", [
        {"ts": "2026-05-02T05:30Z", "topic": "Synthex pricing",
         "summary": "Drop tier-2; expand tier-3."},
    ])
    out = six_pager.assemble_six_pager(repo_root=rr)
    assert "synthex" in out
    assert "Synthex pricing" in out
    assert "no recent snapshots" in out  # CMO/CTO/CS missing
    assert "RA-1842" in out  # placeholder


def test_assemble_truncates_long_margot_summary(tmp_path):
    long_summary = "A" * 2000
    rr = tmp_path
    _write_jsonl(rr / ".harness/margot/insights.jsonl", [
        {"ts": "x", "topic": "t", "summary": long_summary},
    ])
    out = six_pager.assemble_six_pager(repo_root=rr)
    assert "…" in out
    # Should not contain the full 2000-char string
    assert long_summary not in out
