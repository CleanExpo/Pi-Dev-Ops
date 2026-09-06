"""The ship gate must not report tests_passed=True without test evidence.

RA-7433 audit finding. `_log_ship_gate_check` wrote the literal True with the
comment "reached here only if sandbox succeeded". `_phase_sandbox` runs no
tests: it checks the workspace directory exists, re-clones if it does not, and
returns True. It also returns True when the phase is SKIPPED. So the gate row
recorded "tests passed" on the strength of a directory check.

A literal cannot go red. These tests fail if the literal comes back.
"""
from types import SimpleNamespace
from unittest.mock import patch

from app.server import session_phases


def _capture(session, **kw):
    captured = {}
    with patch.object(session_phases, "log_gate_check",
                      side_effect=lambda **k: captured.update(k)):
        session_phases._log_ship_gate_check(session, **kw)
    return captured


def _session(**kw):
    base = dict(
        id="sid-1", workspace="/nonexistent", evaluator_status="passed",
        evaluator_score=9.0, evaluator_confidence=88.0, scope_adhered=True,
        modified_files=["a.py"], started_at=1700000000.0, linear_issue_id=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_no_test_evidence_is_not_a_pass():
    """Nothing in the pipeline sets test evidence today, so the honest value is False."""
    captured = _capture(_session(), push_ok=True, push_ts=1700000600.0)
    assert captured["gate_checks"]["tests_passed"] is False, (
        "tests_passed must reflect real test evidence, not a literal"
    )


def test_explicit_failure_is_reported_as_failure():
    captured = _capture(_session(tests_passed=False), push_ok=True, push_ts=1700000600.0)
    assert captured["gate_checks"]["tests_passed"] is False


def test_explicit_pass_is_reported_as_pass():
    """The field must still be able to go green — a control that can only say
    False is as useless as one that can only say True."""
    captured = _capture(_session(tests_passed=True), push_ok=True, push_ts=1700000600.0)
    assert captured["gate_checks"]["tests_passed"] is True
