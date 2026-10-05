#!/usr/bin/env bash
# cloud-pull — report this container's estate membership. READ-ONLY.
#
# The cloud equivalent of an estate-sync pull cycle. estate-sync itself cannot run here:
# it installs a macOS LaunchAgent or a Windows Task Scheduler job on a 15-minute timer,
# and this container is ephemeral with neither. So membership is established per session,
# on demand, by this script.
#
# It never writes to the checkout, never commits, and never pushes. Its whole job is to
# answer: which estate am I looking at, is it current, and what is waiting for me.
set -uo pipefail

REPO="${SKILLS_LIBRARY_DIR:-$HOME/skills-library}"
[ -d "$REPO/.git" ] || REPO="$HOME/.claude"

say() { printf '%s\n' "$*"; }
warn() { printf '%s\n' "$*" >&2; }

say "== estate membership =="

if [ ! -d "$REPO/.git" ]; then
  warn "  no skills-library checkout found."
  warn "  Looked at: \$SKILLS_LIBRARY_DIR, \$HOME/skills-library, \$HOME/.claude"
  warn "  Clone it:  git clone --depth 1 https://github.com/CleanExpo/skills-library $HOME/skills-library"
  exit 1
fi

say "  checkout : $REPO"
say "  branch   : $(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
say "  head     : $(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo '?')"
say "  skills   : $(ls "$REPO/skills" 2>/dev/null | wc -l | tr -d ' ')"

# Freshness. A stale checkout is the quiet failure here: every skill loads, nothing
# errors, and the container acts on a view of the estate that other machines moved past
# hours ago. Report it; never auto-pull, because a fetch that rewrites the tree underneath
# a running session is worse than a stale one you were told about.
if git -C "$REPO" fetch --quiet origin main 2>/dev/null; then
  behind=$(git -C "$REPO" rev-list --count HEAD..origin/main 2>/dev/null || echo '?')
  ahead=$(git -C "$REPO" rev-list --count origin/main..HEAD 2>/dev/null || echo '?')
  if [ "$behind" = "0" ] && [ "$ahead" = "0" ]; then
    say "  sync     : in sync with origin/main"
  else
    say "  sync     : $behind behind, $ahead ahead of origin/main"
    [ "$behind" != "0" ] && say "             pull before trusting skill contents: git -C $REPO pull --rebase origin main"
  fi
else
  warn "  sync     : could not reach origin (offline, or no credentials) — treat contents as UNVERIFIED"
fi

# Which node am I? Ask the registry rather than asserting, for the reason fleet.py records:
# a map that asserts where you are is worse than no map, because it is believed.
FLEET="$REPO/skills/fleet-compute/scripts/fleet.py"
if [ -f "$FLEET" ]; then
  node=$(python3 -c "
import sys; sys.path.insert(0, '$(dirname "$FLEET")')
import fleet; print(fleet.LOCAL_NODE or 'unregistered')
" 2>/dev/null || echo '?')
  say "  node     : $node"
else
  say "  node     : fleet-compute not present in this checkout"
fi

say ""
say "== mail =="
MBOX="$REPO/skills/estate-mailbox/scripts/mailbox.py"
if [ -f "$MBOX" ]; then
  python3 "$MBOX" read 2>&1 | sed 's/^/  /'
else
  say "  estate-mailbox not present in this checkout"
fi

say ""
say "== not available on this node =="
# Stated explicitly because each of these has been assumed present at least once, and an
# assumed capability wastes a session before it is disproved.
say "  Tailscale  : no — this container can never be an ssh dispatch target"
say "  Codex CLI  : $(command -v codex >/dev/null 2>&1 && echo 'present' || echo 'no — dispatch Codex reviews to the mini via fleet.py')"
say "  estate-sync: no — LaunchAgent/Task Scheduler only; this script is the substitute"
