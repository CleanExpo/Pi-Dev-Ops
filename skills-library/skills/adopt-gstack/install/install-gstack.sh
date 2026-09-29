#!/usr/bin/env bash
# Install gstack (github.com/garrytan/gstack) for Claude Code and Codex at ONE pinned,
# reviewed commit, curated to an allowlist, without touching ~/.claude/settings.json.
#
#   bash install-gstack.sh          install / re-sync (idempotent)
#   bash install-gstack.sh --check  verify only; exit 1 on any drift
#
# Why each guard exists (proven 2026-09-24 in a throwaway HOME):
#   --no-timeline-stop-hook / --no-plan-tune-hooks  default setup adds a Stop hook to settings.json
#   --prefix     default names (review, browse, benchmark) collide with our own skills
#   allowlist    ~55 skill descriptions bloat every session's listing
#   pin          upstream ships daily; an unreviewed update must not reach every machine
set -euo pipefail

PIN="b9706f3635b6a545f46fae607ae9d6bcbfb69b91"   # v1.88.1.0, 2026-09-22
SRC="${GSTACK_SRC:-$HOME/Developer/gstack-pinned}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
ALLOW="$HERE/allowlist.txt"
CLAUDE_SKILLS="$HOME/.claude/skills"
CODEX_SKILLS="${CODEX_HOME:-$HOME/.codex}/skills"
SETTINGS="$HOME/.claude/settings.json"
CONFIG="$HOME/.gstack/config.yaml"
# Codex keeps its fuller set, minus anything that merges, deploys, copies browser cookies,
# pairs a remote agent, or self-upgrades past the pin.
CODEX_DENY="gstack-land-and-deploy gstack-setup-deploy gstack-setup-browser-cookies gstack-pair-agent gstack-upgrade"

allowed() { grep -v '^#' "$ALLOW" | grep -qx "$1"; }

check() {
  local bad=0
  [ "$(git -C "$SRC" rev-parse HEAD 2>/dev/null)" = "$PIN" ] || { echo "FAIL: $SRC is not at pin $PIN"; bad=1; }
  if [ -f "$SETTINGS" ] && grep -q gstack "$SETTINGS"; then echo "FAIL: gstack hook present in $SETTINGS"; bad=1; fi
  local have want
  have="$(ls "$CLAUDE_SKILLS" 2>/dev/null | grep '^gstack-' | sort || true)"
  want="$(grep -v '^#' "$ALLOW" | sort)"
  [ "$have" = "$want" ] || { echo "FAIL: installed gstack-* skills differ from allowlist"; diff <(echo "$want") <(echo "$have") || true; bad=1; }
  for kv in 'telemetry: *off' 'auto_upgrade: *false' 'proactive: *false'; do
    grep -Eq "^$kv" "$CONFIG" 2>/dev/null || { echo "FAIL: $CONFIG lacks '$kv'"; bad=1; }
  done
  for d in $CODEX_DENY; do
    # -L too: [ -e ] is false for a dangling symlink, which would read as absent.
    if [ -e "$CODEX_SKILLS/$d" ] || [ -L "$CODEX_SKILLS/$d" ]; then echo "FAIL: denied Codex skill present: $d"; bad=1; fi
  done
  [ "$bad" -eq 0 ] && echo "gstack OK: pin ${PIN:0:8}, $(echo "$have" | grep -c .) Claude skills, settings.json clean"
  return "$bad"
}

if [ "${1:-}" = "--check" ]; then check; exit $?; fi

command -v bun >/dev/null || { echo "gstack: bun not found (https://bun.sh) - skipped"; exit 0; }

# 1. Source at the pin. $SRC is installer-owned: ./setup --prefix rewrites tracked SKILL.md
#    files there on every run, so working-tree edits are discarded. Local COMMITS are not -
#    they are someone's work, and the install refuses rather than orphan them.
if [ ! -d "$SRC/.git" ]; then
  git clone -q https://github.com/garrytan/gstack.git "$SRC"
fi
git -C "$SRC" fetch -q origin
if [ -n "$(git -C "$SRC" rev-list -n 1 HEAD --not --remotes)" ]; then
  echo "gstack: $SRC has local commits not on origin - refusing to move it to the pin. Inspect it first." >&2
  exit 1
fi
git -C "$SRC" checkout -q -f "$PIN"

# 2. Mac mini: the Playwright cache is a symlink onto Storage Unit; its target must exist.
PW="$HOME/Library/Caches/ms-playwright-gstack"
if [ -L "$PW" ] && [ ! -e "$PW" ]; then
  t="$(readlink "$PW")"
  case "$t" in /*) ;; *) t="$(dirname "$PW")/$t" ;; esac
  mkdir -p "$t"
fi
[ -e "$PW" ] && export PLAYWRIGHT_BROWSERS_PATH="$PW"

# 3. Run upstream setup with every settings.json mutation switched off.
before="$( [ -f "$SETTINGS" ] && shasum "$SETTINGS" || echo none)"
( cd "$SRC" && ./setup --host claude --prefix --no-team --no-plan-tune-hooks --no-timeline-stop-hook </dev/null )
if command -v codex >/dev/null; then
  ( cd "$SRC" && ./setup --host codex --prefix --no-team </dev/null )
fi
after="$( [ -f "$SETTINGS" ] && shasum "$SETTINGS" || echo none)"
[ "$before" = "$after" ] || { echo "gstack: settings.json CHANGED during setup - inspect it; not reverting peer edits" >&2; exit 1; }

# 4. Prune to the allowlist. Only directories setup marked as its own are ever removed.
for d in "$CLAUDE_SKILLS"/gstack-*/; do
  n="$(basename "$d")"
  allowed "$n" && continue
  [ -f "$d/.gstack-owned" ] && rm -rf "$d"
done
for n in $CODEX_DENY; do
  [ -L "$CODEX_SKILLS/$n" ] && rm "$CODEX_SKILLS/$n"
done

# 5. Config: no telemetry, no silent upgrade past the pin, invoke only when named or routed.
GC="$SRC/bin/gstack-config"
"$GC" set telemetry off
"$GC" set auto_upgrade false
"$GC" set proactive false
"$GC" set routing_declined true

check
