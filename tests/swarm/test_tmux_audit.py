"""Tests for swarm.tmux_audit — fail-closed audit ledger."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from swarm import tmux_audit
from swarm.tmux_audit import (
    ATOMIC_WRITE_CAP_BYTES,
    AuditRowTooLargeError,
    AuditUnwritableError,
    append,
    ensure_append_only,
)


@pytest.fixture
def temp_audit(tmp_path, monkeypatch):
    """Isolated audit dir + audit key per test."""
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    key_path = tmp_path / "audit-key"
    monkeypatch.setattr(tmux_audit, "DEFAULT_AUDIT_DIR", audit_dir)
    monkeypatch.setattr(tmux_audit, "AUDIT_KEY_PATH", key_path)
    return audit_dir


class TestAppend:
    def test_writes_one_line_per_call(self, temp_audit):
        audit_id = append({
            "actor": "test", "command": "tmux:list",
            "args": {}, "policy_level": "L1", "result": "ok",
        })
        assert audit_id.startswith("tmx-")
        # Find today's file
        files = list(temp_audit.glob("tmux-*.jsonl"))
        assert len(files) == 1
        lines = files[0].read_text().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["audit_id"] == audit_id
        assert parsed["actor"] == "test"
        assert parsed["command"] == "tmux:list"

    def test_audit_id_is_hmac_prefixed(self, temp_audit):
        audit_id = append({"actor": "t", "command": "c", "result": "ok"})
        assert audit_id.startswith("tmx-")
        assert len(audit_id) == len("tmx-") + 12

    def test_audit_id_changes_per_call(self, temp_audit):
        import time
        a1 = append({"actor": "t", "command": "c", "result": "ok"})
        time.sleep(0.001)
        a2 = append({"actor": "t", "command": "c", "result": "ok"})
        # Differ because ts_realtime differs
        assert a1 != a2

    def test_refuses_when_dir_missing(self, tmp_path, monkeypatch):
        missing = tmp_path / "does-not-exist"
        monkeypatch.setattr(tmux_audit, "DEFAULT_AUDIT_DIR", missing)
        monkeypatch.setattr(
            tmux_audit, "AUDIT_KEY_PATH", tmp_path / "audit-key",
        )
        with pytest.raises(AuditUnwritableError):
            append({"actor": "t", "command": "c", "result": "ok"})

    def test_truncates_captured_text_when_oversize(self, temp_audit):
        # Build an event that's just over the cap
        long_text = "x" * 600
        audit_id = append({
            "actor": "test",
            "command": "tmux:tail",
            "args": {},
            "policy_level": "L1",
            "result": "ok",
            "captured_text": long_text,
        })
        files = list(temp_audit.glob("tmux-*.jsonl"))
        line = files[0].read_text().splitlines()[0]
        assert len(line.encode("utf-8")) <= ATOMIC_WRITE_CAP_BYTES
        parsed = json.loads(line)
        assert "truncated" in parsed["captured_text"].lower()

    def test_refuses_irreducible_oversize(self, temp_audit):
        # Construct an event where mandatory fields alone exceed cap
        with pytest.raises(AuditRowTooLargeError):
            append({
                "actor": "test",
                "command": "tmux:run",
                "args": {},
                "policy_level": "L3",
                "result": "ok",
                "error_code": "x" * 600,  # not in TRUNCATABLE_FIELDS
            })


class TestAuditKey:
    def test_key_generated_on_first_run(self, tmp_path, monkeypatch):
        key_path = tmp_path / "audit-key"
        monkeypatch.setattr(tmux_audit, "AUDIT_KEY_PATH", key_path)
        monkeypatch.setattr(tmux_audit, "DEFAULT_AUDIT_DIR", tmp_path / "audit")
        (tmp_path / "audit").mkdir()
        assert not key_path.exists()
        append({"actor": "t", "command": "c", "result": "ok"})
        assert key_path.exists()
        st = key_path.stat()
        assert (st.st_mode & 0o077) == 0  # only owner can read

    def test_refuses_loose_permissions(self, tmp_path, monkeypatch):
        key_path = tmp_path / "audit-key"
        key_path.write_bytes(b"x" * 32)
        os.chmod(key_path, 0o644)  # world-readable
        monkeypatch.setattr(tmux_audit, "AUDIT_KEY_PATH", key_path)
        monkeypatch.setattr(tmux_audit, "DEFAULT_AUDIT_DIR", tmp_path / "audit")
        (tmp_path / "audit").mkdir()
        with pytest.raises(AuditUnwritableError):
            append({"actor": "t", "command": "c", "result": "ok"})


class TestEnsureAppendOnly:
    def test_creates_dir(self, tmp_path):
        new_dir = tmp_path / "newaudit"
        assert not new_dir.exists()
        status = ensure_append_only(new_dir)
        assert new_dir.exists()
        assert status["audit_dir"] == str(new_dir)

    def test_creates_today_file(self, tmp_path):
        status = ensure_append_only(tmp_path)
        today_file = Path(status["today_file"])
        assert today_file.exists()
        assert today_file.name.startswith("tmux-")
        assert today_file.name.endswith(".jsonl")

    def test_returns_flag_status(self, tmp_path):
        status = ensure_append_only(tmp_path)
        assert "append_only_flag_set" in status
        assert isinstance(status["append_only_flag_set"], bool)


class TestFsyncFailure:
    def test_short_write_raises(self, temp_audit, monkeypatch):
        """Simulate os.write returning fewer bytes than requested."""
        real_write = os.write

        def short_write(fd, data):
            # Write only the first byte
            real_write(fd, data[:1])
            return 1

        monkeypatch.setattr(os, "write", short_write)
        with pytest.raises(AuditUnwritableError):
            append({"actor": "t", "command": "c", "result": "ok"})
