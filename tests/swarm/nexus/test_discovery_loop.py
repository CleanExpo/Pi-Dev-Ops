"""Focused tests for swarm.nexus.discovery_loop + loop_runner."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from swarm.nexus.discovery_loop import (
    MAX_OUTCOMES_PER_CYCLE,
    parse_cadence,
    run_discovery_cycle,
)
from swarm.nexus.loop_runner import run_due_loops
from swarm.nexus.outcomes import InMemoryOutcomesStore
from swarm.nexus.types import Loop, Outcome


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
        self.calls: list[tuple[str, str]] = []

    def complete(self, *, system, user, max_tokens=1024, temperature=0.3):
        self.calls.append((system, user))
        if isinstance(self._resp, Exception):
            raise self._resp
        if isinstance(self._resp, str):
            return self._resp
        return json.dumps(self._resp)


class StubLoopsStore:
    def __init__(self, due: list[Loop]):
        self.due = list(due)
        self.saved: list[Loop] = []

    def list_due(self, *, now: datetime) -> list[Loop]:
        return list(self.due)

    def save(self, loop: Loop) -> Loop:
        self.saved.append(loop)
        return loop


# ============================================================
# Fixtures
# ============================================================


NOW = datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc)


def _loop(**overrides) -> Loop:
    defaults: dict = dict(
        id="lp-1",
        workspace_id="ws-1",
        workspace_slug="acme",
        loop_kind="discovery",
        cadence="7d",
        enabled=True,
        last_run_at=(NOW - timedelta(days=8)).isoformat(),
        next_run_at=(NOW - timedelta(minutes=5)).isoformat(),
    )
    defaults.update(overrides)
    return Loop(**defaults)


def _outcome(*, when: datetime, **kw) -> Outcome:
    base = dict(
        id=kw.pop("id", f"out-{when.timestamp():.0f}"),
        workspace_id="ws-1",
        workspace_slug="acme",
        source="stripe",
        metric="mrr",
        captured_at=when.isoformat(),
        value_numeric=199.0,
    )
    base.update(kw)
    return Outcome(**base)


GOOD_BRIEF = {
    "brief": "MRR ticked up 3% week-over-week, deploys steady.",
    "top_signals": [
        {"id": "out-1", "why_it_matters": "First paying customer this week."}
    ],
    "recommended_action": "Send the founder a celebratory note.",
    "recommended_loop": "kpi",
}


# ============================================================
# parse_cadence
# ============================================================


class TestCadence:
    def test_24h(self):
        assert parse_cadence("24h") == timedelta(hours=24)

    def test_7d(self):
        assert parse_cadence("7d") == timedelta(days=7)

    def test_30d(self):
        assert parse_cadence("30d") == timedelta(days=30)

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="invalid cadence"):
            parse_cadence("90d")


# ============================================================
# run_discovery_cycle
# ============================================================


class TestRunDiscoveryCycle:
    def test_happy_path(self):
        store = InMemoryOutcomesStore()
        store.write(_outcome(when=NOW - timedelta(hours=2)))
        llm = StubLLM(GOOD_BRIEF)
        result = run_discovery_cycle(
            _loop(), llm=llm, outcomes_store=store, clock=FixedClock(NOW),
        )
        assert result.result == "ok"
        assert result.outcomes_consumed == 1
        assert result.brief_outcome_id is not None
        # The brief is persisted as an Outcome row:
        rows = store.list(workspace_slug="acme")
        assert any(r.metric == "discovery_brief" for r in rows)
        # next_run_at is +cadence from now:
        assert result.next_run_at.startswith("2026-06-02")  # +7d

    def test_no_outcomes_short_circuits(self):
        store = InMemoryOutcomesStore()
        llm = StubLLM(GOOD_BRIEF)
        result = run_discovery_cycle(
            _loop(), llm=llm, outcomes_store=store, clock=FixedClock(NOW),
        )
        assert result.result == "no_outcomes"
        assert result.outcomes_consumed == 0
        assert llm.calls == [], "LLM should not be called when there are no outcomes"

    def test_outcomes_outside_window_excluded(self):
        store = InMemoryOutcomesStore()
        # one outcome 10 days old (outside the 7d window)
        store.write(_outcome(when=NOW - timedelta(days=10)))
        llm = StubLLM(GOOD_BRIEF)
        # loop has last_run_at 8 days ago, so window starts 8 days ago — but
        # the test outcome at 10d is older than that.
        result = run_discovery_cycle(
            _loop(), llm=llm, outcomes_store=store, clock=FixedClock(NOW),
        )
        assert result.result == "no_outcomes"

    def test_llm_exception_returns_llm_error(self):
        store = InMemoryOutcomesStore()
        store.write(_outcome(when=NOW - timedelta(hours=1)))
        llm = StubLLM(ConnectionError("anthropic 503"))
        result = run_discovery_cycle(
            _loop(), llm=llm, outcomes_store=store, clock=FixedClock(NOW),
        )
        assert result.result == "llm_error"
        assert result.outcomes_consumed == 1
        assert result.next_run_at  # still advances

    def test_llm_malformed_json_returns_llm_error(self):
        store = InMemoryOutcomesStore()
        store.write(_outcome(when=NOW - timedelta(hours=1)))
        llm = StubLLM("not json at all")
        result = run_discovery_cycle(
            _loop(), llm=llm, outcomes_store=store, clock=FixedClock(NOW),
        )
        assert result.result == "llm_error"

    def test_llm_missing_brief_key_returns_llm_error(self):
        store = InMemoryOutcomesStore()
        store.write(_outcome(when=NOW - timedelta(hours=1)))
        llm = StubLLM({"oops": "no brief field"})
        result = run_discovery_cycle(
            _loop(), llm=llm, outcomes_store=store, clock=FixedClock(NOW),
        )
        assert result.result == "llm_error"

    def test_max_outcomes_per_cycle_cap_passed_to_store(self):
        store = InMemoryOutcomesStore()
        # Write more than the cap; in-memory store respects limit kw.
        for i in range(MAX_OUTCOMES_PER_CYCLE + 50):
            store.write(_outcome(
                id=f"o{i}",
                when=NOW - timedelta(minutes=i + 1),
            ))
        llm = StubLLM(GOOD_BRIEF)
        result = run_discovery_cycle(
            _loop(), llm=llm, outcomes_store=store, clock=FixedClock(NOW),
            max_outcomes=MAX_OUTCOMES_PER_CYCLE,
        )
        assert result.result == "ok"
        assert result.outcomes_consumed == MAX_OUTCOMES_PER_CYCLE

    def test_invalid_cadence_returns_invalid_cadence(self):
        store = InMemoryOutcomesStore()
        llm = StubLLM(GOOD_BRIEF)
        result = run_discovery_cycle(
            _loop(cadence="banana"),
            llm=llm, outcomes_store=store, clock=FixedClock(NOW),
        )
        assert result.result == "invalid_cadence"

    def test_loop_with_no_last_run_uses_default_window(self):
        """When last_run_at is None, the cycle should still execute against the default 7d window."""
        store = InMemoryOutcomesStore()
        store.write(_outcome(when=NOW - timedelta(hours=2)))
        llm = StubLLM(GOOD_BRIEF)
        loop = _loop(last_run_at=None)
        result = run_discovery_cycle(
            loop, llm=llm, outcomes_store=store, clock=FixedClock(NOW),
        )
        assert result.result == "ok"


# ============================================================
# run_due_loops
# ============================================================


class TestRunDueLoops:
    def test_processes_due_discovery_loop(self):
        store = InMemoryOutcomesStore()
        store.write(_outcome(when=NOW - timedelta(hours=1)))
        loop = _loop()
        loops_store = StubLoopsStore(due=[loop])
        summary = run_due_loops(
            loops_store=loops_store,
            outcomes_store=store,
            llm=StubLLM(GOOD_BRIEF),
            clock=FixedClock(NOW),
        )
        assert summary.processed == 1
        assert summary.ok == 1
        assert len(loops_store.saved) == 1
        # last_run_at was advanced to NOW
        assert loops_store.saved[0].last_run_at == NOW.isoformat()

    def test_skips_non_discovery_kinds(self):
        loop = _loop(loop_kind="content")
        loops_store = StubLoopsStore(due=[loop])
        summary = run_due_loops(
            loops_store=loops_store,
            outcomes_store=InMemoryOutcomesStore(),
            llm=StubLLM(GOOD_BRIEF),
            clock=FixedClock(NOW),
        )
        assert summary.processed == 0
        assert loops_store.saved == []  # untouched

    def test_invalid_cadence_does_not_update_loop(self):
        loop = _loop(cadence="banana")
        loops_store = StubLoopsStore(due=[loop])
        summary = run_due_loops(
            loops_store=loops_store,
            outcomes_store=InMemoryOutcomesStore(),
            llm=StubLLM(GOOD_BRIEF),
            clock=FixedClock(NOW),
        )
        assert summary.invalid_cadence == 1
        assert loops_store.saved == []
