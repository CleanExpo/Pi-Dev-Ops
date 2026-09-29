#!/usr/bin/env bash
# Phase 1 grounding, as a control with an exit code rather than a rule to remember.
#
#   ground.sh <project-root>
#
# Exit 0 = grounded. Exit 2 = the waterline gate could not be read; the caller MUST stop.
# Prints one GROUND line, then the recall section on stdout.
set -uo pipefail

ROOT="${1:-$PWD}"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATE_HEADING='The Waterline — autonomy gate'

PROJECT="$(basename "$ROOT" | tr '[:upper:]' '[:lower:]')"
PACK="$SKILL_DIR/references/$PROJECT.md"
[ -r "$PACK" ] || PACK=""

# Resolve CONSTITUTION.md through the symlink the repo uses.
CONST=""
for c in "$ROOT/CONSTITUTION.md" "$ROOT/docs/governance/CONSTITUTION.md"; do
  [ -r "$c" ] && { CONST="$c"; break; }
done

if [ -z "$CONST" ] || ! grep -q "$GATE_HEADING" "$CONST"; then
  echo "GROUND project=$PROJECT pack=${PACK:-none} gate=MISSING"
  echo "STOP: no '$GATE_HEADING' section in ${CONST:-<no CONSTITUTION.md found>}." >&2
  echo "A gate quoted from memory is not a gate. Locate where it moved, then re-run." >&2
  exit 2
fi

echo "GROUND project=$PROJECT pack=${PACK:-none} gate=$CONST"
echo "--- waterline gate (read live, never cached) ---"
awk -v h="$GATE_HEADING" 'index($0,h){f=1} f&&/^### /&&!index($0,h){exit} f' "$CONST"

# The vault checkout is named differently across the estate (~/2nd-brain here, ~/2nd Brain
# there), so resolve it by glob. A hardcoded spelling disables recall on every machine that
# uses the other one, silently — which is the failure this whole script is shaped to avoid.
BRAIN="$(ls "$HOME"/2nd*/"2nd Brain"/_system/brain.js 2>/dev/null | head -1)"
if [ -n "${2:-}" ]; then
  echo "--- recall ---"
  # Phase 3 is gated on recall.go_external, so recall must ALWAYS state a result. Printing
  # nothing when the vault is absent left the caller with no gate at all and read as if
  # grounding had succeeded.
  if [ -n "$BRAIN" ] && [ -r "$BRAIN" ]; then
    node "$BRAIN" find "$2" 2>/dev/null || echo "recall{ go_external: true, reason: miss }"
  else
    echo "recall{ go_external: true, reason: unavailable }"
  fi
fi
