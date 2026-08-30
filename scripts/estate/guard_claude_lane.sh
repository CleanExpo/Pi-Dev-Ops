#!/usr/bin/env bash
# guard_claude_lane.sh - subscription-first, fail-closed launch guard (Claude lane).
# PASS only when the Claude Code login is subscription OAuth (firstParty) and no
# API/profile/provider/gateway route could override it. Any doubt fails.
# Knobs: GUARD_ALLOWED_BASE_URL - the ONE base URL permitted (e.g. a managed host
#        proxy); unset means ANTHROPIC_BASE_URL must be unset.
set -uo pipefail

fail() { echo "GUARD_CLAUDE: FAIL - $1" >&2; exit 1; }

# 1. Environment override routes - presence alone fails, values are never printed.
for v in ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_PROFILE \
         CLAUDE_CODE_OAUTH_TOKEN AWS_BEARER_TOKEN_BEDROCK \
         CLAUDE_CODE_USE_BEDROCK CLAUDE_CODE_USE_VERTEX CLAUDE_CODE_USE_FOUNDRY \
         ANTHROPIC_BEDROCK_BASE_URL ANTHROPIC_VERTEX_BASE_URL \
         ANTHROPIC_VERTEX_PROJECT_ID ANTHROPIC_FOUNDRY_BASE_URL \
         CLAUDE_CODE_SKIP_BEDROCK_AUTH CLAUDE_CODE_SKIP_VERTEX_AUTH; do
  if [ -n "${!v:-}" ]; then fail "override route present in environment: $v"; fi
done

# 2. Gateway / base-URL: only the explicitly allowed value may be set.
if [ -n "${ANTHROPIC_BASE_URL:-}" ] && [ "${ANTHROPIC_BASE_URL}" != "${GUARD_ALLOWED_BASE_URL:-__unset__}" ]; then
  fail "ANTHROPIC_BASE_URL is set and not on the allowlist (gateway override risk)"
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
ok = d.get("loggedIn") is True and d.get("authMethod") == "oauth_token" and d.get("apiProvider") == "firstParty"
sys.exit(0 if ok else 1)
' || fail "auth status is not subscription OAuth/firstParty: $AUTH_JSON"

# 5. Honest limitation, stated: 'claude auth status' does not expose the plan tier.
#    On the durable review host the operator must additionally confirm /status shows
#    the intended Claude Max subscription; this guard proves method+provider only.
echo "GUARD_CLAUDE: PASS - subscription OAuth (firstParty) confirmed; no API/profile/provider/gateway override route present"
echo "GUARD_CLAUDE: evidence - $AUTH_JSON"
echo "GUARD_CLAUDE: note - plan tier not machine-readable via 'claude auth status'; confirm /status shows Claude Max on the review host"
exit 0
