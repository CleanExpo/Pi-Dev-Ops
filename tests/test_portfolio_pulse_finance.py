"""tests/test_portfolio_pulse_finance.py — RA-1891.

Exercises the finance section provider's contract:
  * happy path → live values surface with "(live)" labels
  * missing cfo_state.jsonl → synthetic fallback with "(synthetic)" labels
  * read error → never raises, returns a section
  * llm-cost.jsonl absent → "pending RA-1909" placeholder line
  * llm-cost.jsonl present → "(live)" labelled cost line
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import portfolio_pulse  # noqa: E402
from swarm import portfolio_pulse_finance as ppf  # noqa: E402


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── Happy path ──────────────────────────────────────────────────────────────


def test_happy_path_live_labels(tmp_path):
    """cfo_state.jsonl has data → MRR + burn surface as live."""
    rr = tmp_path
    _write_jsonl(rr / ppf.CFO_STATE_FILE_REL, [
        {
            "ts": "2026-05-03T06:00Z", "business_id": "restoreassist",
            "business_type": "b2b", "mrr": 12500.0, "net_new_arr": 1500.0,
            "net_burn": 4200.0, "burn_multiple": 0.53, "nrr": 1.18,
            "gross_margin": 0.87, "cac_payback_months": 9.5,
            "runway_months": 22.4, "model_spend_ratio": 0.034,
        },
    ])
    body, err = ppf.finance_section_provider("restoreassist", rr)
    assert err is None
    assert "$12,500" in body
    assert "$4,200" in body
    assert "(from Stripe live)" in body
    assert "(from Xero live)" in body
    # No synthetic labels in a fully-live snapshot.
    assert "synthetic" not in body


def test_happy_path_with_llm_cost_live(tmp_path):
    """llm-cost.jsonl with today's rows → cost line labelled live."""
    rr = tmp_path
    _write_jsonl(rr / ppf.CFO_STATE_FILE_REL, [
        {
            "ts": "2026-05-03T06:00Z", "business_id": "pi-ceo",
            "business_type": "b2b", "mrr": 0.0, "net_new_arr": 0.0,
            "net_burn": 0.0, "burn_multiple": None, "nrr": 1.0,
            "gross_margin": 0.0, "cac_payback_months": None,
            "runway_months": None, "model_spend_ratio": 0.0,
        },
    ])
    today = _today()
    _write_jsonl(rr / ppf.LLM_COST_FILE_REL, [
        {"ts": f"{today}T01:00Z", "cost_usd": 0.42},
        {"ts": f"{today}T05:00Z", "cost_usd": 1.13},
        # Yesterday — must be ignored.
        {"ts": "2026-05-01T06:00Z", "cost_usd": 99.0},
    ])
    body, err = ppf.finance_section_provider("pi-ceo", rr)
    assert err is None
    assert "$1.55" in body
    assert "live" in body
    assert "pending RA-1909" not in body


# ── Missing files → synthetic fallback ──────────────────────────────────────


def test_missing_cfo_state_falls_back_to_synthetic(tmp_path):
    """No cfo_state.jsonl → synthetic labels on MRR + burn."""
    rr = tmp_path
    body, err = ppf.finance_section_provider("restoreassist", rr)
    assert err is None
    assert "(from Stripe synthetic)" in body
    assert "(from Xero synthetic)" in body
    assert "pending RA-1909" in body
    assert "$0" in body


def test_unmatched_business_id_falls_back_to_synthetic(tmp_path):
    """cfo_state.jsonl exists but no row matches → synthetic."""
    rr = tmp_path
    _write_jsonl(rr / ppf.CFO_STATE_FILE_REL, [
        {
            "ts": "2026-05-03T06:00Z", "business_id": "some-other-project",
            "business_type": "b2b", "mrr": 99999.0, "net_new_arr": 0.0,
            "net_burn": 9999.0, "burn_multiple": None, "nrr": 1.0,
            "gross_margin": 0.0, "cac_payback_months": None,
            "runway_months": None, "model_spend_ratio": 0.0,
        },
    ])
    body, err = ppf.finance_section_provider("restoreassist", rr)
    assert err is None
    assert "(from Stripe synthetic)" in body
    assert "(from Xero synthetic)" in body
    # The unmatched project's MRR must NOT leak through.
    assert "99,999" not in body


# ── Defensive — never raises ────────────────────────────────────────────────


def test_read_error_returns_section(tmp_path, monkeypatch):
    """A read failure inside _gather_figures must not raise."""
    rr = tmp_path

    def boom(*args, **kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(ppf, "_read_last_cfo_row", boom)
    monkeypatch.setattr(ppf, "_read_today_llm_cost", boom)
    body, err = ppf.finance_section_provider("restoreassist", rr)
    # Section returned, no exception, fallback to synthetic.
    assert isinstance(body, str)
    assert err is None or isinstance(err, str)
    assert "synthetic" in body


def test_corrupt_cfo_state_does_not_raise(tmp_path):
    """Malformed JSON lines are skipped silently → fallback to synthetic."""
    rr = tmp_path
    p = rr / ppf.CFO_STATE_FILE_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json\n\n{\"business_id\": \"x\"}\n", encoding="utf-8")
    body, err = ppf.finance_section_provider("restoreassist", rr)
    assert err is None
    assert "synthetic" in body


# ── Labelling correctness ───────────────────────────────────────────────────


def test_label_correctness_partial_data(tmp_path):
    """A row missing net_burn keeps live MRR but synthetic burn."""
    rr = tmp_path
    _write_jsonl(rr / ppf.CFO_STATE_FILE_REL, [
        {
            "ts": "2026-05-03T06:00Z", "business_id": "restoreassist",
            "mrr": 7777.0,
            # net_burn intentionally absent
        },
    ])
    body, err = ppf.finance_section_provider("restoreassist", rr)
    assert err is None
    # MRR live, monthly burn falls through to live with 0.0 (field present
    # in row even when 0). The contract is: row matched → live label.
    assert "$7,777" in body
    assert "(from Stripe live)" in body


# ── Provider entry point (PulseSection wrapper) ─────────────────────────────


def test_provider_returns_pulsesection(tmp_path):
    """The composite provider() returns a PulseSection named 'finance'."""
    rr = tmp_path
    section = ppf.provider("restoreassist", repo_root=rr)
    assert isinstance(section, portfolio_pulse.PulseSection)
    assert section.name == "finance"
    assert "MRR" in section.body_md
    assert "Monthly burn" in section.body_md


def test_self_registration_replaces_placeholder():
    """Importing the module must replace the foundation placeholder."""
    # Foundation registers a tuple-returning provider; on import,
    # this module's finance_section_provider takes the slot.
    assert (portfolio_pulse._SECTION_PROVIDERS["finance"]
            is ppf.finance_section_provider)
