#!/usr/bin/env python3
"""PreToolUse hook — enforces the autonomy-ladder L3 gate at the tool-call layer.

RA-6874. Reads the Claude Code PreToolUse JSON on stdin; if the pending tool
call is L3 (or a HARD_STOP is active) it emits a ``deny`` decision, otherwise it
stays silent so the normal permission flow applies. The hook performs no actions
— all logic lives in the pure, unit-tested ``swarm.nexus.autonomy_gate`` module.
"""
import json
import os
import sys

# Make ``swarm`` importable whether invoked from the repo root or elsewhere
# (this file lives at <repo>/.claude/hooks/).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from swarm.nexus.autonomy_gate import decide  # noqa: E402

HARD_STOP_PATH = os.path.expanduser("~/.claude/HARD_STOP")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        # A broken gate must not brick the harness. Stay silent: the underlying
        # Claude Code permission flow (and the human) still gate the call.
        return 0

    decision = decide(
        payload.get("tool_name", ""),
        payload.get("tool_input", {}) or {},
        hard_stop=os.path.exists(HARD_STOP_PATH),
    )
    if decision is None:
        return 0

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision["permissionDecision"],
            "permissionDecisionReason": decision["permissionDecisionReason"],
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
