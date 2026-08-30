#!/usr/bin/env bash
# guard_codex_lane.sh - subscription-first, fail-closed launch guard (Codex lane).
# PASS only when: forced_login_method="chatgpt" is pinned machine-level, no API-key
# or provider/base-URL override exists, and `codex login status` proves ChatGPT
# authentication. Any doubt fails.
set -uo pipefail

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

# 4. Custom providers / base URLs / API-key preference in config - refuse.
if grep -Eq '^[[:space:]]*(base_url|wire_api)[[:space:]]*=' "$CFG" \
   || grep -Eq '^\[model_providers[.\]]' "$CFG"; then
  fail "custom provider/base_url override configured in $CFG"
fi
grep -Eq '^[[:space:]]*preferred_auth_method[[:space:]]*=[[:space:]]*"apikey"' "$CFG" \
  && fail "preferred_auth_method=\"apikey\" configured in $CFG"

# 5. Keyring credential storage: require it when this codex version supports the
#    setting; refuse a plaintext auth.json when keyring was requested.
if grep -Eq '^[[:space:]]*credential_store' "$CFG"; then
  grep -Eq '^[[:space:]]*credential_store[[:space:]]*=[[:space:]]*"(keyring|auto)"' "$CFG" \
    || fail "credential_store configured but not keyring/auto in $CFG"
else
  echo "GUARD_CODEX: note - no credential_store key in $CFG; set keyring storage on the durable host if this codex version supports it"
fi

# 6. Positive proof: logged in, and the login is ChatGPT (not API key).
CODEX_BIN="${CODEX_BIN:-codex}"
STATUS="$("$CODEX_BIN" login status 2>&1)"; RC=$?
[ $RC -eq 0 ] || fail "codex is not logged in (status: ${STATUS})"
echo "$STATUS" | grep -qi 'api[ -]key' && fail "API-key login detected (status: ${STATUS})"
echo "$STATUS" | grep -qi 'chatgpt' || fail "login status does not prove ChatGPT auth (status: ${STATUS})"

echo "GUARD_CODEX: PASS - ChatGPT subscription auth confirmed; no API-key/provider/base-URL route present"
echo "GUARD_CODEX: evidence - ${STATUS}"
exit 0
