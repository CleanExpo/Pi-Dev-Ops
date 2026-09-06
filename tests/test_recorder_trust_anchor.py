"""Trust anchor must not default to "passed" when no test evidence exists.

RA-7433 audit finding. `session_recorder` read `sandbox_ok` with a default of
True and nothing in the tree ever set it, so every recorded episode carried
tests_passed=True and verified collapsed to "the run finished". Verified rows
are eligible for context injection, so unproven work fed back in as proven.

The seam is `_trust_verdict`: it takes a session and returns the pair the row
is built from, so the decision can be tested without Supabase.
"""
import pytest

from app.server.session_recorder import _trust_verdict


class _Session:
    def __init__(self, **kw):
        self.status = kw.pop("status", "complete")
        for k, v in kw.items():
            setattr(self, k, v)


def test_absent_evidence_is_not_a_pass():
    """No sandbox_ok attribute at all means unknown, and unknown is not passed."""
    tests_passed, verified = _trust_verdict(_Session())
    assert tests_passed is False, "absent test evidence must not read as passed"
    assert verified is False, "a session with no test evidence must not be verified"


def test_explicit_failure_is_not_verified():
    tests_passed, verified = _trust_verdict(_Session(sandbox_ok=False))
    assert tests_passed is False
    assert verified is False


def test_explicit_pass_on_complete_run_is_verified():
    tests_passed, verified = _trust_verdict(_Session(sandbox_ok=True))
    assert tests_passed is True
    assert verified is True


def test_explicit_pass_on_failed_run_is_not_verified():
    s = _Session(status="failed", sandbox_ok=True)
    tests_passed, verified = _trust_verdict(s)
    assert tests_passed is True
    assert verified is False, "an incomplete run is never verified"


def test_none_is_unknown_not_passed():
    tests_passed, verified = _trust_verdict(_Session(sandbox_ok=None))
    assert tests_passed is False
    assert verified is False
