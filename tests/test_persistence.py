"""
test_persistence.py — Unit tests for atomic session persistence (persistence.py).

Covers:
- Atomic write: save_session writes valid JSON, file exists after save
- Round-trip: save then load_all_sessions returns same data
- Path traversal: _safe_sid strips ../  and special chars
- Corrupt file tolerance: load_all_sessions skips unreadable files
- Concurrent overwrites: last write wins (no corruption)
- delete_session_file: removes file, silently ignores missing
"""
import json
import os
import tempfile
import threading
import importlib
import types

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_log_dir(monkeypatch, tmp_path):
    """Point config.LOG_DIR at a temp directory for isolation."""
    # Import config first so os.environ defaults are set by conftest
    from app.server import config as cfg
    monkeypatch.setattr(cfg, "LOG_DIR", str(tmp_path))
    return tmp_path


class _FakeSession:
    """Minimal session object that matches the fields save_session() reads."""
    def __init__(self, sid="abc123", status="running"):
        self.id = sid
        self.repo_url = f"https://github.com/test/{sid}"
        self.workspace = f"/tmp/workspace/{sid}"
        self.started_at = 1700000000.0
        self.status = status
        self.error = None
        self.output_lines = ["line1", "line2"]
        self.evaluator_status = "pending"
        self.evaluator_score = None
        self.evaluator_model = "claude-haiku-4-5"
        self.evaluator_consensus = ""
        self.last_completed_phase = "phase-2"
        self.retry_count = 0
        self.linear_issue_id = "RA-999"


# ── Tests: save_session ───────────────────────────────────────────────────────

def test_save_creates_valid_json_file(temp_log_dir):
    from app.server import persistence
    importlib.reload(persistence)  # pick up patched LOG_DIR
    session = _FakeSession("session001")
    persistence.save_session(session)

    sessions_dir = temp_log_dir / "sessions"
    files = list(sessions_dir.glob("*.json"))
    assert len(files) == 1

    data = json.loads(files[0].read_text())
    assert data["id"] == "session001"
    assert data["status"] == "running"
    assert data["output_line_count"] == 2
    assert data["linear_issue_id"] == "RA-999"


def test_save_does_not_leave_tmp_file(temp_log_dir):
    from app.server import persistence
    importlib.reload(persistence)
    session = _FakeSession("session002")
    persistence.save_session(session)

    sessions_dir = temp_log_dir / "sessions"
    tmp_files = list(sessions_dir.glob("*.tmp"))
    assert tmp_files == [], "Leftover .tmp file — atomic replace failed"


def test_overwrite_updates_existing(temp_log_dir):
    from app.server import persistence
    importlib.reload(persistence)
    session = _FakeSession("session003", status="running")
    persistence.save_session(session)

    session.status = "done"
    persistence.save_session(session)

    sessions_dir = temp_log_dir / "sessions"
    files = list(sessions_dir.glob("*.json"))
    assert len(files) == 1  # still one file
    data = json.loads(files[0].read_text())
    assert data["status"] == "done"


# ── Tests: load_all_sessions ──────────────────────────────────────────────────

def test_load_returns_saved_sessions(temp_log_dir):
    from app.server import persistence
    importlib.reload(persistence)

    for i in range(3):
        persistence.save_session(_FakeSession(f"sess{i:03d}"))

    loaded = persistence.load_all_sessions()
    assert len(loaded) == 3
    ids = {s["id"] for s in loaded}
    assert ids == {"sess000", "sess001", "sess002"}


def test_load_skips_corrupt_file(temp_log_dir):
    from app.server import persistence
    importlib.reload(persistence)

    persistence.save_session(_FakeSession("good001"))

    # Write a corrupt file directly
    corrupt = temp_log_dir / "sessions" / "bad001.json"
    corrupt.parent.mkdir(parents=True, exist_ok=True)
    corrupt.write_text("{not valid json{{")

    loaded = persistence.load_all_sessions()
    # Only the valid file is returned
    assert len(loaded) == 1
    assert loaded[0]["id"] == "good001"


def test_load_empty_dir_returns_empty_list(temp_log_dir):
    from app.server import persistence
    importlib.reload(persistence)

    loaded = persistence.load_all_sessions()
    assert loaded == []


# ── Tests: delete_session_file ────────────────────────────────────────────────

def test_delete_removes_file(temp_log_dir):
    from app.server import persistence
    importlib.reload(persistence)

    session = _FakeSession("todelete")
    persistence.save_session(session)

    sessions_dir = temp_log_dir / "sessions"
    assert len(list(sessions_dir.glob("*.json"))) == 1

    persistence.delete_session_file("todelete")
    assert len(list(sessions_dir.glob("*.json"))) == 0


def test_delete_missing_file_does_not_raise(temp_log_dir):
    from app.server import persistence
    importlib.reload(persistence)
    # Should not raise even if file never existed
    persistence.delete_session_file("nonexistent_session")


# ── Tests: _safe_sid (path traversal prevention) ─────────────────────────────

def test_safe_sid_strips_path_traversal():
    from app.server import persistence
    importlib.reload(persistence)
    assert persistence._safe_sid("../../etc/passwd") == "etcpasswd"


def test_safe_sid_strips_special_chars():
    from app.server import persistence
    importlib.reload(persistence)
    assert persistence._safe_sid("session-001/evil.json") == "session001eviljson"


def test_safe_sid_preserves_alphanumeric():
    from app.server import persistence
    importlib.reload(persistence)
    assert persistence._safe_sid("Session123ABC") == "Session123ABC"


def test_safe_sid_empty_string():
    from app.server import persistence
    importlib.reload(persistence)
    assert persistence._safe_sid("") == ""


# ── Tests: concurrent writes ──────────────────────────────────────────────────

def test_concurrent_saves_do_not_corrupt(temp_log_dir):
    """Two threads saving the same session simultaneously must not leave corrupt JSON."""
    from app.server import persistence
    importlib.reload(persistence)

    errors = []

    def _save(status):
        try:
            session = _FakeSession("concurrent_session", status=status)
            persistence.save_session(session)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=_save, args=(s,)) for s in ["running"] * 10]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Exceptions during concurrent save: {errors}"

    # File must be valid JSON after all writes
    sessions_dir = temp_log_dir / "sessions"
    files = list(sessions_dir.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["id"] == "concurrent_session"
