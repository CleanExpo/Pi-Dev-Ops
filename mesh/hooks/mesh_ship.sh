#!/usr/bin/env bash
# Nexus Mesh — ship a turn's work, whether or not it is already committed.
#
# RA-7376: `autogit ship` is not "push this branch". It is "stage -> commit ->
# push my uncommitted turn output": with a clean tree it returns silently and
# pushes nothing, including commits already sitting on the branch. Every
# discipline in this estate tells an agent to commit its own work with a real
# message, and the handoff gate requires a clean tree — so a well-behaved agent
# ends its turn with nothing staged and the Stop hook becomes a guaranteed
# no-op. The work never leaves the machine.
#
# This wrapper runs autogit first (it still owns uncommitted work and commit
# subjects), then pushes the branch itself when commits remain unshipped. It
# also survives autogit being absent from PATH entirely, which was the separate
# first cause in RA-6505 — that produced the identical symptom of zero
# refs/heads/mesh/* on origin.
#
# Safety: only mesh/* work branches are ever pushed, never a protected or human
# review branch, and never with force. Every outcome is logged, because the
# `|| true` that keeps a Stop hook non-blocking is exactly what made both causes
# invisible for so long.
#
# Env: MESH_SHIP_LOG (default ~/.hermes/mesh-ship.log) · MESH_SHIP_REMOTE
#      (default origin). Always exits 0 — a ship failure must never break the
#      agent turn, only become loud.
set -uo pipefail

LOG="${MESH_SHIP_LOG:-$HOME/.hermes/mesh-ship.log}"

# log: append one timestamped line to the ship log. Never fails the hook.
log() {
  mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG" 2>/dev/null || true
}

# Hermes pipes a JSON payload carrying `cwd`; Claude/Codex Stop hooks pipe their
# own event JSON. Read it only when stdin is not a terminal, so an interactive
# run cannot hang waiting for input.
payload=""
if [ ! -t 0 ]; then payload="$(cat 2>/dev/null || true)"; fi

if [ -n "$payload" ]; then
  cwd="$(printf '%s' "$payload" | python3 -c 'import sys,json
try:
    d = json.load(sys.stdin); print(d.get("cwd") or "")
except Exception:
    print("")' 2>/dev/null || true)"
  [ -n "$cwd" ] && cd "$cwd" 2>/dev/null || true
fi

branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
if [ -z "$branch" ]; then log "skip: not a git repository ($PWD)"; exit 0; fi

# Never auto-ship human or agent review branches, or anything protected.
case "$branch" in
  feat/*|feature/*|fix/*|main|master|HEAD) log "skip: protected/review branch $branch"; exit 0 ;;
esac

# Opt-in marker. hermes_ship.sh always documented this requirement but only ever
# checked whether autogit was installed, so an un-opted-in repo could be shipped.
root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$root" ] || [ ! -f "$root/.autogit.json" ]; then
  log "skip: no .autogit.json opt-in at ${root:-$PWD}"
  exit 0
fi

# 1. autogit still owns uncommitted work and mines the payload for a subject.
if command -v autogit >/dev/null 2>&1; then
  printf '%s' "$payload" | autogit ship >/dev/null 2>&1
  rc=$?
  [ $rc -eq 0 ] || log "autogit ship exited rc=$rc on $branch (continuing to direct push)"
else
  log "autogit not on PATH — direct push only (RA-6505 symptom) on $branch"
fi

# 2. RA-7376: ship what autogit leaves behind. Restricted to mesh/* work
#    branches, which mesh/runner.py creates as mesh/<host>/<ticket>-<run>.
case "$branch" in
  mesh/*) ;;
  *) log "no push: $branch is not a mesh/* work branch"; exit 0 ;;
esac

remote="${MESH_SHIP_REMOTE:-origin}"
if ! git remote get-url "$remote" >/dev/null 2>&1; then
  log "no push: remote '$remote' not configured"
  exit 0
fi
if ! git rev-parse --verify -q HEAD >/dev/null 2>&1; then
  log "no push: branch $branch has no commits"
  exit 0
fi

# The push itself is the ahead-check: it is a no-op when the remote already has
# these commits, which keeps this correct against a stale remote-tracking ref.
# Explicit refspec, never a force.
out="$(git push "$remote" "HEAD:refs/heads/$branch" 2>&1)"; rc=$?
head_sha="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
if [ $rc -eq 0 ]; then
  if printf '%s' "$out" | grep -qi 'everything up-to-date'; then
    log "up-to-date: $branch already on $remote at $head_sha"
  else
    log "pushed: $branch -> $remote at $head_sha"
  fi
else
  # Loud on failure: a silent ship failure is the defect this file exists to end.
  log "PUSH FAILED rc=$rc on $branch at $head_sha: $(printf '%s' "$out" | tr '\n' ' ' | tail -c 300)"
  printf 'mesh_ship: push of %s failed (rc=%s) — see %s\n' "$branch" "$rc" "$LOG" >&2
fi
exit 0
