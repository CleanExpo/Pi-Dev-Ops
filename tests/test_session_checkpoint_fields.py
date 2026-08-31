"""
test_session_checkpoint_fields.py — a checkpoint that can actually resume elsewhere.

`save_session_checkpoint()` used to persist ten fields and drop about fifteen,
including the plan, the repo context, the scope contract and the evaluator's
findings — so a "resumed" session re-derived all of it from scratch. And its one
machine-local field, `workspace`, was replayed verbatim onto a machine where that
directory does not exist.

Companion to tests/test_session_lease.py (which owns the ownership race) and
tests/test_mesh_ticket_claim.py (which owns the Linear-ticket claim).
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


# ── Checkpoint completeness ───────────────────────────────────────────────────


def _rich_session(**overrides):
    from src.tao.budget.tracker import BudgetTracker  # noqa: PLC0415

    base = dict(
        id="sid-1",
        repo_url="https://github.com/CleanExpo/Pi-Dev-Ops",
        branch="feature/x",
        status="running",
        trigger="linear",
        started_at=1700000000.0,
        last_completed_phase="generator",
        retry_count=2,
        evaluator_status="pass",
        evaluator_score=88.0,
        evaluator_model="sonnet",
        evaluator_consensus="agreed",
        linear_issue_id="RA-1",
        workspace="/tmp/pi-ceo-workspaces/sid-1",
        error="",
        output_lines=[{"text": "a"}],
        plan="## Plan\nstep one",
        repo_context={"languages": ["python"]},
        evaluator_findings=[{"severity": "high", "msg": "x"}],
        scope={"files": ["a.py"]},
        modified_files=["a.py", "b.py"],
        budget=BudgetTracker(total_budget=1000, used=250),
        budget_params={"budget_minutes": 30},
        phase_metrics={"plan": {"duration_s": 4}},
        plan_discovery_meta={"winner": "b", "winner_score": 0.9},
        parent_session_id="parent-1",
        complexity_tier="advanced",
        shared_workspace="/tmp/pi-ceo-workspaces/parent-1",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


_PREVIOUSLY_DROPPED = [
    "plan", "repo_context", "evaluator_findings", "scope", "modified_files",
    "budget", "budget_params", "phase_metrics", "plan_discovery_meta",
    "parent_session_id", "complexity_tier", "shared_workspace", "host",
]


def test_checkpoint_persists_every_previously_dropped_field():
    from app.server import session_lease

    payload = session_lease.checkpoint_payload(_rich_session())
    missing = [f for f in _PREVIOUSLY_DROPPED if f not in payload]
    assert missing == [], f"checkpoint still drops: {missing}"
    assert payload["plan"].startswith("## Plan")
    assert payload["modified_files"] == ["a.py", "b.py"]
    assert payload["complexity_tier"] == "advanced"
    assert payload["parent_session_id"] == "parent-1"


def test_checkpoint_serialises_the_live_budget_object():
    """`budget` is a BudgetTracker instance; an unserialisable value would make
    the whole fire-and-forget checkpoint write vanish silently."""
    import json

    from app.server import session_lease

    payload = session_lease.checkpoint_payload(_rich_session())
    assert payload["budget"]["used"] == 250
    json.dumps(payload)  # must not raise — the writer would swallow it if it did


def test_checkpoint_drops_an_unserialisable_field_rather_than_the_row():
    import json

    from app.server import session_lease

    class NoVars:
        __slots__ = ()

    payload = session_lease.checkpoint_payload(_rich_session(scope=NoVars()))
    assert payload["scope"] is None
    json.dumps(payload)


def test_checkpoint_caps_unbounded_fields():
    from app.server import session_lease

    payload = session_lease.checkpoint_payload(_rich_session(
        modified_files=[f"f{i}.py" for i in range(5000)],
        evaluator_findings=[{"i": i} for i in range(5000)],
        plan="x" * 500_000,
    ))
    assert len(payload["modified_files"]) == session_lease._MAX_ITEMS
    assert len(payload["evaluator_findings"]) == session_lease._MAX_ITEMS
    assert len(payload["plan"]) == session_lease._MAX_CHARS


def test_checkpoint_tolerates_a_bare_session():
    from app.server import session_lease

    payload = session_lease.checkpoint_payload(SimpleNamespace(id="x"))
    assert payload["retry_count"] == 0
    assert payload["plan"] == ""
    assert payload["host"]


def test_save_checkpoint_row_renews_the_lease():
    from app.server import supabase_log

    captured = {}
    with patch.object(supabase_log, "_upsert", side_effect=lambda t, r: captured.update(row=r) or True):
        assert supabase_log.save_session_checkpoint(_rich_session()) is True

    row = captured["row"]
    assert row["claimed_by"]
    assert row["lease_expires_at"] > datetime.now(timezone.utc).isoformat(timespec="seconds")
    assert row["checkpoint"]["host"] == row["claimed_by"]


# ── Cross-machine resume: the workspace path ──────────────────────────────────


def test_same_host_keeps_workspace_and_resume_phase():
    from app.server import session_lease, session_recovery

    cp = {"workspace": "/tmp/ws/s1", "host": session_lease.local_host()}
    assert session_recovery.resume_target(cp, "evaluator") == ("/tmp/ws/s1", "evaluator")


def test_foreign_host_blanks_workspace_and_winds_back_to_pre_sandbox():
    """The directory does not exist here, and neither does the generator's work.

    Blanking alone would not be enough: `_should_skip` skips the sandbox phase —
    the one that re-clones a missing workspace — for any resume at or past it.
    """
    from app.server import session_recovery

    cp = {"workspace": "/Users/someone/ws/s1", "host": "other-machine"}
    workspace, resume_from = session_recovery.resume_target(cp, "evaluator")

    assert workspace == ""
    assert resume_from == session_recovery.PRE_SANDBOX_PHASE

    from app.server import session_phases  # noqa: PLC0415

    order = session_phases._PHASE_ORDER
    assert order.index(resume_from) < order.index("sandbox"), (
        "resume_from must sit before 'sandbox' or the re-clone branch is skipped"
    )
    assert not session_phases._should_skip("sandbox", resume_from)


def test_checkpoint_without_host_is_treated_as_local():
    """Rows written before the `host` field existed must still resume."""
    from app.server import session_recovery

    cp = {"workspace": "/tmp/ws/s1"}
    assert session_recovery.resume_target(cp, "plan") == ("/tmp/ws/s1", "plan")


def test_session_from_checkpoint_hydrates_the_new_fields():
    from app.server import session_lease, session_recovery

    cp = session_lease.checkpoint_payload(_rich_session())
    session = session_recovery.session_from_checkpoint(
        "sid-1", {"repo_url": "https://github.com/CleanExpo/Pi-Dev-Ops"}, cp,
    )

    assert session.plan.startswith("## Plan")
    assert session.repo_context == {"languages": ["python"]}
    assert session.evaluator_findings == [{"severity": "high", "msg": "x"}]
    assert session.scope == {"files": ["a.py"]}
    assert session.modified_files == ["a.py", "b.py"]
    assert session.budget_params == {"budget_minutes": 30}
    assert session.phase_metrics == {"plan": {"duration_s": 4}}
    assert session.plan_discovery_meta == {"winner": "b", "winner_score": 0.9}
    assert session.parent_session_id == "parent-1"
    assert session.complexity_tier == "advanced"
    assert session.shared_workspace.endswith("parent-1")
    assert session.workspace == "/tmp/pi-ceo-workspaces/sid-1"  # same host


# ── Recovery honours the lease ────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_sessions():
    from app.server import session_model

    session_model._sessions.clear()
    yield
    session_model._sessions.clear()


def _recover(rows, claim_results):
    from app.server import session_model

    with patch("app.server.supabase_log.fetch_interrupted_sessions", return_value=rows), \
         patch("app.server.supabase_log.claim_interrupted_session", side_effect=claim_results) as claim, \
         patch("app.server.session_phases.run_build", new=AsyncMock(return_value=None)), \
         patch("app.server.session_model.asyncio.create_task") as task:
        task.side_effect = lambda coro: coro.close() or None
        scheduled = session_model.recover_interrupted_sessions_from_supabase(max_concurrent=5)
    return scheduled, claim, task


def _row(sid: str) -> dict:
    return {
        "id": sid,
        "repo_url": "https://github.com/CleanExpo/Pi-Dev-Ops",
        "status": "interrupted",
        "checkpoint": {"last_completed_phase": "generator", "workspace": f"/tmp/ws/{sid}"},
    }


def test_recovery_skips_rows_this_machine_did_not_win():
    from app.server import session_model

    scheduled, _, _ = _recover([_row("s1"), _row("s2")], [False, True])

    assert scheduled == 1
    assert "s1" not in session_model._sessions
    assert "s2" in session_model._sessions


def test_recovery_claims_before_hydrating():
    """A lost claim must not leave a half-built session in `_sessions`."""
    from app.server import session_model

    scheduled, claim, task = _recover([_row("s1")], [False])

    assert scheduled == 0
    assert session_model._sessions == {}
    assert claim.call_count == 1
    assert task.call_count == 0, "no resume task may be scheduled for a lost claim"


def test_recovery_resume_phase_is_wound_back_for_a_foreign_checkpoint():
    from app.server import session_model, session_recovery

    row = _row("s1")
    row["checkpoint"]["host"] = "some-other-box"

    with patch("app.server.supabase_log.fetch_interrupted_sessions", return_value=[row]), \
         patch("app.server.supabase_log.claim_interrupted_session", return_value=True), \
         patch("app.server.session_phases.run_build") as run_build, \
         patch("app.server.session_model.asyncio.create_task", side_effect=lambda c: None):
        session_model.recover_interrupted_sessions_from_supabase(max_concurrent=5)

    assert run_build.call_args.kwargs["resume_from"] == session_recovery.PRE_SANDBOX_PHASE
    assert session_model._sessions["s1"].workspace == ""
