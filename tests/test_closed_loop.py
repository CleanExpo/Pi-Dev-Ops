"""tests/test_closed_loop.py — UNI-2214: autonomous closed-loop spine.

Proves the composed cycle runs end-to-end in dry-run from a triggered intake to
an assembled brief with zero manual orchestration, and that a finding written
back is retrievable on the next cycle (the flywheel) — the ticket's verify
criterion, at the spine level (no SDK spend, no sends).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import closed_loop as CL  # noqa: E402
from swarm import config as CFG  # noqa: E402


@pytest.fixture
def loop_root(tmp_path, monkeypatch):
    """Isolated repo root: real skills/ (for the plan validator) + tmp writes."""
    (tmp_path / "skills").symlink_to(REPO_ROOT / "skills")
    # flow_engine + audit_emit write under config.SWARM_LOG_DIR — redirect to tmp
    # so the dispatcher state/audit never touch the working tree.
    monkeypatch.setattr(CFG, "SWARM_LOG_DIR", tmp_path / ".harness" / "swarm")
    (tmp_path / ".harness" / "swarm").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_full_cycle_runs_end_to_end_dry_run(loop_root):
    res = CL.run_cycle("research the AU disaster-recovery market size",
                       repo_root=loop_root, dry_run=True)

    # Every stage present, none errored.
    assert [s.name for s in res.stages] == list(CL.STAGES)
    assert res.ok, [(s.name, s.status, s.detail) for s in res.stages]

    # Intake classified the trigger.
    assert res.intent == "research"
    assert res.stage("intake").status == "ok"

    # Plan gated through the forward-planner validator (no hard errors).
    plan = res.stage("plan")
    assert plan.status == "ok", plan.detail
    assert not plan.detail.get("errors")

    # Board queued (non-blocking, no SDK spend).
    assert res.board_session_id and res.board_session_id.startswith("brd-")
    assert res.stage("decide").status == "ok"

    # Dispatcher-core actually ran the flow (dry-run).
    assert res.stage("dispatch").status == "ok"
    assert res.stage("dispatch").detail.get("flow_status") in ("completed", "running")

    # Gate skipped in dry-run (no HITL post), report assembled (no send).
    assert res.stage("gate").status == "skipped"
    assert res.stage("report").status == "ok"
    assert res.stage("report").detail.get("brief_chars", 0) > 0
    assert res.brief_excerpt


def test_finding_written_back_is_retrievable_next_cycle(loop_root):
    first = CL.run_cycle("file a ticket for the smoke-test gap",
                         repo_root=loop_root, dry_run=True)
    # Written back to the corpus.
    assert first.written_to and Path(first.written_to).exists()

    # Retrievable immediately (retrieval arm).
    recalled = CL.recall_recent_cycles(repo_root=loop_root)
    assert any(c["cycle_id"] == first.cycle_id for c in recalled)

    # A second cycle does not lose the first — the corpus accumulates.
    second = CL.run_cycle("research competitor pricing",
                          repo_root=loop_root, dry_run=True)
    recalled2 = CL.recall_recent_cycles(repo_root=loop_root)
    ids = {c["cycle_id"] for c in recalled2}
    assert {first.cycle_id, second.cycle_id} <= ids
    assert len(recalled2) >= 2


def test_trigger_queue_drains_one_per_cycle(loop_root):
    CL.enqueue_trigger("research the market", repo_root=loop_root)
    CL.enqueue_trigger("file a ticket", repo_root=loop_root)

    ran = CL.run_pending_triggers(repo_root=loop_root, dry_run=True, limit=1)
    assert len(ran) == 1
    assert ran[0].ok

    # One trigger left; the second drain takes it, then the queue is empty.
    ran2 = CL.run_pending_triggers(repo_root=loop_root, dry_run=True, limit=1)
    assert len(ran2) == 1
    assert CL.run_pending_triggers(repo_root=loop_root, dry_run=True) == []


def test_empty_queue_is_a_noop(loop_root):
    # No triggers file at all — the orchestrator drain must be a safe no-op.
    assert CL.run_pending_triggers(repo_root=loop_root, dry_run=True) == []
