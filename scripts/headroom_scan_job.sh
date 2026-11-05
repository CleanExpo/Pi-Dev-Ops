#!/bin/bash
# Record HEADROOM events for one finished night-lane job (RA-8188, AR-02).
#
# Usage: headroom_scan_job.sh <job-dir> <provider> <exit-code> [output-file]
#   provider: claude | codex | cursor     output-file default: <job-dir>/claude.out
#
# Call it after the agent exits, e.g. in run.sh right after `wait "$CPID"`:
#   RC=$?; bash "$HOME/Pi-Dev-Ops/scripts/headroom_scan_job.sh" "$J" claude "$RC" "$J/claude.out"
#
# It only reads the job's output and appends to the HEADROOM log. It always exits 0, so it
# can never change what a job does; a failed scan or write is written to <job-dir>/job.log.
# It never signs in or out and never reads or changes credentials.
J="$1"; PROVIDER="$2"; RC="$3"; OUT="${4:-$1/claude.out}"
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${HEADROOM_PYTHON:-python3}"
ARGS=(scan "--provider=$PROVIDER" "--job=$(basename -- "$J")")
if [[ "$RC" =~ ^-?[0-9]+$ ]]; then ARGS+=("--exit-code=$RC"); fi
ARGS+=(-- "$OUT")
STAMP="$(TZ=Australia/Brisbane date '+%F %T AEST')"
if MSG="$("$PY" "$HERE/headroom_events.py" "${ARGS[@]}" 2>&1)"; then
  echo "$STAMP $MSG" >> "$J/job.log" 2>/dev/null
else
  echo "$STAMP headroom: FAILED (exit $?): $MSG" >> "$J/job.log" 2>/dev/null
fi
exit 0
