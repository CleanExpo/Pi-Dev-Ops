"""RA-7546 critic bar — blocked is terminal; IncompleteRead must not drop."""
from __future__ import annotations

import http.client
import json

import pytest

from scripts.smoke_pipeline_client import Session, drain_sse
from scripts.smoke_pipeline_resilience import (
    SESSION_TERMINAL,
    is_terminal_status,
    logs_stream_path,
    row_entered_generate,
    terminal_fail_message,
)
from scripts.smoke_test_pipeline import (
    PipelineAssertions,
    _observe_row,
    poll_terminal,
    watch_stream,
)


def test_logs_stream_path_uses_heartbeat_route():
    assert logs_stream_path("b72988e2f8f4") == "/api/sessions/b72988e2f8f4/logs/stream"


def test_list_sessions_exposes_error_for_blocked_fail_text():
    from pathlib import Path

    text = Path("app/server/session_model.py").read_text(encoding="utf-8")
    assert '"error": s.error' in text
    kill = Path("app/server/sessions.py").read_text(encoding="utf-8")
    assert "if not s or not s.process:" not in kill


def test_blocked_is_terminal_for_smoke_classify():
    """Critic bar 1: blocked must classify as terminal, not 'still running'."""
    assert "blocked" in SESSION_TERMINAL
    assert is_terminal_status("blocked") is True
    assert is_terminal_status("building") is False
    assert is_terminal_status("cloning") is False
    assert is_terminal_status("stalled") is True


def test_row_entered_generate_from_last_phase_plan():
    assert row_entered_generate({"last_phase": "plan"}) is True
    assert row_entered_generate({"last_phase": "sandbox"}) is False
    assert row_entered_generate({"last_phase": "", "phase_metrics": {"generate": {}}}) is True


def test_drain_sse_parses_complete_events_and_keeps_tail():
    buf = (
        'data: {"type":"phase","text":"[3.7/5] Planning implementation (sonnet)..."}\n\n'
        'data: {"type":"error","text":"Plan blocked: planner returned exit status 1"}\n\n'
        "data: {\"type\":\"partial\""
    )
    events, rest = drain_sse(buf)
    assert [e["type"] for e in events] == ["phase", "error"]
    assert "Plan blocked" in events[1]["text"]
    assert rest.startswith("data: {")


def test_incomplete_read_partial_is_not_discarded():
    """urllib IncompleteRead.partial must still parse as SSE (run 34790637141)."""
    payload = (
        b'data: {"type":"error","text":"Plan blocked: planner returned exit status 1"}\n\n'
        b"trailing-incomplete"
    )
    exc = http.client.IncompleteRead(payload)
    events, rest = drain_sse((exc.partial or b"").decode("utf-8"))
    assert events[0]["type"] == "error"
    assert rest == "trailing-incomplete"


class _PartialBody:
    """HTTP body that dies mid-SSE the way Railway dropped /logs."""

    def read(self, _n: int) -> bytes:
        raise http.client.IncompleteRead(
            b'data: {"type":"error","text":"Plan blocked: planner returned exit status 1"}\n\n'
        )

    def __enter__(self) -> "_PartialBody":
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False


def test_session_stream_drains_incomplete_read_partial():
    """Critic bar 2: Session.stream yields exc.partial, then re-raises."""
    session = Session("http://example.test")
    session.opener = type("Opener", (), {"open": lambda *_a, **_k: _PartialBody()})()
    events: list[dict] = []
    with pytest.raises(http.client.IncompleteRead):
        events.extend(session.stream("/api/sessions/b72988e2/logs/stream", timeout_s=5))
    assert events[0]["type"] == "error"
    assert "Plan blocked" in events[0]["text"]


def test_watch_stream_keeps_partial_before_classify():
    """watch_stream must observe drained events before falling back to poll."""
    class _Drop:
        def stream(self, path: str, timeout_s: int):
            assert path.endswith("/logs/stream")
            yield {"type": "error", "text": "Plan blocked: planner returned exit status 1"}
            raise http.client.IncompleteRead(b"x")

    pa = PipelineAssertions()
    watch_stream(_Drop(), "b72988e2f8f4", pa, start=0.0)
    assert any("Plan blocked" in line for line in pa.diagnostics)
    assert pa.entered_generate is False


class _PollSession:
    def __init__(self, gets: list[tuple[int, str]]):
        self._gets = list(gets)

    def get(self, _path: str) -> tuple[int, str]:
        return self._gets.pop(0)


def _health(uptime: int = 200) -> tuple[int, str]:
    return 200, json.dumps({"status": "ok", "uptime_s": uptime})


def test_poll_blocked_is_terminal_not_still_running(monkeypatch):
    """Critic bar 1: poll returns on blocked without sleeping the 770s budget."""
    monkeypatch.setattr(
        "scripts.smoke_test_pipeline.time.sleep",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("poll hung on blocked")),
    )
    row = {
        "id": "b72988e2f8f4",
        "status": "blocked",
        "last_phase": "sandbox",
        "lines": 18,
        "error": "Plan blocked: planner returned exit status 1",
    }
    session = _PollSession(gets=[_health(), (200, json.dumps([row]))])
    pa = PipelineAssertions()
    assert poll_terminal(session, "b72988e2f8f4", pa, start=10**12) == "terminal"
    assert pa.last_status == "blocked"
    assert pa.entered_generate is False
    assert any("terminal=blocked last_phase=sandbox" in err for err in pa.errors)
    assert any("planner returned exit status 1" in err for err in pa.errors)


def test_terminal_fail_message_includes_phase_and_error():
    msg = terminal_fail_message({
        "status": "blocked",
        "last_phase": "sandbox",
        "error": "Plan blocked: planner returned exit status 1",
    })
    assert msg == (
        "session terminal=blocked last_phase=sandbox "
        "error=Plan blocked: planner returned exit status 1"
    )
    assert terminal_fail_message({"status": "failed", "last_phase": "clone"}) == (
        "session terminal=failed last_phase=clone"
    )


def test_poll_recovers_a2_from_last_phase_after_stream_drop():
    row = {
        "id": "b72988e2f8f4",
        "status": "complete",
        "last_phase": "plan",
        "lines": 22,
        "files_modified": 1,
    }
    session = _PollSession(gets=[_health(), (200, json.dumps([row]))])
    pa = PipelineAssertions()
    assert poll_terminal(session, "b72988e2f8f4", pa, start=10**12) == "terminal"
    assert pa.entered_generate is True
    assert pa.reached_complete is True


def test_observe_row_sets_a2_from_last_phase_without_stream_event():
    pa = PipelineAssertions()
    _observe_row(pa, {"status": "building", "last_phase": "plan", "lines": 20}, 12.0)
    assert pa.entered_generate is True
    assert pa.entered_generate_at == 12.0
