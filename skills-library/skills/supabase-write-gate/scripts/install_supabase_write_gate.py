#!/usr/bin/env python3
"""Install the Supabase write gate into this machine's settings.json.

Idempotent. Backs up first. Validates the JSON before and after writing.

This exists because ~/.claude/hooks/ and settings.json are gitignored, so the gate
does not propagate by syncing the repo. Every machine has to run this, and
bootstrap.sh calls it so a fresh machine gets it without anyone remembering.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

SETTINGS = Path.home() / ".claude" / "settings.json"
HOOK = Path.home() / ".claude" / "hooks" / "PreToolUse" / "supabase_write_gate.py"
MATCHER = "mcp__.*[Ss]upabase.*"
COMMAND = f"/usr/bin/env python3 {HOOK}"


def main() -> int:
    if not HOOK.exists():
        print(f"FAIL: hook not found at {HOOK}", file=sys.stderr)
        return 1
    if not SETTINGS.exists():
        print(f"FAIL: no settings.json at {SETTINGS}", file=sys.stderr)
        return 1

    data = json.loads(SETTINGS.read_text())  # fail fast on an already-broken file
    pre = data.setdefault("hooks", {}).setdefault("PreToolUse", [])

    for matcher in pre:
        for hook in matcher.get("hooks", []):
            if "supabase_write_gate.py" in hook.get("command", ""):
                print(f"ALREADY REGISTERED under matcher: {matcher.get('matcher')}")
                return 0

    backup = SETTINGS.with_suffix(f".json.bak.{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(SETTINGS, backup)
    print(f"backup: {backup}")

    pre.append({"matcher": MATCHER, "hooks": [{"type": "command", "command": COMMAND}]})

    out = json.dumps(data, indent=2) + "\n"
    json.loads(out)  # never write what will not parse

    tmp = SETTINGS.with_suffix(".json.tmp")
    tmp.write_text(out)
    os.replace(tmp, SETTINGS)
    print(f"REGISTERED PreToolUse[{MATCHER}] -> supabase_write_gate.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
