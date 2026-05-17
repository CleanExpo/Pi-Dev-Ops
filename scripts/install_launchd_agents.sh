#!/usr/bin/env bash
# scripts/install_launchd_agents.sh — RA-3752
#
# Idempotent installer for Pi-CEO launchd jobs. Reads the canonical
# plists committed in this repo (scripts/launchd/*.plist) and copies
# them into ~/Library/LaunchAgents/, then bootstraps each with
# launchctl. No more hand-edited ~/Library/LaunchAgents/ files —
# version-controlled drift only.
#
# Detects when any installed plist has drifted vs the canonical (or
# been renamed to *.disabled) and reports.
#
# Usage:
#   ./scripts/install_launchd_agents.sh         # install + bootstrap
#   ./scripts/install_launchd_agents.sh --check # report drift, no-op

set -euo pipefail

CANONICAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/launchd" && pwd)"
TARGET_DIR="$HOME/Library/LaunchAgents"
UID_OWNER="$(id -u)"

# Plists managed by this repo
MANAGED=(
  "com.piceo.fastapi-standby.plist"
  "com.piceo.healthcheck.plist"
)

CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

echo "=== launchd agent installer (RA-3752) ==="
echo "Canonical: $CANONICAL_DIR"
echo "Target:    $TARGET_DIR"
echo ""

drift_count=0
for name in "${MANAGED[@]}"; do
  canonical="$CANONICAL_DIR/$name"
  target="$TARGET_DIR/$name"
  disabled="$TARGET_DIR/$name.disabled"

  if [ ! -f "$canonical" ]; then
    echo "  ⚠️  $name: canonical missing at $canonical — skip"
    continue
  fi

  if [ -f "$disabled" ]; then
    echo "  ⚠️  $name: found *.disabled rename at $disabled"
    drift_count=$((drift_count + 1))
    [ "$CHECK_ONLY" = "1" ] && continue
    mv "$disabled" "$disabled.was-disabled-$(date +%Y%m%d)"
    echo "      moved aside to $disabled.was-disabled-$(date +%Y%m%d)"
  fi

  if [ -f "$target" ]; then
    if ! cmp -s "$canonical" "$target"; then
      echo "  ⚠️  $name: drift detected vs canonical"
      drift_count=$((drift_count + 1))
      [ "$CHECK_ONLY" = "1" ] && continue
      cp "$target" "$target.backup-$(date +%Y%m%d-%H%M%S)"
      echo "      backed up existing to $target.backup-$(date +%Y%m%d-%H%M%S)"
    else
      [ "$CHECK_ONLY" = "1" ] && echo "  ✓  $name: in sync"
      [ "$CHECK_ONLY" = "1" ] && continue
    fi
  fi

  if [ "$CHECK_ONLY" = "1" ]; then
    [ -f "$target" ] || echo "  ⚠️  $name: not installed at $target"
    [ -f "$target" ] || drift_count=$((drift_count + 1))
    continue
  fi

  cp "$canonical" "$target"
  echo "  installed: $target"

  # Bootstrap (idempotent — bootout first if loaded)
  if launchctl print "gui/$UID_OWNER/${name%.plist}" >/dev/null 2>&1; then
    launchctl bootout "gui/$UID_OWNER" "$target" 2>/dev/null || true
  fi
  launchctl bootstrap "gui/$UID_OWNER" "$target" 2>&1 | grep -v "already loaded" || true
  echo "  bootstrapped: ${name%.plist}"
done

echo ""
if [ "$CHECK_ONLY" = "1" ]; then
  if [ "$drift_count" -gt 0 ]; then
    echo "❌ $drift_count drift(s) detected. Run without --check to repair."
    exit 1
  fi
  echo "✓ no drift detected."
fi
