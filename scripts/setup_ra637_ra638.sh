#!/bin/bash
# Pi-CEO | RA-637 Setup (file name kept for existing references)
# RA-637: Mac Mini sleep prevention + auto-restart after power failure
# RA-638 (the local-model watchdog) was removed on 21/10/2026 with the runtime it
# watched; this script no longer installs or loads it.
set -e

echo "=== Pi-CEO | RA-637 Setup ==="
echo ""

# ─── RA-637: Power management ─────────────────────────────────────────────────
echo "[RA-637] Applying Mac Mini power settings..."
sudo pmset -a sleep 0          # Never sleep the system
sudo pmset -a disksleep 0      # Never spin down drives
sudo pmset -a displaysleep 15  # Display sleeps after 15 min (fine for server)
sudo pmset -a autorestart 1    # Auto-restart after power failure
sudo pmset -a womp 1           # Wake on network access
echo "[RA-637] Done. Current settings:"
pmset -g | grep -E "sleep|autorestart|womp"
echo ""
echo "=== Setup Complete ==="
echo "RA-637: Sleep=off, autorestart=on, display-sleep=15min"
