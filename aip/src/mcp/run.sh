#!/usr/bin/env bash
# Run wrapper for the AIP MCP server.
#
# Resolves the Supabase service-role key from 1Password at every MCP launch,
# then execs the TypeScript MCP server over stdio. The key never lives in
# settings.json, .env files, or shell history — it stays in 1Password.
#
# Wired into Claude Code via ~/.claude.json under mcpServers["aip-readonly"].
# Update the path there if this script moves.

set -euo pipefail

# Non-secret env
export SUPABASE_PICEO_URL="https://zbryrmxmgfmslqzizsto.supabase.co"

# Secret: read from 1Password via op CLI.
# stderr is fine for diagnostics (MCP transport is stdout); stdout MUST NOT
# leak the key — that would mean writing it into the MCP framing.
if ! command -v op >/dev/null 2>&1; then
  echo "AIP MCP wrapper: 'op' CLI not found on PATH" >&2
  exit 1
fi

SUPABASE_PICEO_SERVICE_KEY="$(op read "op://Unite-Group-Infrastructure/SUPABASE_SERVICE_ROLE_KEY/credential" 2>/dev/null || true)"
if [ -z "${SUPABASE_PICEO_SERVICE_KEY:-}" ]; then
  echo "AIP MCP wrapper: failed to read Supabase service key from 1Password" >&2
  echo "  Check: op item get 'SUPABASE_SERVICE_ROLE_KEY' --vault Unite-Group-Infrastructure" >&2
  echo "  Or unlock 1P CLI: eval \"\$(op signin)\"" >&2
  exit 1
fi
export SUPABASE_PICEO_SERVICE_KEY

# Exec the server. cd into aip/ so node_modules resolution works.
cd /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/aip
exec npx tsx /Users/phill-mac/Pi-CEO/Pi-Dev-Ops/aip/src/mcp/server.ts
