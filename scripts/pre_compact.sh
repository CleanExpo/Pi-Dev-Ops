#!/usr/bin/env bash
# pre_compact.sh — PreCompact hook for Pi-CEO build sessions.
#
# Fires before Claude Code compacts the context window.
# Appends a snapshot entry to .harness/compaction_log.jsonl so long-running
# autonomous sessions leave a breadcrumb trail across compactions.
#
# Environment variables provided by Claude Code:
#   CLAUDE_SESSION_ID    — current session identifier
#   CLAUDE_COMPACT_REASON — why compaction was triggered (if set)

set -euo pipefail

LOG_DIR="/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/swarm"
LOG_FILE="$LOG_DIR/compaction_log.jsonl"

mkdir -p "$LOG_DIR"

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
SESSION_ID="${CLAUDE_SESSION_ID:-unknown}"
REASON="${CLAUDE_COMPACT_REASON:-context_limit}"

printf '{"ts":"%s","event":"pre_compact","session_id":"%s","reason":"%s"}\n' \
    "$TIMESTAMP" "$SESSION_ID" "$REASON" >> "$LOG_FILE"

echo "[pre_compact] Snapshot written to $LOG_FILE (session=$SESSION_ID)"
