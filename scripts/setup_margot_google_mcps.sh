#!/usr/bin/env bash
# RA-6915 — Enable Gmail + Google Drive MCPs on Mac mini Hermes (Margot)
#
# Idempotent setup: OAuth client JSON → GDrive auth → Gmail refresh token →
# patch ~/.hermes/config.yaml → restart gateway → smoke test.
#
# Prerequisites (Google Cloud Console — one project is fine):
#   1. Enable APIs: Gmail API + Google Drive API
#   2. OAuth consent screen: External or Internal, add test user if External
#   3. Credentials → Create OAuth client → Application type: Desktop
#   4. Download JSON → pass to this script (or copy to ~/.margot/gcp-oauth.keys.json)
#
# Gmail scope:  https://www.googleapis.com/auth/gmail.modify
# Drive scope:  https://www.googleapis.com/auth/drive.readonly  (GDrive MCP default)
#
# Usage:
#   bash scripts/setup_margot_google_mcps.sh
#   bash scripts/setup_margot_google_mcps.sh --oauth-json ~/Downloads/client_secret_....json
#   bash scripts/setup_margot_google_mcps.sh --dry-run
#   bash scripts/setup_margot_google_mcps.sh --gmail-playground   # manual refresh token
#
# Run on the Mac mini in an interactive session (browser required for first auth).
# Does NOT read/write repo or ~/.hermes/.env files. Secrets stay local.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

MARGOT_DIR="${HOME}/.margot"
OAUTH_KEYS="${MARGOT_DIR}/gcp-oauth.keys.json"
GDRIVE_CREDENTIALS="${MARGOT_DIR}/.gdrive-server-credentials.json"
GMAIL_TOKEN_CACHE="${MARGOT_DIR}/.gmail-mcp-token.json"
HERMES_CONFIG="${HOME}/.hermes/config.yaml"
HERMES_GATEWAY_LABEL="ai.hermes.gateway"

NODE_VERSION="${SETUP_MARGOT_NODE_VERSION:-v24.14.1}"
NVM_ROOT="${NVM_DIR:-${HOME}/.nvm}"
GDRIVE_SERVER="${NVM_ROOT}/versions/node/${NODE_VERSION}/lib/node_modules/@modelcontextprotocol/server-gdrive/dist/index.js"
GDRIVE_PKG_DIR="$(dirname "$GDRIVE_SERVER")/.."

DRY_RUN=0
SKIP_GATEWAY=0
GMAIL_PLAYGROUND=0
OAUTH_JSON_ARG=""

log()  { printf '%s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
    sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
}

while [ $# -gt 0 ]; do
    case "$1" in
        --oauth-json) OAUTH_JSON_ARG="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        --skip-gateway-restart) SKIP_GATEWAY=1; shift ;;
        --gmail-playground) GMAIL_PLAYGROUND=1; shift ;;
        -h|--help) usage ;;
        *) die "unknown argument: $1 (try --help)" ;;
    esac
done

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "'$1' not found — install it first"
}

NODE_BIN="node"

activate_node() {
    # Hermes MCP globals are installed under nvm; default shell node may differ (e.g. v20).
    if [ -s "${NVM_ROOT}/nvm.sh" ]; then
        # shellcheck disable=SC1091
        . "${NVM_ROOT}/nvm.sh"
        nvm use "${NODE_VERSION}" >/dev/null 2>&1 || nvm install "${NODE_VERSION}"
        NODE_BIN="${NVM_ROOT}/versions/node/${NODE_VERSION}/bin/node"
    fi
    if [ ! -x "$NODE_BIN" ]; then
        NODE_BIN="$(command -v node || true)"
    fi
    [ -n "$NODE_BIN" ] && [ -x "$NODE_BIN" ] || die "node not found — install Node ${NODE_VERSION} via nvm"
    GDRIVE_PKG_DIR="$(dirname "$GDRIVE_SERVER")/.."
}

resolve_gdrive_server() {
    if [ -f "$GDRIVE_SERVER" ]; then
        return 0
    fi
    # Fallback: any node on PATH
    if command -v node >/dev/null 2>&1; then
        local prefix
        prefix="$(npm root -g 2>/dev/null || true)"
        if [ -n "$prefix" ] && [ -f "${prefix}/@modelcontextprotocol/server-gdrive/dist/index.js" ]; then
            GDRIVE_SERVER="${prefix}/@modelcontextprotocol/server-gdrive/dist/index.js"
            GDRIVE_PKG_DIR="${prefix}/@modelcontextprotocol/server-gdrive"
            return 0
        fi
    fi
    return 1
}

