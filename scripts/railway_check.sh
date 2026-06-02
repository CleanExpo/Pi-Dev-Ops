#!/usr/bin/env bash
# Mask Railway variable values so diagnostics do not leak secrets to logs.

set -euo pipefail

mask_kv_stream() {
  while IFS='=' read -r KEY VALUE; do
    [[ -z "$KEY" ]] && continue
    LEN=${#VALUE}
    if [[ "$LEN" -eq 0 ]]; then
      echo "$KEY=<EMPTY>"
    else
      FP="$(printf '%s' "$VALUE" | shasum -a 256 | cut -c1-8)"
      echo "$KEY=<set, len=$LEN, fp=$FP>"
    fi
  done
}

REVEAL_KEYS=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --reveal)
      REVEAL_KEYS="$2"
      shift 2
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

RAW="$(railway variables --kv 2>&1)" || {
  printf '%s\n' "$RAW" | mask_kv_stream
  exit 1
}

while IFS='=' read -r KEY VALUE; do
  [[ -z "$KEY" ]] && continue
  if [[ -n "$REVEAL_KEYS" && ",$REVEAL_KEYS," == *",$KEY,"* ]]; then
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
