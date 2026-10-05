#!/bin/zsh
# Install the estate-sync LaunchAgent (macOS): runs estate-sync.sh every 15 minutes.
set -eu
PLIST="$HOME/Library/LaunchAgents/com.unite.estate-sync.plist"
/bin/cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.unite.estate-sync</string>
  <key>ProgramArguments</key><array>
    <string>/bin/zsh</string>
    <string>$HOME/.claude/skills/estate-sync/scripts/estate-sync.sh</string>
  </array>
  <key>StartInterval</key><integer>900</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardErrorPath</key><string>$HOME/.claude/logs/estate-sync.launchd.log</string>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
  </dict>
</dict></plist>
EOF
launchctl bootout "gui/$(id -u)/com.unite.estate-sync" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed + started com.unite.estate-sync (every 15 min). Log: ~/.claude/logs/estate-sync.log"
