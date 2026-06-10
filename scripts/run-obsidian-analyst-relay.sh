#!/usr/bin/env bash
# Run the narrow Obsidian analyst relay without storing the token in launchd.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

TOKEN="${OBSIDIAN_TOKEN:-}"
if [[ -z "${TOKEN}" ]] && command -v security >/dev/null 2>&1; then
  TOKEN="$(security find-generic-password -a "${USER}" -s pi-ceo-obsidian-token -w 2>/dev/null || true)"
fi

if [[ -z "${TOKEN}" ]]; then
  echo "OBSIDIAN_TOKEN missing; set env or store Keychain item pi-ceo-obsidian-token" >&2
  exit 1
fi

export OBSIDIAN_TOKEN="${TOKEN}"
exec python3 "${REPO_ROOT}/scripts/obsidian_analyst_relay.py" \
  --host "${OBSIDIAN_RELAY_HOST:-127.0.0.1}" \
  --port "${OBSIDIAN_RELAY_PORT:-27125}" \
  --upstream "${OBSIDIAN_RELAY_UPSTREAM:-http://127.0.0.1:27123}"
