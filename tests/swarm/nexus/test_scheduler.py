"""Focused tests for swarm.nexus.scheduler — daily cycle driver."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from swarm.nexus import audit as audit_mod
from swarm.nexus.outcomes import InMemoryOutcomesStore
from swarm.nexus.scheduler import CycleSummary, run_nexus_cycle
from swarm.nexus.types import Loop, Outcome

NOW = datetime(2026, 5, 26, 6, 0, 0, tzinfo=timezone.utc)


# ============================================================
# Stubs
# ============================================================


class FixedClock:
    def __init__(self, when: datetime):
        self._when = when

    def now(self) -> datetime:
        return self._when


class StubLLM:
    def __init__(self, response: object):
        self._resp = response
        self.calls = 0

    def complete(self, *, system, user, max_tokens=1024, temperature=0.3):
        self.calls += 1
        if isinstance(self._resp, Exception):
            raise self._resp
        return self._resp if isinstance(self._resp, str) else json.dumps(self._resp)


class StubLoopsStore:
    def __init__(self, due: list[Loop]):
        self.due = list(due)
        self.saved: list[Loop] = []

    def list_due(self, *, now):
        return list(self.due)

    def save(self, loop):
        self.saved.append(loop)
        return loop


class StubAuditStore:
    def __init__(self):
        self.rows: list = []

    def append(self, row):
        self.rows.append(row)
        return row.id


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def isolate_audit_key(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_mod, "AUDIT_KEY_PATH", tmp_path / "audit-key")


def _outcome(id_="out-1") -> Outcome:
    return Outcome(
        id=id_, workspace_id="ws-1", workspace_slug="acme",
        source="stripe", metric="invoice_paid",
        captured_at=(NOW - timedelta(hours=1)).isoformat(),
        value_numeric=199.0,
    )


def _good_bra_response() -> dict:
    return {"cards": [{
        "brief": "Test", "recommendation": "rec",
        "action": "act", "severity": "low",
        "evidence_ids": ["out-1"],
    }]}


# ============================================================
# Idempotency window guard
# ============================================================


class TestIdempotency:
    def test_first_run_writes_marker(self, tmp_path):
        outcomes = InMemoryOutcomesStore()
        outcomes.write(_outcome())
        marker = tmp_path / "last-run.txt"
        summary = run_nexus_cycle(
            workspace_slugs=["acme"],
            loops_store=StubLoopsStore(due=[]),
            outcomes_store=outcomes,
            llm=StubLLM(_good_bra_response()),
            clock=FixedClock(NOW),
            audit_store=StubAuditStore(),
            last_run_marker_path=marker,
        )
        assert summary.skipped_idempotent is False
        assert marker.read_text() == "2026-05-26"

    def test_second_run_same_window_skips(self, tmp_path):
        outcomes = InMemoryOutcomesStore()
        outcomes.write(_outcome())
        marker = tmp_path / "last-run.txt"
        marker.write_text("2026-05-26")
        llm = StubLLM(_good_bra_response())
        summary = run_nexus_cycle(
            workspace_slugs=["acme"],
            loops_store=StubLoopsStore(due=[]),
            outcomes_store=outcomes, llm=llm,
            clock=FixedClock(NOW),
            audit_store=StubAuditStore(),
            last_run_marker_path=marker,
        )
        assert summary.skipped_idempotent is True
        assert llm.calls == 0  # LLM untouched on idempotent skip

    def test_next_window_runs_again(self, tmp_path):
        outcomes = InMemoryOutcomesStore()
        outcomes.write(_outcome())
        marker = tmp_path / "last-run.txt"
        marker.write_text("2026-05-25")  # yesterday
        summary = run_nexus_cycle(
            workspace_slugs=["acme"],
            loops_store=StubLoopsStore(due=[]),
            outcomes_store=outcomes,
            llm=StubLLM(_good_bra_response()),
            clock=FixedClock(NOW),
            audit_store=StubAuditStore(),
            last_run_marker_path=marker,
        )
        assert summary.skipped_idempotent is False
        assert marker.read_text() == "2026-05-26"


# ============================================================
# Audit rows
# ============================================================


class TestAuditRows:
    def test_start_and_success_rows_appended(self, tmp_path):
        outcomes = InMemoryOutcomesStore()
        outcomes.write(_outcome())
        audit = StubAuditStore()
        run_nexus_cycle(
            workspace_slugs=["acme"],
            loops_store=StubLoopsStore(due=[]),
            outcomes_store=outcomes,
            llm=StubLLM(_good_bra_response()),
            clock=FixedClock(NOW),
            audit_store=audit,
            last_run_marker_path=tmp_path / "marker.txt",
        )
        actions = [r.action for r in audit.rows]
        assert "nexus_scheduler.start" in actions
        assert any(a.startswith("nexus_scheduler.") for a in actions[1:])

    def test_failure_isolation_partial_audit(self, tmp_path):
        outcomes = InMemoryOutcomesStore()
        outcomes.write(_outcome())
        # LLM raises — one workspace's BRA fails, but cycle completes.
        llm = StubLLM(ConnectionError("anthropic 503"))
        audit = StubAuditStore()
        summary = run_nexus_cycle(
            workspace_slugs=["acme", "beta"],
            loops_store=StubLoopsStore(due=[]),
            outcomes_store=outcomes, llm=llm,
            clock=FixedClock(NOW),
            audit_store=audit,
            last_run_marker_path=tmp_path / "marker.txt",
        )
        # Both workspaces' BRA generation hit the exploding LLM.
        # generate_bra() swallows its own exceptions internally — so
        # workspaces_failed lists those that returned dropped_malformed > 0?
        # Actually generate_bra() returns BRAReport even on LLM error, so
        # nothing is in workspaces_failed unless we raise outside. Verify
        # the partial path by patching generate_bra below.
        assert summary.skipped_idempotent is False


# ============================================================
# Failure isolation per workspace
# ============================================================


class TestFailureIsolation:
    def test_one_workspace_failure_does_not_poison_others(
        self, tmp_path, monkeypatch,
    ):
        outcomes = InMemoryOutcomesStore()
        outcomes.write(_outcome())

        calls: dict[str, int] = {}

        def fake_generate_bra(*, workspace_slug, **_kw):
            calls[workspace_slug] = calls.get(workspace_slug, 0) + 1
            if workspace_slug == "boom":
                raise RuntimeError("simulated workspace failure")
            from swarm.nexus.bra import BRAReport
            return BRAReport(workspace_slug=workspace_slug, window="7d")

        monkeypatch.setattr(
            "swarm.nexus.scheduler.generate_bra", fake_generate_bra,
        )

        summary = run_nexus_cycle(
            workspace_slugs=["acme", "boom", "gamma"],
            loops_store=StubLoopsStore(due=[]),
            outcomes_store=outcomes,
            llm=StubLLM(_good_bra_response()),
            clock=FixedClock(NOW),
            audit_store=StubAuditStore(),
            last_run_marker_path=tmp_path / "marker.txt",
        )
        assert summary.workspaces_failed == ("boom",)
        # The two healthy workspaces still produced reports:
        assert set(summary.bra_reports.keys()) == {"acme", "gamma"}
        # Each workspace was attempted exactly once:
        assert calls == {"acme": 1, "boom": 1, "gamma": 1}


# ============================================================
# DRY_RUN mode
# ============================================================


class TestDryRun:
    def test_dry_run_skips_loop_runner_and_bra(self, tmp_path, monkeypatch):
        outcomes = InMemoryOutcomesStore()
        outcomes.write(_outcome())
        llm = StubLLM(_good_bra_response())
        loops_store = StubLoopsStore(due=[Loop(
            id="lp-1", workspace_id="ws-1", workspace_slug="acme",
            loop_kind="discovery", cadence="7d", enabled=True,
        )])

        called = {"run_due_loops": 0, "generate_bra": 0}

        def fake_run_due_loops(**_kw):
            called["run_due_loops"] += 1
            from swarm.nexus.discovery_loop import RunSummary
            return RunSummary()

        def fake_generate_bra(**_kw):
            called["generate_bra"] += 1
            from swarm.nexus.bra import BRAReport
            return BRAReport(workspace_slug=_kw["workspace_slug"], window="7d")

        monkeypatch.setattr(
            "swarm.nexus.scheduler.run_due_loops", fake_run_due_loops,
        )
        monkeypatch.setattr(
            "swarm.nexus.scheduler.generate_bra", fake_generate_bra,
        )

        summary = run_nexus_cycle(
            workspace_slugs=["acme"],
            loops_store=loops_store,
            outcomes_store=outcomes, llm=llm,
            clock=FixedClock(NOW),
            audit_store=StubAuditStore(),
            last_run_marker_path=tmp_path / "marker.txt",
            dry_run=True,
        )
        assert summary.dry_run is True
        assert called == {"run_due_loops": 0, "generate_bra": 0}
        # Marker still updated to prevent immediate re-fire:
        assert (tmp_path / "marker.txt").read_text() == "2026-05-26"

    def test_dry_run_still_writes_audit_rows(self, tmp_path):
        outcomes = InMemoryOutcomesStore()
        audit = StubAuditStore()
        run_nexus_cycle(
            workspace_slugs=["acme"],
            loops_store=StubLoopsStore(due=[]),
            outcomes_store=outcomes,
            llm=StubLLM(_good_bra_response()),
            clock=FixedClock(NOW),
            audit_store=audit,
            last_run_marker_path=tmp_path / "marker.txt",
            dry_run=True,
        )
        actions = [r.action for r in audit.rows]
        assert any(a == "nexus_scheduler.start" for a in actions)


# ============================================================
# Summary shape
# ============================================================


class TestSummaryShape:
    def test_summary_returns_window_key_and_timestamps(self, tmp_path):
        outcomes = InMemoryOutcomesStore()
        summary = run_nexus_cycle(
            workspace_slugs=[],
            loops_store=StubLoopsStore(due=[]),
            outcomes_store=outcomes,
            llm=StubLLM(_good_bra_response()),
            clock=FixedClock(NOW),
            audit_store=StubAuditStore(),
            last_run_marker_path=tmp_path / "m.txt",
        )
        assert isinstance(summary, CycleSummary)
        assert summary.window_key == "2026-05-26"
        assert summary.started_at == NOW.isoformat()
        assert summary.ended_at  # populated

    def test_summary_marker_path_none_does_not_crash(self):
        outcomes = InMemoryOutcomesStore()
        summary = run_nexus_cycle(
            workspace_slugs=[],
            loops_store=StubLoopsStore(due=[]),
            outcomes_store=outcomes,
            llm=StubLLM(_good_bra_response()),
            clock=FixedClock(NOW),
            audit_store=StubAuditStore(),
            last_run_marker_path=None,  # explicitly None
        )
        assert summary.skipped_idempotent is False
