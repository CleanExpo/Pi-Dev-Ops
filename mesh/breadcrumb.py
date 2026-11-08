"""The runner breadcrumb file: what this node runs and is doing, for the heartbeat (08/11/2026).

Split out of runner.py for its 300-line gate. Beyond the live task, every write now
carries the version-gate verdict (approved_version, version_status, version_reason),
the runtime's local_edits, and two facts that must outlive the process: last_update
and last_job. Those two are read back from the previous file on every write, so a
restarted runner still reports what its predecessor last did. Unknown is null.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import version_gate  # noqa: E402

CARRIED = ("last_update", "last_job")
_EDITS: dict[str, int | None] = {}  # code dir -> local edit count, refreshed between claims only


def refresh_local_edits(code_dir: Path) -> None:
    """Count the runtime's local edits now. Called between claims, never from write():
    write() runs inside a claim's interrupt-held ending and must not start a process."""
    _EDITS[str(code_dir)] = version_gate.local_edits(code_dir)


def read(path: Path) -> dict:
    """The previous breadcrumb, or {} when absent or unreadable."""
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _store(path: Path, record: dict) -> None:
    """Write via a temp file and rename, so the heartbeat never reads half a file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(record))
        os.replace(tmp, path)
    except OSError:
        pass


def write(path: Path, fields: dict, verdict: Any, code_dir: Path) -> None:
    """The live fields, the gate's last verdict (None: not checked yet), local edits, carried facts."""
    previous = read(path)
    _store(path, {
        **fields,
        "approved_version": getattr(verdict, "approved", None),
        "version_status": getattr(verdict, "status", None),
        "version_reason": getattr(verdict, "reason", None) or None,
        "local_edits": _EDITS.get(str(code_dir)),
        **{key: previous.get(key) for key in CARRIED},
        "ts": int(time.time()),
    })


def remember(path: Path, key: str, value: dict) -> None:
    """Record one carried fact (last_update or last_job) into the current breadcrumb."""
    record = read(path)
    record[key] = value
    _store(path, record)


def note_jobs(path: Path, results: list[dict]) -> None:
    """The last claim this runner ended, with how it ended."""
    if results:
        last = results[-1]
        remember(path, "last_job", {"linear_id": last.get("linear_id"), "state": last.get("state"),
                                    "ts": int(time.time())})
