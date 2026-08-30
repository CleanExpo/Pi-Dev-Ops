#!/usr/bin/env bash
# guard_codex_lane.sh - subscription-first, fail-closed launch guard (Codex lane).
#
# PASS only when: forced_login_method="chatgpt" is pinned machine-level, credentials
# are held in the OS keyring, no API-key/provider/base-URL override exists, and
# `codex login status` proves ChatGPT authentication. Any doubt fails.
#
# Config key names below were verified against the shipped codex-cli 0.151.0 binary:
# `cli_auth_credentials_store`, `openai_base_url`, `chatgpt_base_url`,
# `model_providers` and `forced_login_method` are all present in it. An earlier
# revision checked `credential_store`, which does not exist in that binary at all,
# so the storage assertion it made was vacuous.
set -uo pipefail

# fail: print the refusal reason to stderr and exit non-zero. Never prints secret values.
fail() { echo "GUARD_CODEX: FAIL - $1" >&2; exit 1; }

# 1. Environment override routes - presence alone fails, values never printed.
for v in OPENAI_API_KEY CODEX_API_KEY OPENAI_BASE_URL OPENAI_API_BASE; do
  if [ -n "${!v:-}" ]; then fail "override route present in environment: $v"; fi
done

# 2. Alternate CODEX_HOME redirects config+credentials - refuse.
if [ -n "${CODEX_HOME:-}" ] && [ "${CODEX_HOME}" != "$HOME/.codex" ]; then
  fail "alternate CODEX_HOME=${CODEX_HOME} (project-controlled auth override risk)"
fi
CFG="${CODEX_HOME:-$HOME/.codex}/config.toml"

# 3. Machine-level pin: forced_login_method = "chatgpt".
[ -f "$CFG" ] || fail "missing $CFG - forced_login_method=\"chatgpt\" is not pinned"
grep -Eq '^[[:space:]]*forced_login_method[[:space:]]*=[[:space:]]*"chatgpt"' "$CFG" \
  || fail "forced_login_method=\"chatgpt\" not pinned in $CFG"

# 4. Provider / endpoint overrides in config - refuse. openai_base_url is honoured by
#    codex 0.151.0 even when forced_login_method="chatgpt", so it must be rejected
#    explicitly; a prefixed key like openai_base_url is not caught by a base_url anchor.
for key in openai_base_url chatgpt_base_url base_url wire_api model_provider; do
  grep -Eq "^[[:space:]]*${key}[[:space:]]*=" "$CFG" \
    && fail "provider/endpoint override '${key}' configured in $CFG"
done
grep -Eq '^[[:space:]]*\[model_providers' "$CFG" \
  && fail "custom [model_providers] table configured in $CFG"

# 5. Credential storage must be the OS keyring. The key's default is "file" and its
#    "auto" value silently falls back to a plaintext auth.json, so require "keyring"
#    exactly - both a wrong value and an absent key fail.
grep -Eq '^[[:space:]]*cli_auth_credentials_store[[:space:]]*=[[:space:]]*"keyring"' "$CFG" \
  || fail "cli_auth_credentials_store must be set to \"keyring\" in $CFG (absent or non-keyring values allow plaintext credential storage)"

# 6. Positive proof: logged in, and the login is ChatGPT (not API key).
CODEX_BIN="${CODEX_BIN:-codex}"
STATUS="$("$CODEX_BIN" login status 2>&1)"; RC=$?
[ $RC -eq 0 ] || fail "codex is not logged in (status: ${STATUS})"
echo "$STATUS" | grep -qi 'api[ -]key' && fail "API-key login detected (status: ${STATUS})"
echo "$STATUS" | grep -qi 'chatgpt' || fail "login status does not prove ChatGPT auth (status: ${STATUS})"

echo "GUARD_CODEX: PASS - ChatGPT subscription auth confirmed; keyring credential storage pinned; no API-key/provider/base-URL route present"
echo "GUARD_CODEX: evidence - ${STATUS}"
exit 0
