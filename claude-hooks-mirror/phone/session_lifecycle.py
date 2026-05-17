#!/usr/bin/env python3
"""SessionStart / Stop hook — RA-1457 S-slice.

One script serves both events. Invoked as:
  session_lifecycle.py start
  session_lifecycle.py stop

Best-effort — never blocks Claude Code, always exits 0.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    THROTTLE_FILE,
    backend_post,
    log_error,
    read_hook_payload,
    session_id_from_payload,
)


def _git_info(cwd: str) -> tuple[str, str]:
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


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("start", "stop"):
        log_error("session_lifecycle: missing action arg")
        return 0

    action = sys.argv[1]
    payload = read_hook_payload()
    session_id = session_id_from_payload(payload)
    cwd = payload.get("cwd") or os.getcwd()
    project, branch = _git_info(cwd)

    if action == "stop":
        # Wipe local throttle/start state for this session
        for f in (THROTTLE_FILE, THROTTLE_FILE.parent / "session_start.json"):
            if f.is_file():
                try:
                    import json
                    state = json.loads(f.read_text())
                    state.pop(session_id, None)
                    f.write_text(json.dumps(state))
                except Exception:
                    pass

    backend_post(
        "/api/phone/session",
        {
            "session_id": session_id,
            "action": action,
            "project": project,
            "branch": branch,
            "summary": payload.get("summary", "") if action == "stop" else "",
        },
        timeout=5.0,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        log_error(f"session_lifecycle crash: {exc}")
        sys.exit(0)
