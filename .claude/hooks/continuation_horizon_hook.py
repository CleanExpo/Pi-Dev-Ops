#!/usr/bin/env python3
"""Claude Code hook for Mission Control rolling continuation.

UserPromptSubmit arms/refreshes the objective. Stop blocks premature session
termination while the cross-channel horizon remains active. The hook never
bypasses protected-action gates and honours stop_hook_active to avoid loops.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.server.continuation_horizon import arm_objective, operator_context, should_continue  # noqa: E402


def _read_payload() -> dict:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _prompt_text(payload: dict) -> str:
    for key in ("prompt", "user_prompt", "message", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def main() -> int:
    payload = _read_payload()
    event = str(payload.get("hook_event_name") or payload.get("event") or "").lower()

    if "userpromptsubmit" in event or event == "user_prompt_submit":
        prompt = _prompt_text(payload)
        if prompt:
            arm_objective(objective=prompt, source="claude")
        print(json.dumps({"hookSpecificOutput": {"additionalContext": operator_context()}}))
        return 0

    if "stop" in event:
        if payload.get("stop_hook_active"):
            return 0
        if should_continue():
            print(json.dumps({
                "decision": "block",
                "reason": operator_context() + "\nContinue with the next safe ready moves now. Re-plan/refill the horizon if fewer than 15 useful moves remain. Do not wait for another user message merely because one sub-task finished."
            }))
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
