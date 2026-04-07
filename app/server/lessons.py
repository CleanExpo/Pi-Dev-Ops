"""
lessons.py — Institutional memory backed by .harness/lessons.jsonl.

JSONL format (one JSON object per line):
  {"ts": "ISO8601", "source": "...", "category": "...", "lesson": "...", "severity": "info|warn"}

load_lessons() reads and filters the file.
append_lesson() appends a new entry atomically (open in 'a' mode — append is
atomic for individual writes within the OS buffer size on POSIX; good enough
for a single-process server).
"""
import json, os, time
from datetime import timezone, datetime
from . import config


def _read_lines() -> list[dict]:
    path = config.LESSONS_FILE
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def load_lessons(category: str | None = None, limit: int = 50) -> list[dict]:
    """Return lessons, optionally filtered by category, newest-last, up to limit."""
    entries = _read_lines()
    if category:
        entries = [e for e in entries if e.get("category") == category]
    return entries[-limit:]


def append_lesson(source: str, category: str, lesson: str, severity: str = "info") -> dict:
    """Append a new lesson to the JSONL file. Returns the saved entry."""
    if severity not in ("info", "warn"):
        severity = "info"
    entry = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source[:100],
        "category": category[:50],
        "lesson": lesson[:500],
        "severity": severity,
    }
    path = config.LESSONS_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry
