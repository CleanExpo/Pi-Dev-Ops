#!/bin/bash
# Install the liveness prover as a LaunchAgent, and PROVE it fires.
#
# WHY AN INSTALLER EXISTS AT ALL. ~/Library/LaunchAgents and ~/.local/bin are not
# version-controlled, so anything wired there exists on exactly one machine. That
# is the same class of defect the prover was built to catch — something that looks
# configured but is absent where it matters. The repo is the source of truth; this
# script is the only supported way to wire it to a machine.
#
# It refuses to finish quietly. Installing and then not verifying is how
# in.unite-group.hermes-heartbeat ended up with a plist on disk, a tombstone
# script, and no loaded agent — three layers of looking-installed over nothing.
#
# Usage:  bash scripts/install-liveness-prover.sh          # install + verify
#         bash scripts/install-liveness-prover.sh --remove # uninstall
set -uo pipefail

LABEL="com.unite.liveness-prover"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/.claude/liveness-prover.log"
UID_N="$(id -u)"

if [ "${1:-}" = "--remove" ]; then
  launchctl bootout "gui/$UID_N/$LABEL" 2>/dev/null
  rm -f "$PLIST"
  echo "removed $LABEL"
  exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.claude"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$ROOT/scripts/liveness-prover-run.sh</string></array>
  <key>StartInterval</key><integer>3600</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$HOME/.claude/liveness-prover.out</string>
  <key>StandardErrorPath</key><string>$HOME/.claude/liveness-prover.err</string>
</dict>
</plist>
PLIST_EOF

plutil -lint "$PLIST" >/dev/null || { echo "FAIL: plist is malformed"; exit 1; }
chmod +x "$ROOT/scripts/liveness-prover-run.sh"

# launchd does not release a label synchronously, so bootout-then-bootstrap races.
# Poll for the condition instead of guessing a delay — a fixed sleep here failed
# twice on 2026-08-19 and was caught by this script's own verification, which is
# exactly what the verification is for.
before=$(wc -c < "$LOG" 2>/dev/null || echo 0)

# launchd's bootout is ASYNCHRONOUS. A bootout-then-bootstrap pair races: the
# service sits in a transitional state where `launchctl list` does not show it yet
# `bootstrap` already reports "5: Input/output error" (already bootstrapped), so a
# retry loop fights itself and never converges. Observed twice on 2026-08-19.
#
# The idiom that does not race: bootstrap only when genuinely absent, otherwise
# kickstart -k to restart in place. kickstart also re-reads the plist, so an edited
# plist still takes effect.
# Query the service directly. `launchctl list | grep` is unreliable here: while a
# RunAtLoad job is executing, the listing lags and the grep reports absent for ~10s
# even though bootstrap already succeeded and reports "5: Input/output error"
# (already bootstrapped) on retry. Chasing that contradiction cost three iterations
# on 2026-08-19. `launchctl print` asks about one service and answers immediately.
is_loaded() { launchctl print "gui/$UID_N/$LABEL" >/dev/null 2>&1; }

if is_loaded; then
  launchctl kickstart -k "gui/$UID_N/$LABEL" 2>/dev/null
else
  launchctl bootstrap "gui/$UID_N" "$PLIST" 2>&1 | tail -1
fi

loaded=0
for _ in $(seq 1 10); do
  if is_loaded; then loaded=1; break; fi
  sleep 1
done

if [ "$loaded" -ne 1 ]; then
  echo "FAIL: $LABEL is not registered with launchd"
  launchctl bootstrap "gui/$UID_N" "$PLIST" 2>&1 | tail -2
  exit 1
fi

# Wait for the RunAtLoad execution to actually append, rather than assuming it has.
after=$before
for _ in $(seq 1 20); do
  after=$(wc -c < "$LOG" 2>/dev/null || echo 0)
  [ "$after" -gt "$before" ] && break
  sleep 1
done
if [ "$after" -le "$before" ]; then
  echo "FAIL: agent is loaded but wrote nothing to $LOG — this is the hermes-heartbeat failure mode"
  exit 1
fi

# The prover having RUN is not the same as the prover WORKING. If the wrapper could
# not locate or execute the script it still writes a well-formed verdict, whose only
# probe is prover_itself: DEAD — and byte growth alone would read that as success.
#
# Note what is deliberately NOT required here: an overall ALIVE verdict. Review
# suggested it; it is wrong. A monitor is installed precisely when the estate is
# unhealthy, so demanding ALIVE would make installation impossible exactly when it
# matters most. The installer's job is to prove the MONITOR works, not that the
# estate is well. Those are different claims and conflating them is how you end up
# tuning a gate until it passes.
# Three states, distinguished explicitly, because an earlier version of this check
# FAILED OPEN: it ran python inside `if`, so an exception (malformed or absent JSON)
# produced a non-zero exit, the `if` went false, and the installer reported success
# over a prover that had emitted nothing usable. "Could not parse" was read as
# "fine" — the same defect this whole change exists to remove, written into its own
# verifier. Caught in review 2026-08-19.
#
#   0 = a real verdict with real probes      -> install is good
#   1 = only prover_itself                   -> agent runs, prover cannot execute
#   2 = no parseable verdict at all          -> agent produced nothing usable
# Anything else is also treated as failure.
set +e
python3 - "$LOG" <<'PY'
import json, sys, pathlib
try:
    t = pathlib.Path(sys.argv[1]).read_text()
    i = t.rfind('{\n  "checked_at"')
    if i < 0:
        sys.exit(2)
    d = json.loads(t[i:])
    names = [p["name"] for p in d["probes"]]
except Exception:
    sys.exit(2)
sys.exit(1 if names == ["prover_itself"] else 0)
PY
verdict_rc=$?
# NB: do not `set -e` here. The script header is `set -uo pipefail` deliberately —
# turning errexit on partway through would change behaviour for everything below.

case "$verdict_rc" in
  0) : ;;
  1) echo "FAIL: the agent ran but the prover could not execute — verdict contains only prover_itself"
     tail -6 "$LOG"; exit 1 ;;
  2) echo "FAIL: the agent produced no parseable verdict in $LOG"
     tail -6 "$LOG"; exit 1 ;;
  *) echo "FAIL: verdict check itself errored (rc=$verdict_rc) — refusing to claim success"
     exit 1 ;;
esac

echo
echo "INSTALLED and VERIFIED:"
echo "  loaded : $(launchctl list | grep "$LABEL")"
echo "  wrote  : $((after - before)) bytes to $LOG"
echo
echo "Latest verdict:"
python3 - "$LOG" <<'PY'
import json, sys, pathlib
t = pathlib.Path(sys.argv[1]).read_text()
i = t.rfind('{\n  "checked_at"')
d = json.loads(t[i:])
print(f"  {d['verdict']} — {d['dead_count']} of {len(d['probes'])} probes cannot prove liveness")
for p in d["probes"]:
    print(f"    {p['state']:<5} {p['name']}")
PY