install_gdrive_server() {
    log "Installing @modelcontextprotocol/server-gdrive globally (node ${NODE_VERSION})…"
    if [ "$DRY_RUN" -eq 1 ]; then
        log "[dry-run] would run: npm install -g @modelcontextprotocol/server-gdrive"
        return 0
    fi
    # shellcheck source=/dev/null
    if [ -s "${NVM_ROOT}/nvm.sh" ]; then
        # shellcheck disable=SC1091
        . "${NVM_ROOT}/nvm.sh"
        nvm use "${NODE_VERSION}" >/dev/null 2>&1 || nvm install "${NODE_VERSION}"
    fi
    npm install -g @modelcontextprotocol/server-gdrive
    resolve_gdrive_server || die "GDrive MCP install failed — ${GDRIVE_SERVER} missing"
}

stage_oauth_keys() {
    mkdir -p "$MARGOT_DIR"
    chmod 700 "$MARGOT_DIR"

    if [ -n "$OAUTH_JSON_ARG" ]; then
        [ -f "$OAUTH_JSON_ARG" ] || die "OAuth JSON not found: $OAUTH_JSON_ARG"
        if [ "$DRY_RUN" -eq 1 ]; then
            log "[dry-run] would copy $OAUTH_JSON_ARG → $OAUTH_KEYS"
        else
            cp "$OAUTH_JSON_ARG" "$OAUTH_KEYS"
            chmod 600 "$OAUTH_KEYS"
            log "OAuth client JSON installed at $OAUTH_KEYS"
        fi
    elif [ ! -f "$OAUTH_KEYS" ]; then
        die "Missing $OAUTH_KEYS — download Desktop OAuth JSON from GCP Console and re-run with:
  bash $SCRIPT_DIR/setup_margot_google_mcps.sh --oauth-json /path/to/client_secret.json"
    else
        log "Using existing OAuth client JSON: $OAUTH_KEYS"
    fi
}

validate_oauth_json() {
    python3 - "$OAUTH_KEYS" <<'PY'
import json, sys
path = sys.argv[1]
with open(path) as f:
    data = json.load(f)
block = data.get("installed") or data.get("web")
if not block or not block.get("client_id") or not block.get("client_secret"):
    sys.exit("OAuth JSON must be a Desktop (installed) client with client_id + client_secret")
print("ok")
PY
}

run_gdrive_auth() {
    resolve_gdrive_server || install_gdrive_server

    if [ -f "$GDRIVE_CREDENTIALS" ]; then
        log "GDrive credentials already exist — skipping browser auth ($GDRIVE_CREDENTIALS)"
        return 0
    fi

    if [ ! -t 0 ] || [ ! -t 1 ]; then
        die "CHECKPOINT: GDrive auth needs an interactive terminal + browser on the Mac mini.
  Run: bash $SCRIPT_DIR/setup_margot_google_mcps.sh
  (opens Google sign-in via @google-cloud/local-auth)"
    fi

    log "Starting Google Drive OAuth (browser will open)…"
    if [ "$DRY_RUN" -eq 1 ]; then
        log "[dry-run] would run GDrive auth"
        return 0
    fi

    GDRIVE_OAUTH_PATH="$OAUTH_KEYS" \
    GDRIVE_CREDENTIALS_PATH="$GDRIVE_CREDENTIALS" \
    "$NODE_BIN" "$GDRIVE_SERVER" auth

    [ -f "$GDRIVE_CREDENTIALS" ] || die "GDrive auth finished but $GDRIVE_CREDENTIALS was not created"
    chmod 600 "$GDRIVE_CREDENTIALS"
    log "GDrive credentials saved (not printing contents)"
}

