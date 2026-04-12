#!/bin/bash
# Pi-CEO | RA-637 + RA-638 Setup
# RA-637: Mac Mini sleep prevention + auto-restart after power failure
# RA-638: Ollama watchdog (relaunches Ollama.app if port 11434 goes silent)
set -e

echo "=== Pi-CEO | RA-637 + RA-638 Setup ==="
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

# ─── RA-638: Ollama watchdog ──────────────────────────────────────────────────
echo "[RA-638] Installing Ollama watchdog..."
mkdir -p ~/pi-ceo/logs

# Write the watchdog script
cat > ~/pi-ceo/ollama_watchdog.sh << 'WATCHDOG'
#!/bin/bash
# Pi-CEO Ollama Watchdog — RA-638
# Checks port 11434 every 60s; relaunches Ollama.app if not responding
LOG="$HOME/pi-ceo/logs/ollama_watchdog.log"
if ! curl -sf --max-time 4 http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "$(date '+%Y-%m-%d %H:%M:%S'): Ollama not responding — relaunching Ollama.app" >> "$LOG"
    open -a /Applications/Ollama.app
else
    echo "$(date '+%Y-%m-%d %H:%M:%S'): Ollama OK" >> "$LOG"
fi
WATCHDOG
chmod +x ~/pi-ceo/ollama_watchdog.sh

# Write the launchd plist
cat > ~/Library/LaunchAgents/com.piceo.ollama-watchdog.plist << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.piceo.ollama-watchdog</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/phill-mac/pi-ceo/ollama_watchdog.sh</string>
    </array>
    <key>StartInterval</key>
    <integer>60</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/phill-mac/pi-ceo/logs/ollama_watchdog.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/phill-mac/pi-ceo/logs/ollama_watchdog.error.log</string>
</dict>
</plist>
PLIST

# Load (or reload) the agent
launchctl unload ~/Library/LaunchAgents/com.piceo.ollama-watchdog.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.piceo.ollama-watchdog.plist

echo "[RA-638] Watchdog installed and loaded."

# Run once immediately to confirm Ollama is up
echo "[RA-638] Running first watchdog check..."
bash ~/pi-ceo/ollama_watchdog.sh
echo "[RA-638] Check complete. Log:"
tail -3 ~/pi-ceo/logs/ollama_watchdog.log

echo ""
echo "=== Setup Complete ==="
echo "RA-637: Sleep=off, autorestart=on, display-sleep=15min"
echo "RA-638: Ollama watchdog checks every 60s — log at ~/pi-ceo/logs/ollama_watchdog.log"
