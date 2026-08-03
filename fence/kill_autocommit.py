#!/usr/bin/env python3
"""kill_autocommit.py — remove every automatic commit/push write path.

WHY: an `autogit busy` hook wired into Claude Code's UserPromptSubmit and
PostToolUse events was committing the working tree and pushing to GitHub,
authored as the founder, with no review. It ran outside the fence (hooks fire
around tool calls, not through PreToolUse), and because Codex runs with
workspace-write it meant the *reviewer* effectively had commit rights — which
breaks "flags, does not fix" structurally.

Kills three things:
  1. the two `autogit busy` hooks in ~/.claude/settings.json
  2. .autogit.json  {"mode":"auto"}  ->  {"mode":"off"}   (belt and braces)
  3. the Codex `notify` hook, which wrote .omx telemetry into the repo that
     autogit then committed

Idempotent. Backups are written by the caller before this runs.
"""
import json
import pathlib
import re
import sys

SETTINGS = pathlib.Path.home() / ".claude" / "settings.json"
CODEX = pathlib.Path.home() / ".codex" / "config.toml"
AUTOGIT = pathlib.Path(r"D:\Pi-Dev-Ops\.autogit.json")

removed = []

# 1 — settings.json hooks
d = json.loads(SETTINGS.read_text(encoding="utf-8"))
hooks = d.get("hooks", {})
for event in list(hooks):
    kept_matchers = []
    for matcher in hooks[event]:
        kept = [h for h in matcher.get("hooks", [])
                if "autogit" not in str(h.get("command", ""))]
        dropped = len(matcher.get("hooks", [])) - len(kept)
        if dropped:
            removed.append(f"settings.json {event}: {dropped} autogit hook(s)")
        if kept:
            matcher["hooks"] = kept
            kept_matchers.append(matcher)
    if kept_matchers:
        hooks[event] = kept_matchers
    else:
        del hooks[event]
        removed.append(f"settings.json {event}: event removed (was autogit-only)")
SETTINGS.write_text(json.dumps(d, indent=2), encoding="utf-8")

# 2 — .autogit.json
if AUTOGIT.exists():
    a = json.loads(AUTOGIT.read_text(encoding="utf-8"))
    if a.get("mode") != "off":
        a["mode"] = "off"
        a["_disabled"] = "2026-08-01 founder directive: autogit committed as the founder and pushed unreviewed, outside the fence."
        AUTOGIT.write_text(json.dumps(a, indent=2), encoding="utf-8")
        removed.append(".autogit.json: mode auto -> off")

# 3 — Codex notify hook
if CODEX.exists():
    t = CODEX.read_text(encoding="utf-8")
    t2 = re.sub(r"^notify = \[[\s\S]*?\]\s*$", "", t, count=1, flags=re.M)
    if t2 != t:
        CODEX.write_text(t2, encoding="utf-8")
        removed.append("codex config.toml: notify hook removed")

print("REMOVED:" if removed else "NOTHING TO REMOVE (already clean)")
for r in removed:
    print("  -", r)

# verify
d2 = json.loads(SETTINGS.read_text(encoding="utf-8"))
still = [f"{ev}" for ev, arr in d2.get("hooks", {}).items()
         for m in arr for h in m.get("hooks", [])
         if "autogit" in str(h.get("command", ""))]
print("\nVERIFY")
print("  autogit hooks remaining in settings.json:", still or "NONE")
print("  settings.json valid JSON: yes")
print("  codex notify remaining:",
      "yes" if CODEX.exists() and re.search(r"^notify = \[", CODEX.read_text(encoding='utf-8'), re.M) else "NONE")
print("  .autogit.json mode:",
      json.loads(AUTOGIT.read_text(encoding="utf-8")).get("mode") if AUTOGIT.exists() else "absent")
sys.exit(0)
