#!/usr/bin/env bash
# scripts/setup_honcho.sh — RA-1864 (Wave 4 B1) Honcho memory provider setup.
#
# Hermes-side configuration only — no Pi-CEO code changes. Run this AFTER
# you have either:
#   (a) signed up at https://app.honcho.dev and copied your API key, or
#   (b) started a self-hosted instance per
#       https://docs.honcho.dev/v3/guides/self-hosted
#
# Then:
#   bash scripts/setup_honcho.sh
#
# The script:
#   1. Verifies the Honcho plugin is installed in the local Hermes
#   2. Asks you for the API key (or self-hosted base URL)
#   3. Writes the key to ~/.hermes/.env (creating the file if missing)
#   4. Sets memory.provider=honcho in ~/.hermes/config.yaml via hermes config
#   5. Runs `hermes memory status` to verify the provider is healthy
#
# Idempotent — safe to re-run.

set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

if [ ! -d "$HERMES_HOME/hermes-agent/plugins/memory/honcho" ]; then
  echo "❌ Honcho plugin not found at $HERMES_HOME/hermes-agent/plugins/memory/honcho"
  echo "   Run 'hermes update' first to pull the latest plugins."
  exit 1
fi

echo "✅ Honcho plugin found at $HERMES_HOME/hermes-agent/plugins/memory/honcho"

# Prompt for API key
echo ""
echo "Paste your Honcho API key (or leave empty to set base URL for self-hosted):"
read -r HONCHO_API_KEY

if [ -n "$HONCHO_API_KEY" ]; then
  ENV_FILE="$HERMES_HOME/.env"
  touch "$ENV_FILE"
  # Drop any existing HONCHO_API_KEY line, then append the new one
  grep -v "^HONCHO_API_KEY=" "$ENV_FILE" > "${ENV_FILE}.tmp" || true
  echo "HONCHO_API_KEY=$HONCHO_API_KEY" >> "${ENV_FILE}.tmp"
  mv "${ENV_FILE}.tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "✅ HONCHO_API_KEY written to $ENV_FILE (mode 600)"
else
  echo "Paste your self-hosted Honcho base URL (e.g. http://localhost:8000):"
  read -r HONCHO_BASE_URL
  if [ -n "$HONCHO_BASE_URL" ]; then
    ENV_FILE="$HERMES_HOME/.env"
    touch "$ENV_FILE"
    grep -v "^HONCHO_BASE_URL=" "$ENV_FILE" > "${ENV_FILE}.tmp" || true
    echo "HONCHO_BASE_URL=$HONCHO_BASE_URL" >> "${ENV_FILE}.tmp"
    mv "${ENV_FILE}.tmp" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "✅ HONCHO_BASE_URL written to $ENV_FILE (mode 600)"
  else
    echo "❌ No key or URL provided — aborting."
    exit 1
  fi
fi

# Set provider
hermes config set memory.provider honcho
echo "✅ memory.provider set to honcho"

echo ""
echo "Verifying:"
hermes memory status

echo ""
echo "Setup complete. Pi-CEO MEMORY.md continues to function independently;"
echo "Honcho is now active for Hermes-runtime sessions only. Cross-substrate"
echo "bridging is a separate Wave 5 ticket."