run_gmail_oauth() {
    if [ -f "$GMAIL_TOKEN_CACHE" ]; then
        if python3 - "$GMAIL_TOKEN_CACHE" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    d = json.load(f)
sys.exit(0 if d.get("refresh_token") else 1)
PY
        then
            log "Gmail token cache present — skipping browser auth ($GMAIL_TOKEN_CACHE)"
            return 0
        fi
    fi

    if [ "$GMAIL_PLAYGROUND" -eq 1 ]; then
        print_gmail_playground_steps
        die "CHECKPOINT: complete OAuth Playground steps above, save refresh token to $GMAIL_TOKEN_CACHE as:
  {\"refresh_token\": \"<token>\", \"client_id\": \"...\", \"client_secret\": \"...\"}
  Then re-run this script."
    fi

    if [ ! -t 0 ] || [ ! -t 1 ]; then
        die "CHECKPOINT: Gmail auth needs an interactive Mac mini session.
  Option A: re-run in Terminal.app with a logged-in GUI session
  Option B: bash $SCRIPT_DIR/setup_margot_google_mcps.sh --gmail-playground"
    fi

    log "Starting Gmail OAuth (browser will open; scope gmail.modify)…"
    if [ "$DRY_RUN" -eq 1 ]; then
        log "[dry-run] would run Gmail OAuth helper"
        return 0
    fi

    # Reuse @google-cloud/local-auth from the globally installed GDrive MCP package.
    resolve_gdrive_server || die "GDrive MCP package required for Gmail OAuth helper"
    activate_node

    local local_auth="${GDRIVE_PKG_DIR}/node_modules/@google-cloud/local-auth/build/src/index.js"
    [ -f "$local_auth" ] || die "GDrive MCP missing @google-cloud/local-auth — reinstall: npm install -g @modelcontextprotocol/server-gdrive"

    LOCAL_AUTH_PATH="$local_auth" \
    OAUTH_KEYS="$OAUTH_KEYS" \
    GMAIL_TOKEN_CACHE="$GMAIL_TOKEN_CACHE" \
    "$NODE_BIN" --input-type=module <<'NODE'
import { pathToFileURL } from "node:url";
import fs from "fs";

const { authenticate } = await import(pathToFileURL(process.env.LOCAL_AUTH_PATH).href);

const keyfile = process.env.OAUTH_KEYS;
const out = process.env.GMAIL_TOKEN_CACHE;

const auth = await authenticate({
  keyfilePath: keyfile,
  scopes: ["https://www.googleapis.com/auth/gmail.modify"],
});

const creds = auth.credentials;
if (!creds.refresh_token) {
  console.error("No refresh_token returned. Revoke prior access at https://myaccount.google.com/permissions");
  console.error("and re-run, or use --gmail-playground with prompt=consent.");
  process.exit(2);
}

const block = JSON.parse(fs.readFileSync(keyfile, "utf8"));
const installed = block.installed || block.web;

fs.writeFileSync(
  out,
  JSON.stringify(
    {
      client_id: installed.client_id,
      client_secret: installed.client_secret,
      refresh_token: creds.refresh_token,
    },
    null,
    2,
  ),
);
fs.chmodSync(out, 0o600);
console.log("Gmail refresh token cached (file only — not printed).");
NODE

    [ -f "$GMAIL_TOKEN_CACHE" ] || die "Gmail OAuth failed — $GMAIL_TOKEN_CACHE not written"
    log "Gmail credentials cached at $GMAIL_TOKEN_CACHE"
}

print_gmail_playground_steps() {
    local client_id
    client_id="$(python3 - "$OAUTH_KEYS" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    d = json.load(f)
print((d.get("installed") or d.get("web"))["client_id"])
PY
)"
    log ""
    log "── Manual Gmail refresh token (OAuth Playground) ──"
    log "1. Open https://developers.google.com/oauthplayground"
    log "2. Gear icon → Use your own OAuth credentials"
    log "   Client ID: (from $OAUTH_KEYS — not printed here)"
    log "3. Select & authorize APIs → Gmail API v1 → https://www.googleapis.com/auth/gmail.modify"
    log "4. Authorize APIs → sign in → Allow"
    log "5. Exchange authorization code for tokens → copy Refresh token"
    log "6. Save $GMAIL_TOKEN_CACHE:"
    log "   {\"client_id\": \"<id>\", \"client_secret\": \"<secret>\", \"refresh_token\": \"<refresh>\"}"
    log ""
    log "OAuth client hint (ID only): ${client_id:0:12}…"
    log ""
}

