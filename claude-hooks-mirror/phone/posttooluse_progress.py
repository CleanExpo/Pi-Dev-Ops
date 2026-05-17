#!/usr/bin/env python3
"""PostToolUse progress — RA-1457 S-slice.

Fires on every tool completion. Throttles to one /progress POST every
10 s across all tools to avoid flooding Telegram. Best-effort — never
blocks the tool call, always exits 0.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    PROGRESS_THROTTLE_S,
    THROTTLE_FILE,
    backend_post,
    log_error,
    read_hook_payload,
    session_id_from_payload,
)


def _git_info(cwd: str) -> tuple[str, str]:
    """Return (project, branch). Never raises."""
    project = Path(cwd).name or "?"
    branch = "?"
    try:
        out = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0:
            branch = out.stdout.strip() or branch
    except Exception:
        pass
    return project, branch


def _last_file(tool_input: dict) -> str:
    if not isinstance(tool_input, dict):
        return ""
    return str(
        tool_input.get("file_path")
        or tool_input.get("notebook_path")
        or tool_input.get("path")
        or ""
    )[:180]


def _should_throttle(session_id: str) -> bool:
    try:
        state = json.loads(THROTTLE_FILE.read_text()) if THROTTLE_FILE.is_file() else {}
    except Exception:
        state = {}
    last = state.get(session_id, 0)
    now = time.time()
    if now - last < PROGRESS_THROTTLE_S:
        return True
    state[session_id] = now
    try:
        THROTTLE_FILE.write_text(json.dumps(state))
    except Exception as exc:
        log_error(f"throttle write failed: {exc}")
    return False


def _started_at(session_id: str) -> float:
    """Track session start time locally so elapsed_s survives across hook calls."""
    f = THROTTLE_FILE.parent / "session_start.json"
    try:
        state = json.loads(f.read_text()) if f.is_file() else {}
    except Exception:
        state = {}
    if session_id not in state:
        state[session_id] = time.time()
        try:
            f.write_text(json.dumps(state))
        except Exception:
            pass
    return state.get(session_id, time.time())


def main() -> int:
    payload = read_hook_payload()
    session_id = session_id_from_payload(payload)
    if _should_throttle(session_id):
        return 0

    tool_name = payload.get("tool_name") or payload.get("toolName") or ""
    tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
    cwd = payload.get("cwd") or os.getcwd()
    project, branch = _git_info(cwd)
    last_file = _last_file(tool_input)
    elapsed = int(time.time() - _started_at(session_id))

    backend_post(
        "/api/phone/progress",
        {
            "session_id": session_id,
            "project": project,
            "branch": branch,
            "current_task": "",  # Claude Code doesn't expose this in the hook payload
            "last_tool": tool_name,
            "last_file": last_file,
            "elapsed_s": elapsed,
        },
        timeout=5.0,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        log_error(f"progress hook crash: {exc}")
        sys.exit(0)
