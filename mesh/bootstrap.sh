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

# Harden generated hooks for the minimal PATH used by agent runtimes, and route
# every ship through mesh/hooks/mesh_ship.sh rather than calling `autogit ship`
# directly. Two independent defects produced the same symptom — zero
# refs/heads/mesh/* on origin — and the wrapper closes both:
#   RA-6505: autogit missing from the hook's minimal PATH, so nothing ran.
#   RA-7376: autogit ships only UNCOMMITTED work, so an agent that committed its
#            own turn (as every gate in this estate requires) shipped nothing.
# The ship call is therefore deliberately NOT gated on `command -v autogit`: the
# wrapper must still push committed work on a node where autogit is unavailable.
say "Hardening agent hooks (mesh ship wrapper, PATH-safe)"
MESH_DIR="$MESH_DIR" python3 - <<'PYH' || warn "hook hardening skipped (non-fatal)"
import json, os
BINS = os.path.expanduser("~/.local/bin") + ":/opt/homebrew/bin:/usr/local/bin"
MESH_DIR = os.environ.get("MESH_DIR", "")
SHIP = os.path.join(MESH_DIR, "hooks", "mesh_ship.sh")
def harden(path):
    """Rewrite an agent's hook commands in place; idempotent across re-runs."""
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
                prefix = f'export PATH="{BINS}:$PATH"; cd "${{CLAUDE_PROJECT_DIR:-.}}" 2>/dev/null; '
                # Re-point both a legacy `autogit ship` hook and an earlier
                # wrapper install (possibly at a stale path) at the current one.
                if "autogit ship" in c or "mesh_ship.sh" in c:
                    new = prefix + f'bash "{SHIP}" || true'
                    if c != new:
                        h["command"] = new
                        changed = True
                elif "autogit busy" in c and "command -v autogit" not in c:
                    h["command"] = (f'export PATH="{BINS}:$PATH"; cd "${{CLAUDE_PROJECT_DIR:-.}}" '
                                    f'&& command -v autogit >/dev/null 2>&1 && autogit busy || true')
                    changed = True
    if changed:
        json.dump(d, open(path, "w"), indent=2)
        print(f"  hardened {path}")
if not os.path.isfile(SHIP):
    raise SystemExit(f"mesh_ship.sh not found at {SHIP}")
harden(os.path.expanduser("~/.claude/settings.json"))
PYH
chmod +x "$MESH_DIR/hooks/mesh_ship.sh" 2>/dev/null || true

# 3. Hermes adapter (only if Hermes is present on this node)
if [ -f "$HOME/.hermes/config.yaml" ]; then
  say "Hermes detected — mesh ship hook available"
  chmod +x "$MESH_DIR/hooks/hermes_ship.sh" 2>/dev/null || true
fi

# 4. Heartbeat — visibility. A machine is not considered operational merely
# because this daemon is alive; the runner below is installed as a peer service.
# HEARTBEAT_OK and SUPERVISED are the two halves of "enlisted". The verdict at
# the bottom is DERIVED from them rather than asserted alongside them: this
# script used to print "Done. $HOST is enlisted with visibility + work
# execution." unconditionally, so a Windows node that installed no daemon and
# whose heartbeat returned {"published": false} still reported success and
# exited 0. A machine that failed to enlist must not look like one that did.
HEARTBEAT_OK=0
SUPERVISED=0

say "Publishing first heartbeat"
if python3 "$MESH_DIR/heartbeat.py"; then
  HEARTBEAT_OK=1
else
  warn "heartbeat publish failed (check PI_CEO_API_KEY / endpoint deploy)"
fi

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
    HB_SVC=0
    if launchctl load "$HEARTBEAT_PLIST"; then
      say "launchd heartbeat loaded"; HB_SVC=1
    else
      warn "launchd could not load the heartbeat daemon"
    fi

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
    RUN_SVC=0
    if launchctl load "$RUNNER_PLIST"; then
      say "launchd work runner loaded"; RUN_SVC=1
    else
      warn "launchd could not load the work runner"
    fi

    # Both, or the node is not supervised. Visibility without execution is a
    # machine dispatch can see and cannot use.
    if [ "$HB_SVC" = 1 ] && [ "$RUN_SVC" = 1 ]; then SUPERVISED=1; fi
    ;;
  Linux)
    warn "Linux — this script does NOT install supervision. Both daemons must be"
    warn "supervised (systemd user units recommended) or this node goes stale in 60s:"
    echo "  python3 $MESH_DIR/heartbeat.py --loop"
    echo "  python3 $MESH_DIR/runner.py"
    ;;
  *)
    warn "Windows ($OS) — this script does NOT install supervision. Register both"
    warn "Scheduled Tasks at logon, or this node goes stale 60s from now:"
    echo "  schtasks /Create /F /SC ONLOGON /TN NexusMeshHeartbeat \\"
    echo "    /TR \"python \\\"$MESH_DIR/heartbeat.py\\\" --loop\""
    echo "  schtasks /Create /F /SC ONLOGON /TN NexusMeshRunner \\"
    echo "    /TR \"python \\\"$MESH_DIR/runner.py\\\"\""
    ;;
esac

# The verdict. Both halves must hold; each failure names the work it needs,
# because a denial an operator cannot act on is barely better than a false
# success. Exit is non-zero so automation cannot read this as done either.
if [ "$HEARTBEAT_OK" = 1 ] && [ "$SUPERVISED" = 1 ]; then
  say "Done. $HOST is enlisted with visibility + work execution."
  exit 0
fi

warn "$HOST is NOT enlisted."
[ "$HEARTBEAT_OK" = 1 ] || warn "  - the first heartbeat did not publish; the node is invisible to dispatch"
[ "$SUPERVISED" = 1 ] || warn "  - no supervision installed; the node goes stale ~60s from now"
warn "Confirm from the fleet, not from this output:"
echo "  curl -s \"\$PI_CEO_API_URL/api/mesh/fleet\" -H \"X-Pi-CEO-Secret: \$PI_CEO_API_KEY\""
exit 1
