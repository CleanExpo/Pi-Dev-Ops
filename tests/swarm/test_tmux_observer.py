"""Tests for swarm.tmux_observer — T1 read-only observer.

Most tests use stub libtmux objects (no real tmux required). A small bucket
of live-socket integration tests auto-skips when tmux isn't on PATH.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from swarm import tmux_audit, tmux_observer


# ============================================================
# Stub libtmux objects (no tmux required)
# ============================================================


class _Cmd:
    def __init__(self, stdout):
        self.stdout = stdout


class FakePane:
    def __init__(
        self,
        pane_id: str,
        *,
        index: int = 0,
        pid: int = 12345,
        current_command: str = "zsh",
        current_path: str = "/tmp",
        active: bool = False,
        dead: bool = False,
        history_size: int = 1000,
    ):
        self.id = pane_id
        self.index = str(index)
        self.pid = str(pid) if pid else ""
        self.pane_current_command = current_command
        self.pane_current_path = current_path
        self.pane_active = "1" if active else "0"
        self.pane_dead = "1" if dead else "0"
        self.history_size = str(history_size)


class FakeWindow:
    def __init__(self, name: str, *, index: int = 0, panes=None):
        self.window_name = name
        self.window_index = str(index)
        self.panes = panes or []


class FakeSession:
    def __init__(self, name: str, *, session_id: str = "$0", windows=None,
                 attached: bool = False, created: str = "2026-05-26T00:00:00Z"):
        self.name = name
        self.session_id = session_id
        self.windows = windows or []
        self.session_attached = "1" if attached else "0"
        self.session_created = created


class FakeServer:
    def __init__(self, sessions=None, capture_lines=None):
        self.sessions = sessions or []
        self._capture_lines = capture_lines or []
        self.cmd_calls: list[tuple] = []

    def cmd(self, *args, **kwargs):
        self.cmd_calls.append((args, kwargs))
        return _Cmd(stdout=self._capture_lines)


@pytest.fixture
def temp_audit(tmp_path, monkeypatch):
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    key_path = tmp_path / "audit-key"
    monkeypatch.setattr(tmux_audit, "DEFAULT_AUDIT_DIR", audit_dir)
    monkeypatch.setattr(tmux_audit, "AUDIT_KEY_PATH", key_path)
    return audit_dir


@pytest.fixture
def fake_server_simple():
    pane = FakePane("%4", index=0, current_command="zsh")
    window = FakeWindow("editor", index=0, panes=[pane])
    session = FakeSession("nexus-dev", session_id="$0", windows=[window])
    return FakeServer(sessions=[session], capture_lines=["line1", "line2", "line3"])


# ============================================================
# Pure-logic helper tests
# ============================================================


class TestPaneSnapshot:
    def test_basic_fields_extracted(self):
        pane = FakePane("%7", index=2, pid=999, current_command="vim",
                        current_path="/repo")
        snap = tmux_observer._pane_snapshot(pane)
        assert snap["id"] == "%7"
        assert snap["index"] == 2
        assert snap["pid"] == 999
        assert snap["current_command"] == "vim"
        assert snap["current_path"] == "/repo"
        assert snap["is_active"] is False
        assert snap["is_dead"] is False

    def test_active_and_dead_flags_propagate(self):
        active_pane = FakePane("%1", active=True)
        dead_pane = FakePane("%2", dead=True)
        assert tmux_observer._pane_snapshot(active_pane)["is_active"] is True
        assert tmux_observer._pane_snapshot(dead_pane)["is_dead"] is True

    def test_missing_pid_yields_zero(self):
        pane = FakePane("%3", pid=0)
        snap = tmux_observer._pane_snapshot(pane)
        assert snap["pid"] == 0


class TestWindowSnapshot:
    def test_collects_all_panes(self):
        p1 = FakePane("%1")
        p2 = FakePane("%2")
        win = FakeWindow("editor", panes=[p1, p2])
        snap = tmux_observer._window_snapshot(win)
        assert snap["name"] == "editor"
        assert len(snap["panes"]) == 2
        assert {p["id"] for p in snap["panes"]} == {"%1", "%2"}


class TestSessionSnapshot:
    def test_recursively_snapshots(self):
        pane = FakePane("%5")
        win = FakeWindow("w", panes=[pane])
        sess = FakeSession("nexus-dev", windows=[win], attached=True)
        snap = tmux_observer._session_snapshot(sess)
        assert snap["name"] == "nexus-dev"
        assert snap["attached"] is True
        assert snap["windows"][0]["panes"][0]["id"] == "%5"


class TestNowIso:
    def test_iso_format_with_z_suffix(self):
        iso = tmux_observer._now_iso()
        assert iso.endswith("Z")
        # Should round-trip via fromisoformat (after stripping Z)
        from datetime import datetime
        datetime.fromisoformat(iso.replace("Z", "+00:00"))


# ============================================================
# Pane resolution
# ============================================================


class TestResolvePaneId:
    def test_exact_match(self, fake_server_simple):
        pid = tmux_observer._resolve_pane_id(
            fake_server_simple, "nexus-dev", "editor", 0
        )
        assert pid == "%4"

    def test_window_none_matches_first(self, fake_server_simple):
        pid = tmux_observer._resolve_pane_id(
            fake_server_simple, "nexus-dev", None, 0
        )
        assert pid == "%4"

    def test_pane_none_matches_first(self, fake_server_simple):
        pid = tmux_observer._resolve_pane_id(
            fake_server_simple, "nexus-dev", "editor", None
        )
        assert pid == "%4"

    def test_unknown_session_returns_none(self, fake_server_simple):
        assert tmux_observer._resolve_pane_id(
            fake_server_simple, "does-not-exist", None, None,
        ) is None

    def test_unknown_window_returns_none(self, fake_server_simple):
        assert tmux_observer._resolve_pane_id(
            fake_server_simple, "nexus-dev", "ghost-window", 0,
        ) is None

    def test_unknown_pane_index_returns_none(self, fake_server_simple):
        assert tmux_observer._resolve_pane_id(
            fake_server_simple, "nexus-dev", "editor", 99,
        ) is None


# ============================================================
# Capture + redaction
# ============================================================


class TestCapturePane:
    def test_returns_redacted_text(self):
        # Pane output containing an Anthropic-shape secret (assembled)
        secret_blob = "ANTHROPIC_API_KEY=" + "sk" + "-ant-api03-" + "x" * 50
        srv = FakeServer(capture_lines=["normal line", secret_blob])
        result = tmux_observer._capture_pane_lines(srv, "%1", lines=10)
        assert "[REDACTED:anthropic]" in result["text"]
        assert result["secret_redactions"].get("anthropic", 0) >= 1
        # Original secret bytes never appear in returned text
        assert "sk-ant-api03-" not in result["text"]

    def test_no_secrets_means_empty_redaction_counts(self):
        srv = FakeServer(capture_lines=["safe line 1", "safe line 2"])
        result = tmux_observer._capture_pane_lines(srv, "%1", lines=10)
        assert result["secret_redactions"] == {}
        assert "safe line 1" in result["text"]

    def test_capture_error_surfaces_gracefully(self):
        class BoomServer:
            def cmd(self, *a, **k):
                raise RuntimeError("simulated tmux failure")
        result = tmux_observer._capture_pane_lines(BoomServer(), "%1", lines=10)
        assert result["text"] == ""
        assert "capture_error" in result
        assert "simulated tmux failure" in result["capture_error"]

    def test_lines_passed_to_capture_pane(self, fake_server_simple):
        tmux_observer._capture_pane_lines(fake_server_simple, "%4", lines=50)
        # Check that capture-pane was called with -S -<lines>
        args, _ = fake_server_simple.cmd_calls[0]
        assert "capture-pane" in args
        assert "-S" in args
        assert "-50" in args
        assert "-t" in args
        # %4 should be in there
        assert "%4" in args


class TestResolveActor:
    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("HERMES_TMUX_ACTOR", "hermes-strategy")
        assert tmux_observer._resolve_actor() == "hermes-strategy"

    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("HERMES_TMUX_ACTOR", raising=False)
        assert tmux_observer._resolve_actor() == "operator-cli"


# ============================================================
# Public API — list
# ============================================================


class TestList:
    def test_list_returns_snapshot_structure(self, fake_server_simple, temp_audit):
        result = tmux_observer.list_sessions(server=fake_server_simple)
        assert "sessions" in result
        assert "captured_at" in result
        assert "audit_id" in result
        assert len(result["sessions"]) == 1
        assert result["sessions"][0]["name"] == "nexus-dev"

    def test_list_writes_one_audit_row(self, fake_server_simple, temp_audit):
        tmux_observer.list_sessions(server=fake_server_simple)
        files = list(temp_audit.glob("tmux-*.jsonl"))
        assert len(files) == 1
        lines = files[0].read_text().splitlines()
        assert len(lines) == 1
        row = json.loads(lines[0])
        assert row["command"] == "tmux:list"
        assert row["policy_level"] == "L1"
        assert row["result"] == "ok"

    def test_list_counts_sessions_and_panes(self, fake_server_simple, temp_audit):
        tmux_observer.list_sessions(server=fake_server_simple)
        files = list(temp_audit.glob("tmux-*.jsonl"))
        row = json.loads(files[0].read_text().splitlines()[0])
        assert row["session_count"] == 1
        assert row["pane_count"] == 1

    def test_list_with_empty_server(self, temp_audit):
        srv = FakeServer(sessions=[])
        result = tmux_observer.list_sessions(server=srv)
        assert result["sessions"] == []


# ============================================================
# Public API — status
# ============================================================


class TestStatus:
    def test_status_adds_health_field(self, fake_server_simple, temp_audit):
        result = tmux_observer.status(server=fake_server_simple)
        pane = result["sessions"][0]["windows"][0]["panes"][0]
        assert "health" in pane
        assert pane["health"] in ("healthy", "stale", "dead")

    def test_status_flags_dead_pane(self, temp_audit):
        dead = FakePane("%9", dead=True, current_command="")
        win = FakeWindow("w", panes=[dead])
        sess = FakeSession("nexus-dev", windows=[win])
        srv = FakeServer(sessions=[sess])
        result = tmux_observer.status(server=srv)
        assert result["sessions"][0]["windows"][0]["panes"][0]["health"] == "dead"

    def test_status_includes_redacted_last_lines(self, temp_audit):
        secret_line = "key=" + "sk" + "-ant-api03-" + "x" * 50
        pane = FakePane("%1")
        win = FakeWindow("w", panes=[pane])
        sess = FakeSession("nexus-dev", windows=[win])
        srv = FakeServer(sessions=[sess], capture_lines=[secret_line])
        result = tmux_observer.status(server=srv)
        pane_data = result["sessions"][0]["windows"][0]["panes"][0]
        assert "last_lines_redacted" in pane_data
        assert "[REDACTED:" in pane_data["last_lines_redacted"]

    def test_status_filters_by_session_name(self, temp_audit):
        sess_a = FakeSession("nexus-dev", windows=[FakeWindow("w")])
        sess_b = FakeSession("nexus-tests", windows=[FakeWindow("w")])
        srv = FakeServer(sessions=[sess_a, sess_b])
        result = tmux_observer.status(session="nexus-tests", server=srv)
        names = [s["name"] for s in result["sessions"]]
        assert names == ["nexus-tests"]

    def test_status_writes_audit_row(self, fake_server_simple, temp_audit):
        tmux_observer.status(server=fake_server_simple)
        files = list(temp_audit.glob("tmux-*.jsonl"))
        row = json.loads(files[0].read_text().splitlines()[0])
        assert row["command"] == "tmux:status"


# ============================================================
# Public API — tail
# ============================================================


class TestTail:
    def test_tail_returns_redacted_with_audit_id(self, fake_server_simple, temp_audit):
        result = tmux_observer.tail(
            "nexus-dev", "editor", 0, lines=10, server=fake_server_simple,
        )
        assert "text" in result
        assert "pane_id" in result
        assert result["pane_id"] == "%4"
        assert "audit_id" in result
        assert result["audit_id"].startswith("tmx-")

    def test_tail_unknown_pane_raises(self, fake_server_simple, temp_audit):
        with pytest.raises(ValueError, match="pane not found"):
            tmux_observer.tail(
                "nexus-dev", "ghost", 99, lines=10, server=fake_server_simple,
            )

    def test_tail_clamps_lines_below_one(self, fake_server_simple, temp_audit):
        # Internal clamp should silently raise 0 to 1
        result = tmux_observer.tail(
            "nexus-dev", "editor", 0, lines=0, server=fake_server_simple,
        )
        assert result["pane_id"] == "%4"

    def test_tail_clamps_lines_above_max(self, fake_server_simple, temp_audit):
        result = tmux_observer.tail(
            "nexus-dev", "editor", 0, lines=99999, server=fake_server_simple,
        )
        # Captured command shows the clamped value
        args, _ = fake_server_simple.cmd_calls[0]
        assert f"-{tmux_observer.MAX_TAIL_LINES}" in args
        assert result["pane_id"] == "%4"

    def test_tail_writes_audit_with_pane_id(self, fake_server_simple, temp_audit):
        tmux_observer.tail("nexus-dev", "editor", 0, server=fake_server_simple)
        row = json.loads(
            list(temp_audit.glob("tmux-*.jsonl"))[0].read_text().splitlines()[0]
        )
        assert row["command"] == "tmux:tail"
        # The audit row carries the resolved pane_id in args
        assert row["args"].get("pane_id") == "%4"


# ============================================================
# Hermes protected panes snapshot
# ============================================================


class TestSnapshotHermesPanes:
    def test_writes_snapshot_file(self, tmp_path, monkeypatch, fake_server_simple):
        out_path = tmp_path / "protected-panes.json"
        monkeypatch.setattr(tmux_observer, "PROTECTED_PANES_FILE", out_path)
        monkeypatch.setattr(tmux_observer, "HERMES_PID_FILE", tmp_path / "no-gateway.pid")
        result = tmux_observer.snapshot_hermes_panes(server=fake_server_simple)
        assert out_path.exists()
        data = json.loads(out_path.read_text())
        assert "captured_at" in data
        assert "protected_pane_ids" in data
        # No Hermes pid file → empty list
        assert data["protected_pane_ids"] == []

    def test_snapshot_structure_includes_pid_file_path(
        self, tmp_path, monkeypatch, fake_server_simple,
    ):
        out_path = tmp_path / "protected.json"
        pid_file = tmp_path / "gateway.pid"
        monkeypatch.setattr(tmux_observer, "PROTECTED_PANES_FILE", out_path)
        monkeypatch.setattr(tmux_observer, "HERMES_PID_FILE", pid_file)
        result = tmux_observer.snapshot_hermes_panes(server=fake_server_simple)
        assert str(pid_file) in result["hermes_gateway_pid_file"]


# ============================================================
# pid_in_tree (subprocess-dependent)
# ============================================================


class TestPidInTree:
    def test_direct_match(self):
        assert tmux_observer._pid_in_tree(12345, 12345) is True

    def test_pgrep_failure_returns_false(self, monkeypatch):
        def boom(*a, **k):
            raise FileNotFoundError("pgrep not on PATH")
        monkeypatch.setattr(tmux_observer.subprocess, "run", boom)
        assert tmux_observer._pid_in_tree(99999, 1) is False

    def test_pgrep_returns_no_children(self, monkeypatch):
        class _R:
            returncode = 1
            stdout = ""
        monkeypatch.setattr(tmux_observer.subprocess, "run", lambda *a, **k: _R())
        assert tmux_observer._pid_in_tree(99999, 1) is False


# ============================================================
# Live tmux integration (auto-skip if tmux absent)
# ============================================================


TMUX_AVAILABLE = shutil.which("tmux") is not None


@pytest.mark.skipif(not TMUX_AVAILABLE, reason="tmux binary not on PATH")
class TestLiveTmuxIntegration:
    """Run against an isolated `tmux -L t1-tests` socket — never touches the
    operator's real sessions."""

    SOCKET = "t1-tests"

    @classmethod
    def setup_class(cls):
        # Ensure the test socket has at least one session for list() to find.
        subprocess.run(
            ["tmux", "-L", cls.SOCKET, "kill-server"],
            check=False, capture_output=True,
        )
        subprocess.run(
            ["tmux", "-L", cls.SOCKET, "new-session", "-d", "-s", "t1-smoke"],
            check=False, capture_output=True,
        )

    @classmethod
    def teardown_class(cls):
        subprocess.run(
            ["tmux", "-L", cls.SOCKET, "kill-server"],
            check=False, capture_output=True,
        )

    def test_live_list_finds_test_session(self, temp_audit):
        import libtmux
        server = libtmux.Server(socket_name=self.SOCKET)
        result = tmux_observer.list_sessions(server=server)
        names = [s["name"] for s in result["sessions"]]
        assert "t1-smoke" in names

    def test_live_pane_id_is_percent_n_format(self, temp_audit):
        import libtmux
        server = libtmux.Server(socket_name=self.SOCKET)
        result = tmux_observer.list_sessions(server=server)
        for sess in result["sessions"]:
            for win in sess["windows"]:
                for pane in win["panes"]:
                    assert pane["id"].startswith("%")


# ============================================================
# CLI smoke
# ============================================================


class TestCli:
    def test_cli_list_argparse(self, monkeypatch, temp_audit, fake_server_simple):
        # Patch the _get_server import path so CLI doesn't try real tmux
        monkeypatch.setattr(tmux_observer, "_get_server",
                            lambda **kw: fake_server_simple)
        # Capture stdout
        from io import StringIO
        buf = StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        rc = tmux_observer.main(["list"])
        assert rc == 0
        out = buf.getvalue()
        parsed = json.loads(out)
        assert "sessions" in parsed

    def test_cli_unknown_subcommand_exits(self, monkeypatch, temp_audit):
        with pytest.raises(SystemExit):
            tmux_observer.main(["totally-bogus"])

    def test_cli_tail_requires_session(self, monkeypatch, temp_audit):
        with pytest.raises(SystemExit):
            tmux_observer.main(["tail"])
