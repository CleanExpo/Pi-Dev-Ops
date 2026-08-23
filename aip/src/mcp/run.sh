#!/usr/bin/env bash
# Run wrapper for the AIP MCP server.
#
# Resolves the Supabase service-role key from 1Password at every MCP launch,
# then execs the TypeScript MCP server over stdio. Claude's GUI-launched MCP
# processes do not inherit shell startup files, so this wrapper can load the
# existing 1Password service-account token from the protected Hermes env file.
#
# Wired into Claude Code via ~/.claude.json under mcpServers["aip-readonly"].
# Update the path there if this script moves.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
AIP_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
OP_TOKEN_ENV_FILE="${AIP_OP_SERVICE_ACCOUNT_ENV_FILE:-${HOME}/.hermes/.env}"
OP_TOKEN_SOURCE_NAME="OP_SERVICE_ACCOUNT_TOKEN_NEXUS_AUDIT"

# Non-secret env
export SUPABASE_PICEO_URL="https://zbryrmxmgfmslqzizsto.supabase.co"

# Secret: read from 1Password via op CLI.
# stderr is fine for diagnostics (MCP transport is stdout); stdout MUST NOT
# leak the key — that would mean writing it into the MCP framing.
if ! command -v op >/dev/null 2>&1; then
  echo "AIP MCP wrapper: 'op' CLI not found on PATH" >&2
  exit 1
fi

load_headless_op_token() {
  local file_mode file_uid line token_value token_found=0

  if [ ! -r "${OP_TOKEN_ENV_FILE}" ]; then
    echo "AIP MCP wrapper: protected 1Password service-account env file is not readable" >&2
    return 1
  fi

  file_mode="$(stat -f '%Lp' "${OP_TOKEN_ENV_FILE}" 2>/dev/null || stat -c '%a' "${OP_TOKEN_ENV_FILE}" 2>/dev/null || true)"
  file_uid="$(stat -f '%u' "${OP_TOKEN_ENV_FILE}" 2>/dev/null || stat -c '%u' "${OP_TOKEN_ENV_FILE}" 2>/dev/null || true)"
  if [ "${file_uid}" != "$(id -u)" ] || { [ "${file_mode}" != "600" ] && [ "${file_mode}" != "400" ]; }; then
    echo "AIP MCP wrapper: refusing insecure 1Password service-account env file" >&2
    return 1
  fi

  while IFS= read -r line || [ -n "${line}" ]; do
    line="${line%$'\r'}"
    case "${line}" in
      "${OP_TOKEN_SOURCE_NAME}="*) token_value="${line#*=}" ;;
      "export ${OP_TOKEN_SOURCE_NAME}="*) token_value="${line#*=}" ;;
      *) continue ;;
    esac

    token_found=$((token_found + 1))
    if [ "${token_found}" -ne 1 ]; then
      echo "AIP MCP wrapper: duplicate service-account token entries in protected env file" >&2
      return 1
    fi

    case "${token_value}" in
      \"*\") token_value="${token_value#\"}"; token_value="${token_value%\"}" ;;
      \'*\') token_value="${token_value#\'}"; token_value="${token_value%\'}" ;;
    esac
    if [ -z "${token_value}" ]; then
      echo "AIP MCP wrapper: service-account token entry is empty" >&2
      return 1
    fi
  done <"${OP_TOKEN_ENV_FILE}"

  if [ "${token_found}" -ne 1 ]; then
    echo "AIP MCP wrapper: service-account token entry is missing from protected env file" >&2
    return 1
  fi

  export OP_SERVICE_ACCOUNT_TOKEN="${token_value}"
}

if [ -z "${OP_SERVICE_ACCOUNT_TOKEN:-}" ]; then
  if [ -n "${OP_SERVICE_ACCOUNT_TOKEN_NEXUS_AUDIT:-}" ]; then
    export OP_SERVICE_ACCOUNT_TOKEN="${OP_SERVICE_ACCOUNT_TOKEN_NEXUS_AUDIT}"
  else
    load_headless_op_token || exit 1
  fi
fi

if ! SUPABASE_PICEO_SERVICE_KEY="$(op read "op://Unite-Group-Infrastructure/SUPABASE_SERVICE_ROLE_KEY/credential" 2>/dev/null)"; then
  SUPABASE_PICEO_SERVICE_KEY=""
fi
unset OP_SERVICE_ACCOUNT_TOKEN OP_SERVICE_ACCOUNT_TOKEN_NEXUS_AUDIT

if [ -z "${SUPABASE_PICEO_SERVICE_KEY:-}" ]; then
  echo "AIP MCP wrapper: failed to read Supabase service key from 1Password" >&2
  echo "  Check the headless service account's access to Unite-Group-Infrastructure" >&2
  exit 1
fi
export SUPABASE_PICEO_SERVICE_KEY

# Exec the server. cd into aip/ so node_modules resolution works.
cd "${AIP_DIR}"
exec npx tsx "${SCRIPT_DIR}/server.ts"
