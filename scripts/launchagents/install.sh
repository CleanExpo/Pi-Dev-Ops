#!/usr/bin/env bash
# install.sh — install the self-improving-system LaunchAgents.
#
# The plists run their scripts from a dedicated git worktree pinned to `main`
# (~/Pi-CEO/Pi-Dev-Ops-routines), NOT the live dev checkout (/Users/phill-mac/Pi-Dev-Ops).
# The dev checkout doubles as a human workspace and gets parked on feature
# branches that predate these scripts, which would make every fire log
# file-not-found. A main-pinned worktree never moves when the dev checkout
# switches branches. This script creates that worktree if it is missing.
#
# Validates plists, copies them to ~/Library/LaunchAgents, and (re)loads them.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/Library/LaunchAgents"
REPO="/Users/phill-mac/Pi-Dev-Ops"
WORKTREE="/Users/phill-mac/Pi-CEO/Pi-Dev-Ops-routines"
PROD="$WORKTREE/scripts"

for f in com.pi-ceo.data-ingestion com.pi-ceo.improve-system; do
  plutil -lint "$HERE/$f.plist"                      # fail fast on malformed plist
done

# Create the main-pinned worktree on first install (idempotent).
if [ ! -d "$WORKTREE" ]; then
  echo "creating routines worktree (main) at $WORKTREE"
  git -C "$REPO" fetch origin main --quiet || true
  git -C "$REPO" worktree add "$WORKTREE" main
fi

[ -f "$PROD/data_ingestion.sh" ] || { echo "WARN: $PROD/data_ingestion.sh missing — worktree not on a branch with the scripts"; exit 1; }
[ -f "$PROD/improve_system.py" ] || { echo "WARN: $PROD/improve_system.py missing — worktree not on a branch with the scripts"; exit 1; }

for f in com.pi-ceo.data-ingestion com.pi-ceo.improve-system; do
  cp "$HERE/$f.plist" "$DEST/$f.plist"
  launchctl bootout "gui/$(id -u)/$f" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$DEST/$f.plist"
  echo "installed + loaded: $f"
done
echo "Done. Verify: launchctl list | grep pi-ceo"
