#!/usr/bin/env bash
# Nexus Mesh — one-command fleet join. Run this on each machine (Mac mini, Windows
# via Git Bash/WSL, any Linux node) to enlist it in the fleet.
#
#   curl -fsSL <raw-url>/mesh/bootstrap.sh | bash      # or run from a Pi-CEO checkout
#
# It is idempotent and read-mostly: installs autogit, wires the agent + Hermes
# hooks, drops the heartbeat daemon, and registers the machine. No secrets are
# written by this script — set PI_CEO_API_KEY in your shell first.
#
# Spec: docs/superpowers/specs/2026-06-11-nexus-mesh-design.md
set -euo pipefail

say() { printf '\033[1;36m▸ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$*"; }

MESH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="$(hostname | cut -d. -f1)"
: "${PI_CEO_API_URL:=https://pi-dev-ops-production.up.railway.app}"

say "Nexus Mesh bootstrap on $HOST"

# 1. Prereqs
command -v node >/dev/null || { warn "Node.js >=18 required — install it first"; exit 1; }
command -v python3 >/dev/null || { warn "python3 required"; exit 1; }
[ -n "${PI_CEO_API_KEY:-}" ] || warn "PI_CEO_API_KEY not set — heartbeat will be rejected until you export it"

# 1b. Persist the secret to ~/.hermes/.env (mode 600) so the daemon reads it at
#     runtime — it is never embedded in the launchd plist / Scheduled Task.
if [ -n "${PI_CEO_API_KEY:-}" ]; then
  ENVF="$HOME/.hermes/.env"; mkdir -p "$HOME/.hermes"; touch "$ENVF"; chmod 600 "$ENVF"
  grep -q '^PI_CEO_API_KEY=' "$ENVF" 2>/dev/null || printf 'PI_CEO_API_KEY=%s\n' "$PI_CEO_API_KEY" >> "$ENVF"
  grep -q '^PI_CEO_API_URL=' "$ENVF" 2>/dev/null || printf 'PI_CEO_API_URL=%s\n' "$PI_CEO_API_URL" >> "$ENVF"
  say "Secret persisted to ~/.hermes/.env (600); not embedded in any daemon config"
fi

# 2. autogit — work bus
if ! command -v autogit >/dev/null; then
  say "Installing autogit"
  npm install -g @davidondrej/autogit
fi
say "Wiring agent hooks (Claude/Codex/Cursor/Pi)"
autogit setup || warn "autogit setup reported issues (non-fatal)"

# 3. Hermes adapter (only if Hermes is present on this node)
if [ -f "$HOME/.hermes/config.yaml" ]; then
  say "Hermes detected — wire mesh/hooks/hermes_ship.sh as an on_session_end hook"
  warn "Add to ~/.hermes/config.yaml (then: hermes hooks list to approve):"
  echo "    hooks:"
  echo "      on_session_end:"
  echo "        - command: \"$MESH_DIR/hooks/hermes_ship.sh\""
  chmod +x "$MESH_DIR/hooks/hermes_ship.sh" 2>/dev/null || true
fi

# 4. Heartbeat — nervous system. Register once, then schedule the loop.
say "Publishing first heartbeat"
python3 "$MESH_DIR/heartbeat.py" || warn "heartbeat publish failed (check PI_CEO_API_KEY / endpoint deploy)"

OS="$(uname -s)"
case "$OS" in
  Darwin)
    PLIST="$HOME/Library/LaunchAgents/com.unite-group.mesh-heartbeat.plist"
    say "Installing launchd heartbeat daemon → $PLIST"
    cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.unite-group.mesh-heartbeat</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/env</string><string>python3</string>
    <string>$MESH_DIR/heartbeat.py</string><string>--loop</string>
  </array>
  <key>EnvironmentVariables</key><dict>
    <key>PI_CEO_API_URL</key><string>$PI_CEO_API_URL</string>
  </dict>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
</dict></plist>
PL
    # The secret is NOT embedded in the plist — heartbeat.py reads PI_CEO_API_KEY
    # from ~/.hermes/.env at runtime. Make sure it's there and protected.
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load "$PLIST" && say "launchd heartbeat loaded"
    ;;
  Linux)
    say "Linux — add to crontab:  */1 * * * * PI_CEO_API_KEY=... python3 $MESH_DIR/heartbeat.py"
    ;;
  *)
    warn "Windows: register a Scheduled Task running 'python $MESH_DIR\\heartbeat.py --loop' at logon"
    ;;
esac

say "Done. $HOST is enlisted. Watch it appear in Mission Control."
