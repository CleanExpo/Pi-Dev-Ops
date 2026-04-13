"""
persistence.py — Atomic session JSON persistence.

Saves session metadata to {LOG_DIR}/sessions/{sid}.json after every status change.
On server startup, restore_sessions() reloads all saved sessions and marks any
that were mid-flight as "interrupted".

Atomic write pattern: write to .tmp then os.replace() to prevent corrupt files
on crash or mid-write power loss.

Session IDs are sanitised (alphanumeric only) before any file path use to
prevent path traversal attacks.
"""
import json
import os
import re
import tempfile
import time
from . import config


def _sessions_dir() -> str:
    d = os.path.join(config.LOG_DIR, "sessions")
    os.makedirs(d, exist_ok=True)
    return d


def _safe_sid(sid: str) -> str:
    """Strip everything that is not a-z A-Z 0-9 from the session ID."""
    return re.sub(r"[^a-zA-Z0-9]", "", sid)


def _path(sid: str) -> str:
    return os.path.join(_sessions_dir(), f"{_safe_sid(sid)}.json")


def save_session(session) -> None:
    """Atomically persist session metadata to disk. Excludes process and output_lines."""
    data = {
        "id": session.id,
        "repo_url": session.repo_url,
        "workspace": session.workspace,
        "started_at": session.started_at,
        "status": session.status,
        "error": session.error,
        "output_line_count": len(session.output_lines),
        "evaluator_status": getattr(session, "evaluator_status", "pending"),
        "evaluator_score": getattr(session, "evaluator_score", None),
        "evaluator_model": getattr(session, "evaluator_model", ""),
        "evaluator_consensus": getattr(session, "evaluator_consensus", ""),
        "last_completed_phase": getattr(session, "last_completed_phase", ""),
        "retry_count": getattr(session, "retry_count", 0),
        "linear_issue_id": getattr(session, "linear_issue_id", None),
        "saved_at": time.time(),
    }
    target = _path(session.id)
    sessions_dir = os.path.dirname(target)
    try:
        # Use a unique tmp file in the same directory so os.replace() is atomic
        # (same filesystem). A fixed .tmp suffix causes races when two threads
        # save the same session simultaneously — each would overwrite the other's
        # tmp file before calling os.replace().
        fd, tmp = tempfile.mkstemp(dir=sessions_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, target)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError:
        # Non-fatal — persistence failure should not crash the session
        pass


def load_all_sessions() -> list[dict]:
    """Read all session JSON files from disk. Returns list of dicts."""
    d = _sessions_dir()
    results = []
    for fname in os.listdir(d):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(d, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                results.append(json.load(f))
        except (OSError, json.JSONDecodeError):
            pass
    return results


def delete_session_file(sid: str) -> None:
    """Remove the persisted JSON file for a session."""
    path = _path(sid)
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
