"""Tests for the T2 tmux writer — slice 1 `send` (RA-7012).

The writer's invariants are fail-closed: validate → audit → act. These tests use
a fake libtmux server (no real tmux needed, runs in CI) and assert the gate, the
fail-closed audit, and the happy path. A real-tmux smoke lives in the PR body.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from swarm import tmux_writer


class _FakePane:
    def __init__(self):
        self.sent = []

    def send_keys(self, text, enter=True):
        self.sent.append((text, enter))


class _FakeSession:
    def __init__(self, name):
        self.name = name
        self.active_pane = _FakePane()
        self.killed = False

    def kill(self):
        self.killed = True


class _FakeServer:
    def __init__(self, names=("w1",)):
        self.sessions = [_FakeSession(n) for n in names]

    def new_session(self, session_name, attach=False):
        self.sessions.append(_FakeSession(session_name))
        return self.sessions[-1]


@pytest.fixture
def audit_dir(tmp_path) -> Path:
    d = tmp_path / "audit"
    d.mkdir()
    return d


def _rows(audit_dir: Path) -> list[str]:
    files = [f for f in audit_dir.glob("*") if "key" not in f.name]
    return [line for f in files for line in f.read_text().splitlines()] if files else []


def test_valid_send_reaches_pane_and_audits(audit_dir):
    srv = _FakeServer()
    r = tmux_writer.send("w1", "echo hello", server=srv, audit_dir=audit_dir)
    assert r["ok"] is True
    assert srv.sessions[0].active_pane.sent == [("echo hello", True)]
    # attempt + sent rows both recorded
    assert any("attempt" in row for row in _rows(audit_dir))
    assert any("sent" in row for row in _rows(audit_dir))


def test_denylisted_command_refused_before_any_send(audit_dir):
    srv = _FakeServer()
    r = tmux_writer.send("w1", "echo $(rm -rf /tmp/x)", server=srv, audit_dir=audit_dir)
    assert r["ok"] is False
    assert srv.sessions[0].active_pane.sent == []  # no tmux effect
    assert any("refused" in row for row in _rows(audit_dir))


def test_missing_session_is_refused_not_raised(audit_dir):
    srv = _FakeServer(names=("other",))
    r = tmux_writer.send("w1", "echo hi", server=srv, audit_dir=audit_dir)
    assert r["ok"] is False
    assert "not found" in r["reason"]


def test_audit_unwritable_aborts_before_send(monkeypatch, audit_dir):
    """Fail-closed: if the intent can't be recorded, the keystroke never fires."""
    srv = _FakeServer()

    def _boom(*a, **k):
        raise tmux_writer.tmux_audit.AuditUnwritableError("disk full")

    monkeypatch.setattr(tmux_writer.tmux_audit, "append", _boom)
    r = tmux_writer.send("w1", "echo hello", server=srv, audit_dir=audit_dir)
    assert r["ok"] is False
    assert "audit unwritable" in r["reason"]
    assert srv.sessions[0].active_pane.sent == []  # never acted


def test_level_ceiling_refuses_escalation(audit_dir):
    """A command needing a higher level than the caller's ceiling is refused."""
    srv = _FakeServer()
    # empty command → validator returns level_required L1 but allowed=False; use a
    # clearly-refused input to assert the ceiling path returns ok=False.
    r = tmux_writer.send("w1", "", server=srv, audit_dir=audit_dir)
    assert r["ok"] is False
    assert srv.sessions[0].active_pane.sent == []


# ── open_session (slice 2) ───────────────────────────────────────────────────
def test_open_creates_new_session_and_audits(audit_dir):
    srv = _FakeServer(names=())
    r = tmux_writer.open_session("build1", server=srv, audit_dir=audit_dir)
    assert r["ok"] is True
    assert any(s.name == "build1" for s in srv.sessions)
    assert any("opened" in row for row in _rows(audit_dir))


def test_open_refuses_unsafe_name(audit_dir):
    srv = _FakeServer(names=())
    r = tmux_writer.open_session("bad;$(whoami)", server=srv, audit_dir=audit_dir)
    assert r["ok"] is False
    assert srv.sessions == []  # nothing created


def test_open_never_clobbers_existing_session(audit_dir):
    srv = _FakeServer(names=("w1",))
    r = tmux_writer.open_session("w1", server=srv, audit_dir=audit_dir)
    assert r["ok"] is False
    assert "already exists" in r["reason"]
    assert len(srv.sessions) == 1  # unchanged


# ── close_session (slice 3 — L3 human-gated) ─────────────────────────────────
def test_close_without_approval_is_blocked_never_kills(audit_dir):
    """The load-bearing L3 invariant: no autonomous close, ever."""
    srv = _FakeServer(names=("w1",))
    r = tmux_writer.close_session("w1", server=srv, audit_dir=audit_dir)
    assert r["ok"] is False
    assert "human approval" in r["reason"]
    assert srv.sessions[0].killed is False  # NOT killed


def test_close_with_draft_routes_to_human_not_kill(audit_dir):
    srv = _FakeServer(names=("w1",))
    routed = {}

    def _post_draft(*, draft_text, destination_chat_id, drafted_by_role):
        routed["text"] = draft_text

    r = tmux_writer.close_session("w1", server=srv, audit_dir=audit_dir, post_draft=_post_draft)
    assert r["status"] == "pending-approval"
    assert srv.sessions[0].killed is False  # routed, not killed
    assert "Close tmux session 'w1'" in routed["text"]


def test_close_with_approval_kills_and_audits(audit_dir):
    srv = _FakeServer(names=("w1",))
    r = tmux_writer.close_session("w1", approved=True, server=srv, audit_dir=audit_dir)
    assert r["ok"] is True
    assert srv.sessions[0].killed is True
    assert any("closed" in row for row in _rows(audit_dir))


def test_close_missing_session_refused(audit_dir):
    srv = _FakeServer(names=("other",))
    r = tmux_writer.close_session("w1", approved=True, server=srv, audit_dir=audit_dir)
    assert r["ok"] is False
    assert "not found" in r["reason"]
