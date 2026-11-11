#!/usr/bin/env python3
"""Install the Supabase write gate into this machine's settings.json.

Idempotent. Backs up first. Validates the JSON before and after writing.

This exists because ~/.claude/hooks/ and settings.json are gitignored, so the gate
does not propagate by syncing the repo. Every machine has to run this, and
bootstrap.sh calls it so a fresh machine gets it without anyone remembering.

MATCHERS (grill 18, 07/11/2026). The gate reads the Supabase MCP tools AND the two shell
tools. This installer used to register only the MCP matcher and stop at the first match;
the Bash matcher was added by hand on some machines and PowerShell on none, so a command
refused under Bash ran through PowerShell unchecked. Each matcher is now ensured on its
own, so re-running upgrades a machine that has only some of them.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

# The shared rule for "is this hook entry installed". No fallback: an installer that cannot
# load the rule must stop, not guess.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks" / "lib"))
from hook_entry import ensure, installed  # noqa: E402

SETTINGS = Path.home() / ".claude" / "settings.json"
HOOK = Path.home() / ".claude" / "hooks" / "PreToolUse" / "supabase_write_gate.py"
MATCHERS = ("mcp__.*[Ss]upabase.*", "Bash", "PowerShell")


def hook_command() -> str:
    # Quoted for homes with spaces. On Windows /usr/bin/env resolves to nothing useful
    # (or the WindowsApps stub), so name this interpreter, as install_pr_release_gate does.
    if os.name == "nt":
        return f'"{sys.executable}" "{HOOK}"'
    return f'/usr/bin/env python3 "{HOOK}"'


def main() -> int:
    if not HOOK.exists():
        print(f"FAIL: hook not found at {HOOK}", file=sys.stderr)
        return 1
    if not SETTINGS.exists():
        print(f"FAIL: no settings.json at {SETTINGS}", file=sys.stderr)
        return 1

    data = json.loads(SETTINGS.read_text(encoding="utf-8"))  # fail fast on a broken file
    pre = data.setdefault("hooks", {}).setdefault("PreToolUse", [])

    # Installed is decided by the one shared rule (hooks/lib/hook_entry.py): this installer's
    # exact command, in exactly the entry shape it writes, under the exact matcher. Reviews of
    # a7ea0f3b, db611864, 5b79b600 and 62e07dd6 each found an entry taken for the gate that was
    # not one (lookalike name, echo, "async": true, "type": "prompt").
    command = hook_command()
    missing = [m for m in MATCHERS if not installed(pre, m, lambda c: c == command)]
    if not missing:
        print(f"ALREADY REGISTERED under every matcher: {', '.join(MATCHERS)}")
        return 0

    backup = SETTINGS.with_suffix(f".json.bak.{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(SETTINGS, backup)
    print(f"backup: {backup}")

    ensure(pre, missing, command)

    out = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    json.loads(out)  # never write what will not parse

    tmp = SETTINGS.with_suffix(".json.tmp")
    tmp.write_text(out, encoding="utf-8")
    os.replace(tmp, SETTINGS)
    for matcher in missing:
        print(f"REGISTERED PreToolUse[{matcher}] -> supabase_write_gate.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
