"""
test_budget_tracker_wired.py — RA-1682 BudgetTracker actually records spend.

Locks the contract that every evaluator round contributes to the session's
BudgetTracker. Before this PR, `session.budget` existed but `.record()` was
never called, so `session.budget.used` always returned 0 — useless for any
budget-aware decision.
"""
from __future__ import annotations

from src.tao.budget.tracker import BudgetTracker
from app.server.session_model import BuildSession, _sessions
from app.server.session_evaluator import _record_evaluator_tokens


def test_record_updates_session_budget():
    sid = "test-budget-1"
    session = BuildSession(id=sid)
    session.budget = BudgetTracker(total_budget=10_000)
    _sessions[sid] = session
    try:
        _record_evaluator_tokens(sid, "sonnet", input_tokens=1500, output_tokens=300)
        assert session.budget.used == 1800
        assert session.budget.per_tier == {"sonnet": 1800}
        assert session.budget.remaining() == 8200
    finally:
        _sessions.pop(sid, None)


def test_record_accumulates_across_calls():
    sid = "test-budget-2"
    session = BuildSession(id=sid)
    session.budget = BudgetTracker(total_budget=10_000)
    _sessions[sid] = session
    try:
        _record_evaluator_tokens(sid, "sonnet", 1000, 200)
        _record_evaluator_tokens(sid, "sonnet", 500, 100)
        _record_evaluator_tokens(sid, "haiku",   400,  50)
        assert session.budget.used == 2250
        assert session.budget.per_tier == {"sonnet": 1800, "haiku": 450}
    finally:
        _sessions.pop(sid, None)


def test_record_no_session_id_is_noop():
    """Empty session_id (eg. one-off probe) must not raise or mutate state."""
    _record_evaluator_tokens("", "sonnet", 100, 100)  # must not raise


def test_record_unknown_session_is_noop():
    """Session GC'd between request and response must not raise."""
    _record_evaluator_tokens("nonexistent-sid", "sonnet", 100, 100)


def test_record_session_without_budget_is_noop():
    """Sessions that bypassed plan phase have no .budget — graceful skip."""
    sid = "test-budget-3"
    session = BuildSession(id=sid)  # session.budget defaults to None
    _sessions[sid] = session
    try:
        _record_evaluator_tokens(sid, "sonnet", 100, 100)  # must not raise
        assert session.budget is None  # unchanged
    finally:
        _sessions.pop(sid, None)


def test_record_swallows_tracker_errors():
    """A buggy tracker .record() must not break the evaluator hot path."""
    sid = "test-budget-4"
    session = BuildSession(id=sid)

    class BrokenTracker:
        def record(self, *_a, **_kw):
            raise ValueError("simulated tracker bug")

    session.budget = BrokenTracker()
    _sessions[sid] = session
    try:
        _record_evaluator_tokens(sid, "sonnet", 100, 100)  # must not raise
    finally:
        _sessions.pop(sid, None)
