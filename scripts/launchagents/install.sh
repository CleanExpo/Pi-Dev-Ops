#!/usr/bin/env bash
# install.sh — install the self-improving-system LaunchAgents.
#
# RUN AFTER this PR merges AND the production checkout (~/Pi-CEO/Pi-Dev-Ops, the
# path the existing pi-ceo LaunchAgents use) has pulled the new scripts. The
# plists point at that path; installing before the scripts exist there would log
# file-not-found on the first fire.
#
# Validates plists, copies them to ~/Library/LaunchAgents, and (re)loads them.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/Library/LaunchAgents"
PROD="$HOME/Pi-CEO/Pi-Dev-Ops/scripts"

for f in com.pi-ceo.data-ingestion com.pi-ceo.improve-system; do
  plutil -lint "$HERE/$f.plist"                      # fail fast on malformed plist
done
[ -f "$PROD/data_ingestion.sh" ] || { echo "WARN: $PROD/data_ingestion.sh missing — pull the prod checkout first"; exit 1; }
[ -f "$PROD/improve_system.py" ] || { echo "WARN: $PROD/improve_system.py missing — pull the prod checkout first"; exit 1; }

for f in com.pi-ceo.data-ingestion com.pi-ceo.improve-system; do
  cp "$HERE/$f.plist" "$DEST/$f.plist"
  launchctl bootout "gui/$(id -u)/$f" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$DEST/$f.plist"
  echo "installed + loaded: $f"
done
echo "Done. Verify: launchctl list | grep pi-ceo"
