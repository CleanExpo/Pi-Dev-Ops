#!/bin/bash
# C7: fleet.py probe resolves the MacBook and the PC (no "Could not resolve hostname").
# Reachability past name lookup (keys, users) is reported, not required: that is a key step.
set -u
out="$(/opt/homebrew/bin/python3 /Users/phill-mac/.claude/skills/fleet-compute/scripts/fleet.py probe --json 2>&1)"
printf '%s' "$out" | /opt/homebrew/bin/python3 -c '
import json, sys
raw = sys.stdin.read()
try:
    data = json.loads(raw)
except ValueError:
    print("FAIL: probe output is not JSON: %r" % raw[:200]); sys.exit(1)
nodes = data if isinstance(data, list) else data.get("nodes", data)
items = nodes.items() if isinstance(nodes, dict) else [(n.get("node"), n) for n in nodes]
bad = 0
seen = set()
for name, n in items:
    if name not in ("macbook", "windows"):
        continue
    seen.add(name)
    err = str(n.get("error") or "")
    print("%s reachable=%s error=%s" % (name, n.get("reachable"), err[:160]))
    if "Could not resolve hostname" in err:
        bad += 1
if seen != {"macbook", "windows"}:
    print("FAIL: probe did not report both macbook and windows: %s" % sorted(seen)); sys.exit(1)
sys.exit(1 if bad else 0)
'
