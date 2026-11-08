"""What the heartbeat says about this node's mesh runner, whatever the breadcrumb's age (08/11/2026).

heartbeat.py used to drop a breadcrumb older than 120 s before reading anything from
it. The runner writes it once at the start of a build, so during any long build, and
whenever the runner was dead, the fleet showed "nexus-mesh/0.1" on every machine. A
dead runner's last-known code is still a fact, so the version is now always read and
labelled with the breadcrumb's age instead. The `mesh-runner` entry rides in the
existing `agent_runtimes` jsonb list (no schema change); anything not known is null.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

FRESH_S = 120
_FIELDS = ("approved_version", "version_status", "state", "current_task", "hold_reason",
           "local_edits", "last_update", "last_job")


def _sha(value: object) -> str | None:
    text = str(value or "").strip()
    return text if len(text) == 40 and all(c in "0123456789abcdef" for c in text) else None


def read(path: str) -> tuple[bool, dict]:
    """(the breadcrumb file exists, its contents or {} when unreadable)."""
    if not os.path.exists(path):
        return False, {}
    try:
        with open(path) as f:
            data = json.loads(f.read())
    except (OSError, ValueError):
        return True, {}
    return True, data if isinstance(data, dict) else {}


def age_s(crumb: dict, now: float | None = None) -> int | None:
    """Seconds since the runner last wrote the breadcrumb, or None without a timestamp."""
    try:
        ts = float(crumb["ts"])
    except (KeyError, TypeError, ValueError):
        return None
    return max(0, int((now if now is not None else time.time()) - ts))


def version_label(crumb: dict, now: float | None = None) -> str | None:
    """`nexus-mesh/<sha12>`, plus the breadcrumb's age once it is not fresh. None when no
    commit is known: the old fallback "nexus-mesh/0.1" was a guess (the column is nullable)."""
    sha = _sha(crumb.get("version"))
    if not sha:
        return None
    age = age_s(crumb, now)
    return f"nexus-mesh/{sha[:12]}" + (f" (state {age}s old)" if age is not None and age > FRESH_S else "")


def git_head(directory: Path) -> str | None:
    """The commit checked out in `directory`, or None if git cannot say."""
    try:
        done = subprocess.run(["git", "-C", str(directory), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return _sha(done.stdout) if done.returncode == 0 else None


def entry(path: str, now: float | None = None) -> dict:
    """The one `mesh-runner` row for agent_runtimes. Unknown values are null, never guessed."""
    present, crumb = read(path)
    row = {"runtime": "mesh-runner", "present": present, "version": _sha(crumb.get("version"))}
    row.update({key: crumb.get(key) for key in _FIELDS})
    row["approved_version"] = _sha(row["approved_version"])
    row["state_age_s"] = age_s(crumb, now)
    row["skills_version"] = git_head(Path.home() / ".claude")
    row["heartbeat_version"] = git_head(Path(__file__).resolve().parent)
    return row
