"""Tests for swarm/feature_orchestrator.py — the third swarm lane that
ships margot-idea Backlog tickets via specialist Claude Code agents.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from swarm import feature_orchestrator as fo


# ─── Helpers ───────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate_jobs_log(tmp_path, monkeypatch):
    """Re-point the JSONL state file at a temp file so tests don't pollute
    .harness/swarm/feature_jobs.jsonl in the real repo."""
    fake_log = tmp_path / "feature_jobs.jsonl"

    def _fake_jobs_log() -> Path:
        return fake_log

    monkeypatch.setattr(fo, "_jobs_log", _fake_jobs_log)
    # Force shadow mode so we never accidentally fire a real specialist
    monkeypatch.setenv("TAO_SWARM_SHADOW", "1")
    # Reset cached project index so tests aren't affected by load order
    monkeypatch.setattr(fo, "_PROJECT_INDEX", None)
    yield fake_log


def _ticket(identifier: str, title: str, description: str,
            priority: int = 2, labels: list[str] | None = None) -> dict:
    return {
        "id": f"uuid-{identifier}",
        "identifier": identifier,
        "title": title,
        "description": description,
        "priority": priority,
        "createdAt": "2026-05-14T00:00:00Z",
        "labels": {
            "nodes": [{"name": n} for n in (labels or ["margot-idea"])]
        },
    }


# ─── 1. should_run cadence gate ────────────────────────────────────────────


def test_should_run_returns_false_if_last_cycle_within_30_min():
    """should_run must be False when the last cycle ran <30 min ago."""
    recent = (
        datetime.now(timezone.utc) - timedelta(minutes=15)
    ).isoformat()
    state = {fo.STATE_KEY: recent}
    assert fo.should_run(state) is False


def test_should_run_returns_true_if_last_cycle_over_30_min_ago():
    """Sanity: same cadence gate returns True when stale enough."""
    old = (
        datetime.now(timezone.utc) - timedelta(minutes=45)
    ).isoformat()
    state = {fo.STATE_KEY: old}
    assert fo.should_run(state) is True


def test_should_run_returns_true_if_never_run():
    assert fo.should_run({}) is True


# ─── 2 & 3. Pure-function triage ───────────────────────────────────────────


def test_triage_specialist_picks_idd4_for_frontend_only_description():
    """Frontend-only UI tweaks must route to IDD-4."""
    spec = fo.triage_specialist(
        title="Tweak dashboard copy on the CEO landing page",
        description=(
            "Update the hero UI copy on the landing page. "
            "Tailwind component change only. No backend needed."
        ),
    )
    assert spec == "IDD-4"


def test_triage_specialist_picks_sd1_for_migration_description():
    """Migration / schema language must route to SD-1, not IDD-3."""
    spec = fo.triage_specialist(
        title="Add boards_mandates table",
        description=(
            "Create a new Supabase SQL migration adding the boards_mandates "
            "table with RLS policies. Includes ALTER TABLE on board_sessions."
        ),
    )
    assert spec == "SD-1"


def test_triage_specialist_default_idd3_for_ambiguous_backend():
    """When nothing specific matches, IDD-3 is the catch-all."""
    spec = fo.triage_specialist(
        title="Improve swarm cycle latency",
        description="Make the Python loop faster, ideally under 5s.",
    )
    assert spec == "IDD-3"


def test_triage_complexity_returns_xl_for_phase_4_epic():
    """Phase / epic / multi-week markers must force xl bucket → park."""
    bucket = fo.triage_complexity(
        title="Wave 7 — phase 4 ATIA federation rollout",
        description=(
            "This is the phase 4 epic that ties together all five vertical lanes."
        ),
    )
    assert bucket == "xl"


def test_triage_complexity_s_for_short_ui_description():
    bucket = fo.triage_complexity(
        title="Rename dashboard tab",
        description="Change 'Tickets' to 'Work Orders' in the nav.",
    )
    assert bucket == "s"


def test_triage_complexity_l_for_multi_subsystem_description():
    bucket = fo.triage_complexity(
        title="Auto-sync deal velocity from CCW to CFO bot",
        description=(
            "We need a new FastAPI endpoint on the backend, a Supabase migration "
            "to add the deal_velocity table, a Vercel deploy of the dashboard UI "
            "component, and a Tailwind frontend page showing the chart."
        ),
    )
    assert bucket == "l"


# ─── 4. run_cycle — no eligible tickets ─────────────────────────────────────


def test_run_cycle_no_tickets_is_noop():
    """Empty Linear result must produce a no-op result."""
    with patch.object(fo, "_fetch_eligible_tickets", return_value=[]):
        result = fo.run_cycle()

    assert result.jobs_dispatched == []
    assert result.jobs_failed == []
    assert result.jobs_parked == []
    assert result.jobs_needing_plan == []


# ─── 5. run_cycle — two m-tickets dispatched ───────────────────────────────


def test_run_cycle_with_two_eligible_m_tickets_dispatches_both():
    """Two priority-2 m-complexity tickets must dispatch both specialists
    in a single cycle (cap is 2)."""
    t1 = _ticket(
        "UNI-1001",
        "Add Pi-CEO health endpoint",
        # Force `m` bucket: API mention bumps small descriptions to m
        "Add a /api/health endpoint that returns swarm status JSON.",
    )
    t2 = _ticket(
        "UNI-1002",
        "Improve fix_orchestrator triage logging",
        # ~100 words ⇒ m bucket
        " ".join(["Add structured Python backend logging."] * 20),
    )

    with patch.object(fo, "_fetch_eligible_tickets", return_value=[t1, t2]):
        result = fo.run_cycle()

    assert "UNI-1001" in result.jobs_dispatched
    assert "UNI-1002" in result.jobs_dispatched
    assert len(result.jobs_dispatched) == 2


# ─── 6. Concurrency cap ────────────────────────────────────────────────────


def test_run_cycle_respects_max_active_features_cap(_isolate_jobs_log):
    """When MAX_ACTIVE_FEATURES jobs are already 'dispatched', no new
    dispatches happen this cycle."""
    log_file = _isolate_jobs_log
    now = datetime.now(timezone.utc).isoformat()
    pre_dispatched = [
        {
            "linear_id": "UNI-9001", "title": "old job 1", "description": "",
            "priority": 2, "project_slug": "pi-dev-ops", "labels": ["margot-idea"],
            "complexity": "m", "specialist": "IDD-3", "status": "dispatched",
            "pr_url": None, "error": None, "failed_attempts": 0,
            "created_at": now, "updated_at": now,
        },
        {
            "linear_id": "UNI-9002", "title": "old job 2", "description": "",
            "priority": 2, "project_slug": "pi-dev-ops", "labels": ["margot-idea"],
            "complexity": "m", "specialist": "IDD-4", "status": "pr_open",
            "pr_url": None, "error": None, "failed_attempts": 0,
            "created_at": now, "updated_at": now,
        },
    ]
    log_file.write_text("\n".join(json.dumps(r) for r in pre_dispatched) + "\n")

    new_ticket = _ticket(
        "UNI-1003",
        "Add a new thing",
        "Tiny backend Python feature.",
    )

    with patch.object(fo, "_fetch_eligible_tickets", return_value=[new_ticket]):
        result = fo.run_cycle()

    # Cap is 2 and 2 are already active — nothing new should dispatch
    assert result.jobs_dispatched == []


# ─── 7. Failure cycles back to Backlog with incremented counter ────────────


def test_specialist_failure_cycles_ticket_back_and_increments_attempts(
    monkeypatch, _isolate_jobs_log,
):
    """When dispatch returns status='failed', the job must:
    - not be marked done
    - have failed_attempts incremented
    - still be eligible for retry on the next cycle (unless 3 failures)
    """
    # Disable shadow mode so the real dispatch path runs (mocked below)
    monkeypatch.delenv("TAO_SWARM_SHADOW", raising=False)

    def _failing_dispatch(job, project):
        job.status = "failed"
        job.error = "boom"
        job.failed_attempts += 1
        fo._save_job(job)
        return job

    monkeypatch.setattr(fo, "_dispatch_specialist", _failing_dispatch)

    t = _ticket(
        "UNI-2001",
        "Add API endpoint",
        "Backend API endpoint adding hello world.",
    )

    with patch.object(fo, "_fetch_eligible_tickets", return_value=[t]):
        result = fo.run_cycle()

    assert "UNI-2001" in result.jobs_failed

    # Read the JSONL and check failed_attempts incremented + status=failed
    jobs = fo._load_jobs_index()
    assert "UNI-2001" in jobs
    assert jobs["UNI-2001"].status == "failed"
    assert jobs["UNI-2001"].failed_attempts == 1
    # Not parked yet — only after MAX_FAILED_ATTEMPTS
    assert jobs["UNI-2001"].status != "parked"


def test_three_failures_park_the_ticket(monkeypatch, _isolate_jobs_log):
    """After MAX_FAILED_ATTEMPTS (3) failures, the next cycle must park
    the ticket instead of dispatching again."""
    log_file = _isolate_jobs_log
    now = datetime.now(timezone.utc).isoformat()
    log_file.write_text(json.dumps({
        "linear_id": "UNI-3001", "title": "thrice failed",
        "description": "Backend Python API.", "priority": 2,
        "project_slug": "pi-dev-ops", "labels": ["margot-idea"],
        "complexity": "m", "specialist": "IDD-3", "status": "failed",
        "pr_url": None, "error": "previous error",
        "failed_attempts": fo.MAX_FAILED_ATTEMPTS,
        "created_at": now, "updated_at": now,
    }) + "\n")

    t = _ticket(
        "UNI-3001",
        "thrice failed",
        "Backend Python API endpoint.",
    )

    with patch.object(fo, "_fetch_eligible_tickets", return_value=[t]):
        result = fo.run_cycle()

    assert "UNI-3001" in result.jobs_parked
    jobs = fo._load_jobs_index()
    assert jobs["UNI-3001"].status == "parked"
    assert "3 attempts failed" in (jobs["UNI-3001"].error or "")


# ─── 8. xl/l routing ───────────────────────────────────────────────────────


def test_xl_complexity_ticket_is_parked_not_dispatched(_isolate_jobs_log):
    """xl complexity → parked with reason, no dispatch."""
    t = _ticket(
        "UNI-4001",
        "Phase 4 epic — multi-week federation",
        "This is the phase 4 epic spanning multiple weeks.",
    )
    with patch.object(fo, "_fetch_eligible_tickets", return_value=[t]):
        result = fo.run_cycle()

    assert "UNI-4001" in result.jobs_parked
    assert "UNI-4001" not in result.jobs_dispatched


def test_l_complexity_ticket_flagged_for_planning_not_dispatched(
    _isolate_jobs_log,
):
    """l complexity → needs_planning, alerts PM, no dispatch."""
    description = (
        "We need a new FastAPI backend endpoint, a Supabase database "
        "migration, a Vercel deploy of the dashboard UI page, and a "
        "Tailwind frontend component for the chart."
    )
    t = _ticket(
        "UNI-4002",
        "Multi-subsystem feature",
        description,
    )
    with patch.object(fo, "_fetch_eligible_tickets", return_value=[t]):
        result = fo.run_cycle()

    assert "UNI-4002" in result.jobs_needing_plan
    assert "UNI-4002" not in result.jobs_dispatched
