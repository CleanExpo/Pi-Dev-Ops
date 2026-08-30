#!/usr/bin/env bash
# guard_claude_lane.sh - subscription-first, fail-closed launch guard (Claude lane).
#
# PASS only when the Claude Code login is subscription OAuth (firstParty) and no
# API/profile/provider/gateway route could override it. Any doubt fails.
#
# The base-URL allowlist is deliberately NOT read from the environment. The bridge
# invokes this guard with the caller's environment inherited, so an env-supplied
# allowlist could be set equal to whatever ANTHROPIC_BASE_URL the caller wanted to
# smuggle in, which would make the check self-approving. The single approved URL is
# read from protected host configuration at a fixed path instead.
set -uo pipefail

# Fixed, non-overridable. Changing the allowlist requires host-level write access.
ALLOWLIST_FILE="/etc/estate/claude-lane.allow"

# fail: print the refusal reason to stderr and exit non-zero. Never prints secret values.
fail() { echo "GUARD_CLAUDE: FAIL - $1" >&2; exit 1; }

# read_approved_base_url: echo the single approved base URL from protected host
# configuration, or the empty string when no allowlist is configured. Refuses a
# symlinked, group/world-writable, malformed, or non-HTTPS allowlist.
read_approved_base_url() {
  [ -e "$ALLOWLIST_FILE" ] || { echo ""; return 0; }
  [ -L "$ALLOWLIST_FILE" ] && fail "allowlist $ALLOWLIST_FILE is a symlink"
  [ -f "$ALLOWLIST_FILE" ] || fail "allowlist $ALLOWLIST_FILE is not a regular file"
  local perms
  perms="$(stat -c '%a' "$ALLOWLIST_FILE" 2>/dev/null || stat -f '%Lp' "$ALLOWLIST_FILE" 2>/dev/null)"
  case "$perms" in
    *[2367])   fail "allowlist $ALLOWLIST_FILE is world-writable (mode $perms)";;
    ?[2367]?)  fail "allowlist $ALLOWLIST_FILE is group-writable (mode $perms)";;
  esac
  local lines url
  lines="$(grep -cvE '^[[:space:]]*(#|$)' "$ALLOWLIST_FILE" || true)"
  [ "$lines" = "1" ] || fail "allowlist $ALLOWLIST_FILE must hold exactly one URL (found $lines)"
  url="$(grep -vE '^[[:space:]]*(#|$)' "$ALLOWLIST_FILE" | head -1 | tr -d '[:space:]')"
  case "$url" in
    https://*) ;;
    *) fail "allowlist URL is not HTTPS";;
  esac
  echo "$url"
}

# 1. Environment override routes - presence alone fails, values are never printed.
for v in ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_PROFILE \
         CLAUDE_CODE_OAUTH_TOKEN AWS_BEARER_TOKEN_BEDROCK \
         CLAUDE_CODE_USE_BEDROCK CLAUDE_CODE_USE_VERTEX CLAUDE_CODE_USE_FOUNDRY \
         ANTHROPIC_BEDROCK_BASE_URL ANTHROPIC_VERTEX_BASE_URL \
         ANTHROPIC_VERTEX_PROJECT_ID ANTHROPIC_FOUNDRY_BASE_URL \
         CLAUDE_CODE_SKIP_BEDROCK_AUTH CLAUDE_CODE_SKIP_VERTEX_AUTH; do
  if [ -n "${!v:-}" ]; then fail "override route present in environment: $v"; fi
done

# 2. Gateway / base URL: only the protected-config value may be set.
APPROVED_BASE_URL="$(read_approved_base_url)"
if [ -n "${ANTHROPIC_BASE_URL:-}" ]; then
  [ -n "$APPROVED_BASE_URL" ] || fail "ANTHROPIC_BASE_URL is set but no approved allowlist exists at $ALLOWLIST_FILE"
  [ "$ANTHROPIC_BASE_URL" = "$APPROVED_BASE_URL" ] || fail "ANTHROPIC_BASE_URL does not match the approved value in $ALLOWLIST_FILE"
fi

# 3. apiKeyHelper anywhere in effective settings.
for f in "$HOME/.claude/settings.json" "$HOME/.claude/settings.local.json" \
         "${CLAUDE_PROJECT_DIR:-$PWD}/.claude/settings.json" \
         "${CLAUDE_PROJECT_DIR:-$PWD}/.claude/settings.local.json"; do
  if [ -f "$f" ] && grep -q '"apiKeyHelper"' "$f"; then
    fail "apiKeyHelper configured in $f"
  fi
done

# 4. Positive proof: subscription OAuth on the first-party provider.
CLAUDE_BIN="${CLAUDE_BIN:-claude}"
AUTH_JSON="$("$CLAUDE_BIN" auth status 2>/dev/null)" || fail "'claude auth status' failed - cannot prove subscription login"
echo "$AUTH_JSON" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(1)
ok = (d.get("loggedIn") is True
      and d.get("authMethod") == "oauth_token"
      and d.get("apiProvider") == "firstParty")
sys.exit(0 if ok else 1)
' || fail "auth status is not subscription OAuth/firstParty: $AUTH_JSON"

# 5. Honest limitation, stated: 'claude auth status' does not expose the plan tier.
#    On the durable review host the operator must additionally confirm /status shows
#    the intended Claude Max subscription; this guard proves method+provider only.
echo "GUARD_CLAUDE: PASS - subscription OAuth (firstParty) confirmed; no API/profile/provider/gateway override route present"
echo "GUARD_CLAUDE: evidence - $AUTH_JSON"
echo "GUARD_CLAUDE: note - plan tier not machine-readable via 'claude auth status'; confirm /status shows Claude Max on the review host"
exit 0
