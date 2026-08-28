#!/usr/bin/env bash
# Nexus Mesh — one-command fleet join. Run this on each machine (Mac mini, Windows
# via Git Bash/WSL, any Linux node) to enlist it in the fleet.
#
# It is idempotent: wires agent hooks, installs BOTH the heartbeat and the work
# runner, and keeps secrets in ~/.hermes/.env rather than daemon definitions.
set -euo pipefail

say() { printf '\033[1;36m▸ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$*"; }

MESH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$MESH_DIR/.." && pwd)"
HOST="$(hostname | cut -d. -f1)"
: "${PI_CEO_API_URL:=https://pi-dev-ops-production.up.railway.app}"
DAEMON_PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

say "Nexus Mesh bootstrap on $HOST"

# 1. Prereqs
command -v node >/dev/null || { warn "Node.js >=18 required — install it first"; exit 1; }
command -v python3 >/dev/null || { warn "python3 required"; exit 1; }
[ -n "${PI_CEO_API_KEY:-}" ] || warn "PI_CEO_API_KEY not set — daemons will use ~/.hermes/.env if already provisioned"

# 1b. Persist mesh authority to the protected shared env when supplied.
if [ -n "${PI_CEO_API_KEY:-}" ]; then
  ENVF="$HOME/.hermes/.env"; mkdir -p "$HOME/.hermes"; touch "$ENVF"; chmod 600 "$ENVF"
  grep -q '^PI_CEO_API_KEY=' "$ENVF" 2>/dev/null || printf 'PI_CEO_API_KEY=%s\n' "$PI_CEO_API_KEY" >> "$ENVF"
  grep -q '^PI_CEO_API_URL=' "$ENVF" 2>/dev/null || printf 'PI_CEO_API_URL=%s\n' "$PI_CEO_API_URL" >> "$ENVF"
  say "Mesh authority persisted to ~/.hermes/.env (600)"
fi

# 2. autogit — work bus
if ! command -v autogit >/dev/null; then
  say "Installing autogit"
  npm install -g @davidondrej/autogit
fi
say "Wiring agent hooks (Claude/Codex/Cursor/Pi)"
autogit setup || warn "autogit setup reported issues (non-fatal)"

# Harden generated hooks for the minimal PATH used by agent runtimes.
say "Hardening agent hooks (PATH-safe autogit)"
python3 - <<'PYH' || warn "hook hardening skipped (non-fatal)"
import json, os
BINS = os.path.expanduser("~/.local/bin") + ":/opt/homebrew/bin:/usr/local/bin"
def harden(path):
    if not os.path.exists(path):
        return
    try:
        d = json.load(open(path))
    except Exception:
        return
    changed = False
    hooks = d.get("hooks", {})
    if not isinstance(hooks, dict):
        return
    for groups in hooks.values():
        if not isinstance(groups, list):
            continue
        for grp in groups:
            for h in grp.get("hooks", []) if isinstance(grp, dict) else []:
                c = h.get("command", "")
                prefix = (f'export PATH="{BINS}:$PATH"; cd "${{CLAUDE_PROJECT_DIR:-.}}" '
                          f'&& command -v autogit >/dev/null 2>&1 && ')
                if "autogit ship" in c and "feat/*" not in c:
                    run = ('{ b="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"; '
                           'case "$b" in feat/*|feature/*|fix/*|main|master|HEAD) ;; '
                           '*) autogit ship ;; esac; }')
                    h["command"] = prefix + run + " || true"
                    changed = True
                elif "autogit busy" in c and "command -v autogit" not in c:
                    h["command"] = prefix + "autogit busy || true"
                    changed = True
    if changed:
        json.dump(d, open(path, "w"), indent=2)
        print(f"  hardened {path}")
harden(os.path.expanduser("~/.claude/settings.json"))
PYH

# 3. Hermes adapter (only if Hermes is present on this node)
if [ -f "$HOME/.hermes/config.yaml" ]; then
  say "Hermes detected — mesh ship hook available"
  chmod +x "$MESH_DIR/hooks/hermes_ship.sh" 2>/dev/null || true
fi

# 4. Heartbeat — visibility. A machine is not considered operational merely
# because this daemon is alive; the runner below is installed as a peer service.
say "Publishing first heartbeat"
python3 "$MESH_DIR/heartbeat.py" || warn "heartbeat publish failed (check PI_CEO_API_KEY / endpoint deploy)"

OS="$(uname -s)"
case "$OS" in
  Darwin)
    mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

    HEARTBEAT_PLIST="$HOME/Library/LaunchAgents/com.unite-group.mesh-heartbeat.plist"
    say "Installing launchd heartbeat daemon → $HEARTBEAT_PLIST"
    cat > "$HEARTBEAT_PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.unite-group.mesh-heartbeat</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/env</string><string>python3</string>
    <string>$MESH_DIR/heartbeat.py</string><string>--loop</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO_DIR</string>
  <key>EnvironmentVariables</key><dict>
    <key>PI_CEO_API_URL</key><string>$PI_CEO_API_URL</string>
    <key>PATH</key><string>$DAEMON_PATH</string>
  </dict>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/nexus-mesh-heartbeat.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/nexus-mesh-heartbeat.err.log</string>
</dict></plist>
PL
    launchctl unload "$HEARTBEAT_PLIST" 2>/dev/null || true
    launchctl load "$HEARTBEAT_PLIST" && say "launchd heartbeat loaded"

    RUNNER_PLIST="$HOME/Library/LaunchAgents/com.unite-group.mesh-runner.plist"
    say "Installing launchd work runner → $RUNNER_PLIST"
    cat > "$RUNNER_PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.unite-group.mesh-runner</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/env</string><string>python3</string>
    <string>$MESH_DIR/runner.py</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO_DIR</string>
  <key>EnvironmentVariables</key><dict>
    <key>PI_CEO_API_URL</key><string>$PI_CEO_API_URL</string>
    <key>MESH_REPO_DIR</key><string>$REPO_DIR</string>
    <key>PATH</key><string>$DAEMON_PATH</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>ThrottleInterval</key><integer>15</integer>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/nexus-mesh-runner.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/nexus-mesh-runner.err.log</string>
</dict></plist>
PL
    # The runner reads PI_CEO_API_KEY from ~/.hermes/.env at runtime. It is not
    # embedded in this plist. Successful exit (hard stop or claim cap) stays
    # stopped; crashes restart after the throttle interval.
    launchctl unload "$RUNNER_PLIST" 2>/dev/null || true
    launchctl load "$RUNNER_PLIST" && say "launchd work runner loaded"
    ;;
  Linux)
    say "Linux — supervise both mesh daemons (systemd recommended):"
    echo "  python3 $MESH_DIR/heartbeat.py --loop"
    echo "  python3 $MESH_DIR/runner.py"
    ;;
  *)
    warn "Windows: register Scheduled Tasks at logon for BOTH heartbeat.py --loop and runner.py"
    ;;
esac

say "Done. $HOST is enlisted with visibility + work execution."
