"""
test_autonomy_no_code_filter.py — RA-1495 filter coverage.

Locks the behaviour: the autonomous poller never claims tickets that are
explicitly process / legal / manual-escalation work. The original incident
(DR-535, 2026-04-20) wasted tokens on a non-code ticket; the filter is
the contract that prevents recurrence.
"""
from __future__ import annotations

import pytest

from app.server.autonomy import _should_skip_no_code


def _ticket(*, labels=(), title="x", description="y"):
    return {
        "title": title,
        "description": description,
        "labels": {"nodes": [{"name": n} for n in labels]},
    }


@pytest.mark.parametrize(
    "label",
    ["no-code", "manual-action", "legal", "No-Code", "LEGAL", " legal "],
)
def test_skip_on_label(label):
    """Any of the three reserved labels (case/whitespace-insensitive) skips."""
    skip, reason = _should_skip_no_code(_ticket(labels=[label]))
    assert skip is True
    assert reason is not None and reason.startswith("label:")


def test_skip_on_phrase_in_title():
    skip, reason = _should_skip_no_code(
        _ticket(title="DR-535 — Resolve via legal: not a code change")
    )
    assert skip is True
    assert reason == "phrase:not a code change"


def test_skip_on_phrase_in_description():
    skip, reason = _should_skip_no_code(
        _ticket(description="Owner: Toby. This is a manual escalation, no PR needed.")
    )
    assert skip is True
    assert reason == "phrase:manual escalation"


def test_no_skip_for_normal_engineering_ticket():
    skip, reason = _should_skip_no_code(
        _ticket(
            labels=["bug", "frontend"],
            title="Fix login redirect after OAuth",
            description="Investigate and fix the redirect loop.",
        )
    )
    assert skip is False
    assert reason is None


def test_no_skip_with_empty_labels_and_body():
    skip, reason = _should_skip_no_code(_ticket(labels=[], title="", description=""))
    assert skip is False
    assert reason is None


def test_no_skip_when_phrase_appears_only_with_negation_context():
    """The filter is intentionally simple: literal phrase match. False
    positives on tickets that *discuss* but don't *invoke* manual escalation
    are an accepted trade-off (operator can remove the phrase or add a code-
    triggering label) until the false-positive rate justifies a richer
    parser."""
    skip, _ = _should_skip_no_code(
        _ticket(description="Document the difference between manual escalation paths")
    )
    # By design, this DOES skip. Test asserts the simple-match contract.
    assert skip is True
