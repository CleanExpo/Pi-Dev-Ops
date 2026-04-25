#!/usr/bin/env bash
#
# RA-1518 gap #2 — Gate-to-green runner.
#
# Usage:
#   autonomous_gate.sh <repo> <pr_number> [max_wait_minutes=30]
# Example:
#   autonomous_gate.sh CleanExpo/RestoreAssist 619
#
# Polls a PR's check statuses until terminal (all green or any required red).
# Prints a concise summary. Exits 0 on all-green, 1 on red (with failing check
# names), 2 on timeout.
#
# Designed to be invoked after `git push` in an autonomous session. The caller
# (Claude) reads the output; on red, reads logs via `gh run view <id>
# --log-failed` and iterates on the same branch.

set -euo pipefail

REPO="${1:-}"
PR="${2:-}"
MAX_WAIT_MIN="${3:-30}"

if [[ -z "$REPO" || -z "$PR" ]]; then
  echo "Usage: $0 <owner/repo> <pr_number> [max_wait_minutes=30]" >&2
  exit 64
fi

deadline=$(( $(date +%s) + MAX_WAIT_MIN * 60 ))

# Python analyser lives in its own file (no shell-escape pain) — write once.
analyser=$(mktemp -t autogate.XXXXXX.py)
trap 'rm -f "$analyser"' EXIT
cat >"$analyser" <<'PYEOF'
import json, sys
d = json.load(sys.stdin)
checks = d.get("statusCheckRollup") or []
if not checks:
    print("NO_CHECKS")
    sys.exit()
success, failure, pending, skipped = [], [], [], []
for c in checks:
    name = c.get("name") or c.get("context") or "?"
    state = (c.get("state") or c.get("conclusion") or c.get("status") or "").upper()
    if state in ("SUCCESS", "COMPLETED"):
        success.append(name)
    elif state in ("FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"):
        failure.append(name)
    elif state in ("PENDING", "IN_PROGRESS", "QUEUED", "WAITING"):
        pending.append(name)
    elif state in ("SKIPPED", "NEUTRAL"):
        skipped.append(name)
    else:
        pending.append(f"{name}:{state}")
print(f"s={len(success)} f={len(failure)} p={len(pending)} k={len(skipped)}")
if failure:
    print("RED: " + ",".join(failure))
if pending:
    print("PENDING: " + ",".join(pending))
PYEOF

while :; do
  json=$(gh pr view "$PR" --repo "$REPO" --json statusCheckRollup,mergeable 2>/dev/null || echo '{}')
  summary=$(echo "$json" | python3 "$analyser")
  ts=$(date +%H:%M:%S)
  echo "[$ts] $PR $summary"

  if echo "$summary" | grep -q "^RED:"; then
    echo "[$ts] Gate RED. Inspect: gh pr checks $PR --repo $REPO"
    exit 1
  fi
  if ! echo "$summary" | grep -q "^PENDING:" && ! echo "$summary" | grep -q "NO_CHECKS"; then
    echo "[$ts] Gate GREEN."
    exit 0
  fi

  if (( $(date +%s) >= deadline )); then
    echo "[$ts] Gate TIMEOUT after ${MAX_WAIT_MIN}m" >&2
    exit 2
  fi

  sleep 30
done