patch_hermes_config() {
    [ -f "$HERMES_CONFIG" ] || die "Hermes config not found: $HERMES_CONFIG"
    [ -f "$GMAIL_TOKEN_CACHE" ] || die "Gmail token cache missing — run Gmail OAuth first"

    local backup
    backup="${HERMES_CONFIG}.pre-ra6915-$(date +%Y%m%d-%H%M%S)"

    if [ "$DRY_RUN" -eq 1 ]; then
        log "[dry-run] would backup $HERMES_CONFIG → $backup and patch gmail + google-drive"
        return 0
    fi

    cp "$HERMES_CONFIG" "$backup"
    chmod 600 "$backup"
    log "Hermes config backed up to $backup"

    python3 - "$HERMES_CONFIG" "$GMAIL_TOKEN_CACHE" "$OAUTH_KEYS" <<'PY'
import json
import re
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
token_path = Path(sys.argv[2])
oauth_path = Path(sys.argv[3])

with token_path.open() as f:
    tok = json.load(f)

client_id = tok.get("client_id")
client_secret = tok.get("client_secret")
refresh_token = tok.get("refresh_token")
if not all([client_id, client_secret, refresh_token]):
    raise SystemExit("Gmail token cache missing client_id, client_secret, or refresh_token")

lines = config_path.read_text().splitlines(keepends=True)
out: list[str] = []
section: str | None = None

def is_top_level_mcp_server(line: str) -> bool:
    return bool(re.match(r"^  [a-z0-9_-]+:\s*$", line))

for line in lines:
    stripped = line.rstrip("\n")
    if is_top_level_mcp_server(stripped):
        name = stripped.strip().rstrip(":")
        section = name if name in ("gmail", "google-drive") else None

    if section == "gmail":
        if stripped.startswith("      GOOGLE_CLIENT_ID:"):
            line = f"      GOOGLE_CLIENT_ID: {client_id}\n"
        elif stripped.startswith("      GOOGLE_CLIENT_SECRET:"):
            line = f"      GOOGLE_CLIENT_SECRET: {client_secret}\n"
        elif stripped.startswith("      GOOGLE_REFRESH_TOKEN:"):
            line = f"      GOOGLE_REFRESH_TOKEN: {refresh_token}\n"
        elif re.match(r"^    enabled: false\s*$", stripped):
            line = "    enabled: true\n"
    elif section == "google-drive":
        if re.match(r"^    enabled: false\s*$", stripped):
            line = "    enabled: true\n"

    out.append(line)

config_path.write_text("".join(out))
print("Patched gmail env + enabled both MCP servers (secrets not logged).")
PY
}

restart_gateway() {
    if [ "$SKIP_GATEWAY" -eq 1 ]; then
        log "Skipping gateway restart (--skip-gateway-restart)"
        return 0
    fi
    if [ "$DRY_RUN" -eq 1 ]; then
        log "[dry-run] would run: launchctl kickstart -k gui/\$(id -u)/$HERMES_GATEWAY_LABEL"
        return 0
    fi
    log "Restarting Hermes gateway…"
    launchctl kickstart -k "gui/$(id -u)/${HERMES_GATEWAY_LABEL}" \
        || warn "launchctl kickstart failed — restart Hermes manually"
    sleep 3
}

smoke_test() {
    if ! command -v hermes >/dev/null 2>&1; then
        warn "hermes CLI not on PATH — skip smoke test"
        return 0
    fi
    if [ "$DRY_RUN" -eq 1 ]; then
        log "[dry-run] would run: hermes mcp list"
        return 0
    fi

    log ""
    log "── Smoke test: hermes mcp list ──"
    if hermes mcp list 2>/dev/null | tee /tmp/hermes-mcp-list-ra6915.txt; then
        if grep -E 'gmail.*enabled|google-drive.*enabled' /tmp/hermes-mcp-list-ra6915.txt >/dev/null 2>&1 \
           || hermes mcp list 2>/dev/null | grep -qi gmail; then
            log "MCP list OK (see above)"
        else
            warn "hermes mcp list ran but could not confirm gmail/google-drive — check gateway logs"
        fi
    else
        warn "hermes mcp list failed — gateway may still be starting"
    fi
    rm -f /tmp/hermes-mcp-list-ra6915.txt
}

main() {
    log "=== RA-6915 | Margot Google MCP setup ==="
    log "Repo: $REPO_ROOT"
    log ""

    need_cmd python3
    need_cmd npm

    resolve_gdrive_server || true
    activate_node

    stage_oauth_keys
    validate_oauth_json

    run_gdrive_auth
    run_gmail_oauth
    patch_hermes_config
    restart_gateway
    smoke_test

    log ""
    log "=== Done ==="
    log "Gmail + Google Drive MCPs should be enabled in $HERMES_CONFIG"
    log "Verify: hermes mcp list"
    log "Optional: hermes mcp tools gmail   (or tool list subcommand if available)"
}

main "$@"
