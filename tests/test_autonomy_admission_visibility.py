"""UNI-2742 — a ticket dropped at admission must be visible in the server's logs.

`generation_blocked` returns early for every polled issue when the host cannot run
the SDK. It recorded the drop only via the `emit` callback, which writes to the
JSONL event log and a 20-entry memory ring -- never to stdout. Every sibling branch
of the per-issue path does log (`autonomy.py:959`, `:982`, `:1008`, `:882`), so this
was the one early return that left no trace an operator could read.

Production consequence: the poller logged "processing UNI-2726 / UNI-2638 / UNI-2661"
and then nothing at all, which is indistinguishable from a quiet, healthy pass.
"""
import logging

import pytest

from app.server import autonomy_evidence

_BLOCKER = "execution_blocked: required sandbox dependencies are unavailable"


@pytest.fixture
def blocked_host(monkeypatch):
    monkeypatch.setattr(
        "app.server.session_sdk.generation_readiness",
        lambda: {"status": "blocked", "blockers": [_BLOCKER]},
    )


def test_admission_drop_logs_a_warning(blocked_host, caplog):
    events = []
    with caplog.at_level(logging.WARNING, logger="pi-ceo.autonomy"):
        assert autonomy_evidence.generation_blocked("UNI-2742", events.append) is True

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "admission drop emitted no WARNING - the drop is invisible in stdout"
    message = " ".join(r.getMessage() for r in warnings)
    assert "UNI-2742" in message, f"warning does not name the dropped ticket: {message!r}"
    assert "sandbox dependencies" in message, f"warning does not name the blocker: {message!r}"


def test_admission_drop_still_emits_the_jsonl_event(blocked_host):
    """Regression guard: adding the log must not replace the structured evidence."""
    events = []
    assert autonomy_evidence.generation_blocked("UNI-2742", events.append) is True
    assert [e["action"] for e in events] == ["session_blocked"]
    assert events[0]["ticket"] == "UNI-2742"
    assert events[0]["blockers"] == [_BLOCKER]


def test_unblocked_host_neither_logs_nor_emits(monkeypatch, caplog):
    """Negative control: the warning fires only on a real drop, not on every poll."""
    monkeypatch.setattr(
        "app.server.session_sdk.generation_readiness",
        lambda: {"status": "unverified", "blockers": []},
    )
    events = []
    with caplog.at_level(logging.WARNING, logger="pi-ceo.autonomy"):
        assert autonomy_evidence.generation_blocked("UNI-2742", events.append) is False
    assert events == []
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []
