#!/usr/bin/env bash
# Sync ~/.hermes/plugins/ <-> Pi-Dev-Ops/hermes-plugins/
#
# Usage:
#   ./scripts/sync-hermes-plugins.sh pull   # ~/.hermes/plugins/  →  repo
#   ./scripts/sync-hermes-plugins.sh push   # repo  →  ~/.hermes/plugins/
#   ./scripts/sync-hermes-plugins.sh diff   # show drift without touching anything
#
# Hermes plugins live at ~/.hermes/plugins/<name>/ at runtime; they are not
# under git there. This script keeps them backed up in Pi-Dev-Ops so the
# work survives a Hermes reinstall or fresh-Mac setup.

set -euo pipefail

LOCAL="${HOME}/.hermes/plugins"
REPO="$(cd "$(dirname "$0")/.." && pwd)/hermes-plugins"

# Plugins under management. Add new ones here.
PLUGINS=(unite-group)

mode="${1:-}"
if [[ -z "$mode" ]]; then
    echo "Usage: $0 {pull|push|diff}" >&2
    exit 2
fi

case "$mode" in
    pull)
        # Local (authoritative) → repo
        for p in "${PLUGINS[@]}"; do
            [[ -d "$LOCAL/$p" ]] || { echo "skip: $LOCAL/$p does not exist"; continue; }
            mkdir -p "$REPO/$p"
            # rsync respects extant target file mtimes; only updates changed content
            rsync -a --delete \
                --exclude='__pycache__' --exclude='*.pyc' \
                "$LOCAL/$p/" "$REPO/$p/"
            echo "pulled $p → $REPO/$p"
        done
        echo "✅ done — review with: git -C $(dirname "$REPO") status hermes-plugins"
        ;;
    push)
        # Repo (authoritative after a pull or fresh-clone) → local
        for p in "${PLUGINS[@]}"; do
            [[ -d "$REPO/$p" ]] || { echo "skip: $REPO/$p does not exist"; continue; }
            mkdir -p "$LOCAL/$p"
            rsync -a --delete \
                --exclude='__pycache__' --exclude='*.pyc' \
                "$REPO/$p/" "$LOCAL/$p/"
            echo "pushed $p → $LOCAL/$p"
        done
        echo "✅ done — restart hermes gateway to pick up: launchctl kickstart -k gui/\$(id -u)/ai.hermes.gateway"
        ;;
    diff)
        any_drift=0
        for p in "${PLUGINS[@]}"; do
            echo "─── $p ───"
            if [[ ! -d "$LOCAL/$p" ]]; then
                echo "  LOCAL missing: $LOCAL/$p"
                any_drift=1
                continue
            fi
            if [[ ! -d "$REPO/$p" ]]; then
                echo "  REPO missing: $REPO/$p"
                any_drift=1
                continue
            fi
            # Use diff -r to show the differences, excluding __pycache__
            if diff -r -q \
                --exclude='__pycache__' --exclude='*.pyc' \
                "$LOCAL/$p" "$REPO/$p" 2>&1 | head -50; then
                :
            fi
            if ! diff -r -q \
                --exclude='__pycache__' --exclude='*.pyc' \
                "$LOCAL/$p" "$REPO/$p" >/dev/null 2>&1; then
                any_drift=1
            fi
        done
        if [[ "$any_drift" -eq 0 ]]; then
            echo "✅ no drift"
        else
            echo "⚠️  drift detected — run pull or push to resolve"
            exit 1
        fi
        ;;
    *)
        echo "Unknown mode: $mode (use pull, push, or diff)" >&2
        exit 2
        ;;
esac
