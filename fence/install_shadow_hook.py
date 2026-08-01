#!/usr/bin/env python3
"""install_shadow_hook.py — register the fence as a PreToolUse hook, SHADOW only.

Idempotent. Does not touch the PermissionRequest auto-allow hook.
Reverse with uninstall_hook.py, or restore the timestamped settings backup.
"""
import json
import pathlib
import sys

SETTINGS = pathlib.Path.home() / ".claude" / "settings.json"
CMD = '/usr/bin/env python3 "/c/Users/Disaster Recovery 4/.claude/fence/pretooluse_fence.py"'

d = json.loads(SETTINGS.read_text(encoding="utf-8"))
hooks = d.setdefault("hooks", {})
existing = hooks.get("PreToolUse", [])

if any("pretooluse_fence" in json.dumps(e) for e in existing):
    print("already registered — not duplicating")
else:
    hooks["PreToolUse"] = existing + [{
        "matcher": "*",
        "hooks": [{"type": "command", "command": CMD,
                   "statusMessage": "fence (shadow: observing only)"}],
    }]
    SETTINGS.write_text(json.dumps(d, indent=2), encoding="utf-8")
    print("PreToolUse registered (shadow, matcher='*')")

check = json.loads(SETTINGS.read_text(encoding="utf-8"))
print("hook events now:", list(check["hooks"].keys()))
print("PreToolUse entries:", len(check["hooks"].get("PreToolUse", [])))
print("PermissionRequest auto-allow left in place:", "PermissionRequest" in check["hooks"])
sys.exit(0)
