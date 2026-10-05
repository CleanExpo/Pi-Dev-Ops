#!/usr/bin/env python3
"""Scope-freeze guard: block Edit/Write outside one directory, per session.

Adapted from garrytan/gstack @ b9706f36 freeze/bin/check-freeze.sh (MIT).
Two deliberate changes:
  - State is keyed by session id (~/.local/state/gs/freeze/<session>.txt), not one
    global file, so a freeze in one agent session never blocks a concurrent one.
  - No analytics or telemetry writes.

Usage:
  check_freeze.py set <dir>   freeze this session to <dir> (uses CLAUDE_CODE_SESSION_ID)
  check_freeze.py clear       remove this session's freeze
  check_freeze.py status      print this session's boundary, or "none"
  check_freeze.py             PreToolUse hook mode: reads the tool payload on stdin

Hook polarity is fail-closed: a payload that cannot be parsed, or any unexpected
error, is DENIED. A payload with no file_path (not a file tool) is allowed.
"""
import json
import os
import sys
from pathlib import Path

STATE = Path.home() / ".local/state/gs/freeze"


def _state_file(session: str) -> Path:
    safe = "".join(c for c in session if c.isalnum() or c in "-_")
    if not safe:
        raise ValueError("empty session id")
    return STATE / f"{safe}.txt"


def _decide(decision: str, reason: str = "") -> None:
    if decision == "allow":
        print("{}")
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}))


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def hook(raw: str) -> None:
    try:
        payload = json.loads(raw)
    except ValueError:
        _decide("deny", "[gs-freeze] Could not parse the tool payload. Blocked (fail closed).")
        return
    session = payload.get("session_id") or ""
    try:
        state = _state_file(session)
    except ValueError:
        _decide("deny", "[gs-freeze] No session id in the tool payload. Blocked (fail closed).")
        return
    if not state.is_file():
        _decide("allow")
        return
    boundary = state.read_text().strip()
    if not boundary:
        # The state file exists, so a freeze was set; an empty one is corrupt, not
        # lifted. `clear` deletes the file (review of 1d17806 found this allowed all).
        _decide("deny", "[gs-freeze] Freeze state is empty or corrupt. Blocked (fail closed). "
                        "Run the gs-freeze skill with 'clear' to lift it.")
        return
    file_path = (payload.get("tool_input") or {}).get("file_path") or (
        payload.get("tool_input") or {}).get("notebook_path")
    if not file_path:
        _decide("allow")
        return
    cwd = payload.get("cwd") or os.getcwd()
    target = Path(os.path.join(cwd, os.path.expanduser(file_path))).resolve()
    root = Path(boundary).resolve()
    if _inside(target, root):
        _decide("allow")
    else:
        _decide("deny", f"[gs-freeze] Blocked: {target} is outside the freeze boundary ({root}). "
                        "Only edits inside the frozen directory are allowed. Run the gs-freeze "
                        "skill with 'clear' to lift it.")


def main() -> int:
    args = sys.argv[1:]
    if not args:
        try:
            hook(sys.stdin.read())
        except Exception as exc:  # fail closed on anything unexpected
            _decide("deny", f"[gs-freeze] Hook error ({type(exc).__name__}). Blocked (fail closed).")
        return 0
    session = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    state = _state_file(session)
    if args[0] == "set" and len(args) == 2:
        root = Path(os.path.expanduser(args[1])).resolve()
        if not root.is_dir():
            print(f"not a directory: {root}", file=sys.stderr)
            return 2
        STATE.mkdir(parents=True, exist_ok=True)
        state.write_text(str(root) + "\n")
        print(f"Freeze boundary set for this session: {root}")
        return 0
    if args[0] == "clear":
        state.unlink(missing_ok=True)
        print("Freeze cleared for this session.")
        return 0
    if args[0] == "status":
        print(state.read_text().strip() if state.is_file() else "none")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
