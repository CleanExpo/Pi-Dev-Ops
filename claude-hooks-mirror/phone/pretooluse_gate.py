#!/usr/bin/env python3
"""PreToolUse gate — RA-1457 S-slice.

Posts an authority prompt to Telegram via /api/phone/gate, then polls
/status every 2 s up to 60 s. Exit 0 = approved, exit non-zero = denied
or timeout (fail-closed). Also fails closed if the backend is
unreachable — the whole point is to not run a destructive op without
user consent.

Claude Code provides the tool-call JSON on stdin:
  { "session_id": "...", "tool_name": "Bash", "tool_input": {...}, ... }
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    POLL_INTERVAL,
    TIMEOUT_S,
    backend_get,
    backend_post,
    log_error,
    read_hook_payload,
    session_id_from_payload,
)


def _summarise_input(tool_name: str, tool_input: dict) -> tuple[str, str]:
    """Return (summary, reason). Redacts file contents — path + line count only."""
    if not isinstance(tool_input, dict):
        return str(tool_input)[:200], "destructive tool call"

    if tool_name == "Bash":
        cmd = str(tool_input.get("command", ""))[:300]
        return f"$ {cmd}", "destructive bash command"

    if tool_name in ("Write", "Edit"):
        path = str(tool_input.get("file_path", ""))[:180]
        content = tool_input.get("content") or tool_input.get("new_string") or ""
        lines = str(content).count("\n") + 1 if content else 0
        return f"{tool_name} {path}\n({lines} lines — content redacted)", \
               f"{tool_name} to sensitive path"

    # Default: keys only, no values
    keys = ",".join(sorted(str(k) for k in tool_input.keys()))[:200]
    return f"keys: {keys}", f"{tool_name} call"


def main() -> int:
    payload = read_hook_payload()
    tool_name = payload.get("tool_name") or payload.get("toolName") or "unknown"
    tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
    session_id = session_id_from_payload(payload)

    summary, reason = _summarise_input(tool_name, tool_input)

    # RA-1109: every gate must have a terminal state visible on the phone.
    # We rely on the backend to edit the card when status flips.
    status_code, body = backend_post(
        "/api/phone/gate",
        {
            "session_id": session_id,
            "tool_name": tool_name,
            "tool_input_summary": summary,
            "reason": reason,
            "timeout_s": TIMEOUT_S,
        },
        timeout=10.0,
    )
    if status_code != 200 or "gate_id" not in body:
        log_error(f"gate create failed: {status_code} {body}")
        # Fail-closed on destructive gates
        print(f"phone-companion: backend unreachable ({status_code}). Blocking.", file=sys.stderr)
        return 2

    gate_id = body["gate_id"]
    deadline = time.time() + TIMEOUT_S + 5  # +5 s grace for network

    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        sc, sbody = backend_get(f"/api/phone/gate/{gate_id}/status", timeout=8.0)
        if sc != 200:
            continue
        st = sbody.get("status")
        if st == "approved":
            print(f"phone-companion: approved (gate={gate_id})", file=sys.stderr)
            return 0
        if st in ("denied", "expired"):
            print(f"phone-companion: {st} (gate={gate_id})", file=sys.stderr)
            return 1

    # Local timeout fallback — backend should've set expired already
    print(f"phone-companion: timeout (gate={gate_id})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
