#!/usr/bin/env bash
# scripts/railway_check.sh — RA-3012 process hardening
#
# Wraps `railway variables` so secret values never hit stdout / transcripts.
# Replaces each KEY=VALUE with KEY=<set, len=N, fp=sha256[:8]>.
#
# Usage:
#   ./scripts/railway_check.sh                 # all keys masked
#   ./scripts/railway_check.sh --reveal KEY1   # opt-in to print KEY1 raw
#
# Background: RA-2989 traced today's 6-secret session leak to bare
# `railway variables` calls. Diagnostic is needed; secret values are not.

set -euo pipefail

REVEAL_KEYS=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --reveal) REVEAL_KEYS="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 2 ;;
  esac
done

# Use --kv (newline-separated KEY=VALUE) per Railway CLI docs
RAW="$(railway variables --kv 2>&1)" || { echo "$RAW"; exit 1; }

while IFS='=' read -r KEY VALUE; do
  [[ -z "$KEY" ]] && continue
  # Honour opt-in reveal list
  if [[ -n "$REVEAL_KEYS" ]] && [[ ",$REVEAL_KEYS," == *",$KEY,"* ]]; then
    echo "$KEY=$VALUE"
    continue
  fi
  LEN=${#VALUE}
  if [[ "$LEN" -eq 0 ]]; then
    echo "$KEY=<EMPTY>"
  else
    FP="$(printf '%s' "$VALUE" | shasum -a 256 | cut -c1-8)"
    echo "$KEY=<set, len=$LEN, fp=$FP>"
  fi
done <<< "$RAW"
