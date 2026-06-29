#!/usr/bin/env bash
# data_ingestion.sh — B.U.I.L.D. Inflow orchestration.
# Runs the data-capture pipelines as one routine (the AM routine in the rhythm).
# Improvement (improve_system.py) is a SEPARATE routine (the EOD one) so a
# failure is isolated to the stage that failed.
#
# Stages: 1) mine session lake → digests  2) refresh OKF indexes  3) wiki→Supabase
#
# Usage: bash scripts/data_ingestion.sh   (idempotent; safe to re-run)
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VAULT="$HOME/2nd Brain/2nd Brain"
OKF="$HOME/pi-seo-workspace/unite-group/apps/workspace/scripts/okf-index.py"
LOG="$HOME/.hermes/logs/data-ingestion.log"
mkdir -p "$(dirname "$LOG")"
ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
say() { echo "[$(ts)] $*" | tee -a "$LOG"; }

say "=== data-ingestion start ==="
rc=0

say "stage 1/3 — sync-claude-sessions (--since-last)"
python3 "$REPO/scripts/sync_claude_sessions.py" --since-last 2>&1 | tee -a "$LOG" || { say "STAGE 1 FAILED"; rc=1; }

say "stage 2/3 — OKF index refresh"
if [ -f "$OKF" ]; then
  python3 "$OKF" "$VAULT" 2>&1 | tee -a "$LOG" || { say "STAGE 2 FAILED"; rc=1; }
else
  say "STAGE 2 SKIP — okf-index.py not found at $OKF"
fi

say "stage 3/3 — wiki → Supabase (--since-last)"
if [ -f "$REPO/scripts/sync_wiki_to_supabase.py" ]; then
  python3 "$REPO/scripts/sync_wiki_to_supabase.py" --since-last 2>&1 | tee -a "$LOG" || { say "STAGE 3 FAILED"; rc=1; }
else
  say "STAGE 3 SKIP — sync_wiki_to_supabase.py not found"
fi

say "=== data-ingestion done (rc=$rc) ==="
exit $rc
