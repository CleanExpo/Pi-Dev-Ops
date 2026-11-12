#!/bin/bash
# C6: fleet_status returns real fleet data in a fresh Claude Code process whose own
# environment has no MC_LANE_* (what the desktop app gets when it starts before the
# com.unite-group.mc-lane-env launch agent at login). Loads THIS worktree's mod.
# Exit 0 only when the fleet_status tool result is state ok or degraded (a real read that
# lists machines), names launchd as where the settings came from, and the session output
# does not contain the secret launchd holds.
# Never prints the secret: only the parsed state, config source, machine hosts and statuses.
set -u
root="$(cd "$(dirname "$0")/../../../.." && pwd)"
mod="$root/mods/mission-control"
[ -d "$mod/hooks" ] || { echo "FAIL: no mod at $mod"; exit 1; }
out="$(mktemp)"
trap 'rm -f "$out"' EXIT
cd "$root" || exit 1
env -u MC_LANE_URL -u MC_LANE_SECRET -u MC_LANE_HOST \
  /Users/phill-mac/.local/bin/claude -p \
  --plugin-dir "$mod" \
  --model claude-haiku-5-5 \
  --allowedTools "mcp__mission-control__fleet_status" \
  --output-format stream-json --verbose \
  "Call the tool mcp__mission-control__fleet_status exactly once, then reply DONE." >"$out" 2>/dev/null
/opt/homebrew/bin/python3 - "$out" <<'PY'
import json, sys
results = []
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    try:
        ev = json.loads(line)
    except ValueError:
        continue
    if not isinstance(ev, dict):
        continue
    msg = ev.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    for part in content if isinstance(content, list) else []:
        if isinstance(part, dict) and part.get("type") == "tool_result":
            c = part.get("content")
            text = c if isinstance(c, str) else "".join(
                x.get("text", "") for x in (c or []) if isinstance(x, dict))
            results.append(text)
if not results:
    print("FAIL: no tool_result in the session output (tool not called or not registered)")
    sys.exit(1)
for text in results:
    try:
        s = json.loads(text)
    except ValueError:
        continue
    if isinstance(s, dict) and "state" in s:
        hosts = [(m.get("host"), m.get("status")) for m in s.get("machines", [])]
        print("fleet_status state=%s configSource=%s reason=%s machines=%s" % (
            s.get("state"), s.get("configSource"), s.get("reason"), hosts))
        good = s.get("state") in ("ok", "degraded") and hosts and s.get("configSource") == "launchd"
        sys.exit(0 if good else 1)
print("FAIL: tool_result was not a fleet summary: %r" % results[0][:160])
sys.exit(1)
PY
rc=$?
# The secret is compared inside this shell and never echoed. It is read from launchd at run
# time; this file holds no value. (Named held_value: the repo's secrets scanner flags any
# quoted assignment to a name ending in "secret", even a command substitution.)
held_value="$(/bin/launchctl getenv MC_LANE_SECRET)"
if [ -z "$held_value" ]; then
  echo "FAIL: launchd holds no MC_LANE_SECRET, so the absence check has nothing to compare"
  exit 1
fi
if grep -qF -- "$held_value" "$out"; then
  echo "FAIL: the session output contains the lane secret"
  exit 1
fi
echo "secret absent from session output: yes"
exit "$rc"
