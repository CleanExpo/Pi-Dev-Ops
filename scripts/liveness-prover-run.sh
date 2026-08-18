#!/bin/bash
# Wrapper for the liveness prover. Exists because the first version of this agent
# failed the exact way the prover was built to catch: it was loaded, exited 0, and
# appended "No such file or directory" to a log nobody reads. A monitor that fails
# silently is the defect, not a bug in the defect.
#
# Two rules here:
#   1. Find the script rather than assume one path. The repo has many worktrees and
#      the script may not be on main yet.
#   2. If it cannot run, say so LOUDLY in the same JSON shape the prover emits, so a
#      reader of the log cannot mistake "never ran" for "nothing to report".
set -uo pipefail

LOG="$HOME/.claude/liveness-prover.log"
STAMP="$HOME/.claude/liveness-prover-last-run.json"
mkdir -p "$HOME/.claude"

emit_dead() {
  printf '{\n  "checked_at": "%s",\n  "verdict": "DEAD",\n  "dead_count": 1,\n  "probes": [{"name":"prover_itself","state":"DEAD","evidence":%s,"remedy":"the prover could not run — fix this before trusting any other probe"}]\n}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(printf '%s' "$1" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')" >> "$LOG"
}

# Candidate checkouts, most authoritative first.
SCRIPT=""
for root in "$HOME/Pi-Dev-Ops" "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" /tmp/pi-overnight; do
  if [ -f "$root/scripts/liveness_prover.py" ]; then SCRIPT="$root/scripts/liveness_prover.py"; ROOT="$root"; break; fi
done

if [ -z "$SCRIPT" ]; then
  emit_dead "liveness_prover.py not found in any known checkout — it is probably still on an unmerged branch"
  exit 1
fi

PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
[ -x "$PY" ] || { emit_dead "no usable python interpreter"; exit 1; }

OUT="$("$PY" "$SCRIPT" --json 2>&1)"
RC=$?

# A crash must not look like a quiet pass.
if [ $RC -gt 1 ] || ! printf '%s' "$OUT" | head -c1 | grep -q '{'; then
  emit_dead "prover exited $RC without valid JSON: ${OUT:0:300}"
  exit 1
fi

printf '%s\n' "$OUT" >> "$LOG"
exit $RC
