#!/usr/bin/env bash
# Nexus Mesh — Hermes → autogit adapter.
# Wired as a Hermes on_session_end shell hook (see mesh/bootstrap.sh). Hermes pipes
# a JSON payload on stdin carrying `cwd`; we cd there and let autogit ship the turn.
# Closes the work-plane loop for Hermes-driven turns, same as Claude/Codex Stop hooks.
set -euo pipefail

payload="$(cat || true)"

# Extract cwd from the payload without a jq dependency.
cwd="$(printf '%s' "$payload" | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin); print(d.get("cwd") or "")
except Exception:
    print("")' 2>/dev/null || true)"

[ -n "$cwd" ] && cd "$cwd" 2>/dev/null || true

# Only ship inside a git repo that opted in (autogit on → .autogit.json present).
command -v autogit >/dev/null 2>&1 || exit 0
# Re-feed the payload so autogit can mine the prompt for the commit subject.
printf '%s' "$payload" | autogit ship 2>/dev/null || true
exit 0
