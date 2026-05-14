"""Tests for swarm/_dedupe.py — the shared content-hash dedupe gate that
sits in front of every autonomous Linear-ticket generator.

Also exercises the three generators' wire-ups (enhancement_scout,
project_health_monitor, production_coordinator) end-to-end with the
Linear API patched so a second cron tick is a no-op on a duplicate.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from swarm import _dedupe


# ─── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate_state_dir(tmp_path, monkeypatch):
    """Re-point _STATE_DIR at a temp directory so tests never touch the
    real .harness/swarm/dedupe_*.jsonl state files."""
    fake_dir = tmp_path / "swarm_state"
    fake_dir.mkdir()
    monkeypatch.setattr(_dedupe, "_STATE_DIR", fake_dir)
    yield fake_dir


# ─── 1. content_hash stability ─────────────────────────────────────────────


def test_content_hash_stable_for_identical_inputs():
    """Same title+body must always produce the same hash."""
    h1 = _dedupe.content_hash("Build dashboard", "Add the home tab.")
    h2 = _dedupe.content_hash("Build dashboard", "Add the home tab.")
    assert h1 == h2
    assert len(h1) == 16


# ─── 2. content_hash normalisation ─────────────────────────────────────────


def test_content_hash_normalises_whitespace_and_case():
    """'Foo Bar' and 'foo bar  ' must collide — case and whitespace are
    not semantically significant. This is the key property that prevents
    the runaway generators re-filing slightly reformatted dupes."""
    h1 = _dedupe.content_hash("Foo Bar", "")
    h2 = _dedupe.content_hash("foo bar  ", "")
    h3 = _dedupe.content_hash("  FOO  BAR ", "")
    assert h1 == h2 == h3


# ─── 3. content_hash discrimination ────────────────────────────────────────


def test_content_hash_different_for_different_bodies():
    """Bodies that differ in the first 500 chars must produce distinct hashes."""
    h1 = _dedupe.content_hash("Same title", "Body A")
    h2 = _dedupe.content_hash("Same title", "Body B")
    assert h1 != h2


# ─── 4. already_filed — missing state file ─────────────────────────────────


def test_already_filed_returns_none_when_state_missing():
    """First-ever call must not blow up on a missing JSONL file."""
    assert _dedupe.already_filed("scout", "abcdef0123456789") is None


# ─── 5. already_filed — entry within window ────────────────────────────────


def test_already_filed_returns_linear_id_when_within_window(_isolate_state_dir):
    """An entry filed yesterday must still be seen."""
    yesterday = (
        datetime.now(timezone.utc) - timedelta(days=1)
    ).isoformat()
    row = {
        "hash": "abc123def456ghi7",
        "linear_id": "RA-9999",
        "filed_at": yesterday,
    }
    (_isolate_state_dir / "dedupe_scout.jsonl").write_text(
        json.dumps(row) + "\n", encoding="utf-8",
    )
    assert _dedupe.already_filed("scout", "abc123def456ghi7") == "RA-9999"


# ─── 6. already_filed — rolling expiry ─────────────────────────────────────


def test_already_filed_returns_none_when_entry_older_than_window(
    _isolate_state_dir,
):
    """Entries older than 14d must roll out of the window — otherwise the
    state file grows without bound and the dedupe surface drifts."""
    ancient = (
        datetime.now(timezone.utc) - timedelta(days=30)
    ).isoformat()
    row = {
        "hash": "oldhash0123456789",
        "linear_id": "RA-1",
        "filed_at": ancient,
    }
    (_isolate_state_dir / "dedupe_scout.jsonl").write_text(
        json.dumps(row) + "\n", encoding="utf-8",
    )
    assert _dedupe.already_filed("scout", "oldhash0123456789") is None


# ─── 7. record_filed then already_filed roundtrip ──────────────────────────


def test_record_filed_then_already_filed_sees_it(_isolate_state_dir):
    """The append + read cycle must round-trip — this is the core property
    every generator relies on."""
    h = _dedupe.content_hash("Round trip", "body")
    assert _dedupe.already_filed("phm", h) is None
    _dedupe.record_filed("phm", h, "UNI-7777")
    assert _dedupe.already_filed("phm", h) == "UNI-7777"


# ─── 8. Bonus: malformed rows are skipped, not fatal ───────────────────────


def test_already_filed_skips_malformed_rows(_isolate_state_dir):
    """A broken JSONL row must not crash the loader — cron resilience."""
    p = _isolate_state_dir / "dedupe_scout.jsonl"
    valid = {
        "hash": "valid000000000000",
        "linear_id": "RA-1",
        "filed_at": datetime.now(timezone.utc).isoformat(),
    }
    p.write_text(
        "{not json at all\n"
        + json.dumps(valid) + "\n"
        + "{\"hash\": \"x\"}\n",  # missing filed_at
        encoding="utf-8",
    )
    assert _dedupe.already_filed("scout", "valid000000000000") == "RA-1"


# ─── 9. Per-generator integration — enhancement_scout dedupes ──────────────


def test_enhancement_scout_dedupes_on_second_run(_isolate_state_dir, monkeypatch):
    """Two scout runs with the same proposal must call propose_idea once."""
    from swarm import enhancement_scout as es

    proposal = es.EnhancementProposal(
        title="[Enhancement] Same title each cycle",
        source="tech-drops-q2-2026.md",
        description="Adopt the new approach.",
        impact="medium",
        effort="days",
        category="infra",
    )

    calls: list[dict] = []

    def fake_propose_idea(**kwargs):
        calls.append(kwargs)
        return {"status": "created", "identifier": f"UNI-{len(calls)}"}

    # Patch the import path used inside _file_as_board_agenda
    monkeypatch.setattr(
        "swarm.margot_tools.propose_idea", fake_propose_idea, raising=True,
    )

    # First pass — should file
    filed1 = es._file_as_board_agenda([proposal])
    # Second pass — should skip (dedupe)
    filed2 = es._file_as_board_agenda([proposal])

    assert len(calls) == 1, f"expected 1 Linear call, got {len(calls)}"
    assert filed1 == ["UNI-1"]
    assert filed2 == []


# ─── 10. Per-generator integration — project_health_monitor dedupes ────────


def test_project_health_monitor_dedupes_on_second_run(
    _isolate_state_dir, monkeypatch,
):
    """Two phm runs with the same WorkOrder must call propose_idea once."""
    from swarm import project_health_monitor as phm

    wo = phm.WorkOrder(
        work_order_id="wo-test-001",
        project_id="pi-dev-ops",
        failure_type="ci_failing",
        severity="high",
        description="CI failing on main",
        context={"repo": "x/y"},
        assigned_specialist="IDD-4",
    )

    calls: list[dict] = []

    def fake_propose_idea(**kwargs):
        calls.append(kwargs)
        return {"status": "created", "identifier": f"UNI-{len(calls)}"}

    monkeypatch.setattr(
        "swarm.margot_tools.propose_idea", fake_propose_idea, raising=True,
    )

    id1 = phm._file_work_order_ticket(wo)
    id2 = phm._file_work_order_ticket(wo)

    assert len(calls) == 1
    assert id1 == "UNI-1"
    assert id2 == ""


# ─── 11. Per-generator integration — production_coordinator dedupes ────────


def test_production_coordinator_dedupes_on_second_run(
    _isolate_state_dir, monkeypatch,
):
    """Two prod_coord runs with the same ProductionJob must call propose_idea once."""
    from swarm import production_coordinator as pc

    job = pc.ProductionJob(
        business_id="restoreassist",
        content_type="videos",
        asset_id="product_demo_60s",
        skill="remotion-orchestrator",
        brief="...",
        status="done",
        output_path="/tmp/out.md",
    )

    calls: list[dict] = []

    def fake_propose_idea(**kwargs):
        calls.append(kwargs)
        return {"status": "created", "identifier": f"UNI-{len(calls)}"}

    monkeypatch.setattr(
        "swarm.margot_tools.propose_idea", fake_propose_idea, raising=True,
    )

    id1 = pc._file_linear_ticket(job)
    id2 = pc._file_linear_ticket(job)

    assert len(calls) == 1
    assert id1 == "UNI-1"
    assert id2 == ""
