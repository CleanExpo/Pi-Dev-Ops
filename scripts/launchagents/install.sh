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

AGENTS="com.pi-ceo.data-ingestion com.pi-ceo.improve-system com.unite.hermes-model-health"

for f in $AGENTS; do
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
[ -f "$PROD/hermes_model_chain_health.py" ] || { echo "WARN: $PROD/hermes_model_chain_health.py missing — worktree not on a branch with the scripts"; exit 1; }

# The health check needs PyYAML. /usr/bin/python3 does not have it, so fail here
# rather than at 09:15 tomorrow into a log nobody is reading.
/opt/homebrew/bin/python3 -c 'import yaml' 2>/dev/null || { echo "WARN: /opt/homebrew/bin/python3 lacks PyYAML — hermes-model-health would fail every run"; exit 1; }

for f in $AGENTS; do
  cp "$HERE/$f.plist" "$DEST/$f.plist"
  launchctl bootout "gui/$(id -u)/$f" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$DEST/$f.plist"
  echo "installed + loaded: $f"
done
echo "Done. Verify: launchctl list | grep -E 'pi-ceo|unite'"
echo
echo "hermes-model-health: prove it can fail before trusting a pass —"
echo "  /opt/homebrew/bin/python3 $PROD/hermes_model_chain_health.py --inject-broken"
