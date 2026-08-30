#!/usr/bin/env bash
# test_bridge_failclosed.sh - red-then-green proof suite for the subscription-first
# guards and the deterministic review bridge. Every red case must be REFUSED for the
# RIGHT REASON (exit code AND diagnostic), so an unrelated failure cannot masquerade
# as the property under test. Green controls prove the harness can pass at all.
#
# Sentinel values are deliberately NOT key-shaped: the guards test for the PRESENCE
# of an override route, never its format, so a literal placeholder proves the same
# property without planting anything that reads as a credential.
#
# Stub guard/codex substitutions are a documented test mechanism - review_bridge.sh
# records every substituted binary path+sha256 in its verdict record by design, so a
# weakened guard is evidence rather than a silent bypass.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
LANE="$ROOT/scripts/estate"
BRIEF="${1:-$ROOT/docs/briefs/estate-librarian-v1.md}"
SENTINEL="GUARD-TEST-SENTINEL-NOT-A-CREDENTIAL"
ALLOWLIST="/etc/estate/claude-lane.allow"
T="$(mktemp -d)"
PASS=0; FAIL=0

# cleanup: remove the temp tree and any allowlist this suite created, so the host is
# left exactly as it was found.
cleanup() {
  rm -rf "$T"
  [ -f "$T.allowlist-created" ] && rm -f "$ALLOWLIST"
  rm -f "$T.allowlist-created"
}
trap cleanup EXIT

say()  { printf '%s\n' "$*"; }
ok()   { PASS=$((PASS+1)); say "  PASS: $1"; }
bad()  { FAIL=$((FAIL+1)); say "  FAIL: $1"; }

# expect: assert both the exit code and (optionally) a diagnostic substring, so a case
# cannot pass because some unrelated check failed first.
expect() { # expect <name> <want_rc> <got_rc> <log> [pattern]
  local name="$1" want="$2" got="$3" log="$4" pat="${5:-}"
  if [ "$got" -ne "$want" ]; then
    bad "$name (want rc=$want got rc=$got)"; sed 's/^/    | /' "$log" | tail -3; return
  fi
  if [ -n "$pat" ] && ! grep -qF "$pat" "$log"; then
    bad "$name (rc ok but diagnostic missing: '$pat')"; sed 's/^/    | /' "$log" | tail -3; return
  fi
  ok "$name"
}

# clean_env: run a command with every override route this suite knows about unset, so
# ambient state cannot satisfy or defeat the property under test.
clean_env() {
  env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_PROFILE \
      -u CLAUDE_CODE_OAUTH_TOKEN -u AWS_BEARER_TOKEN_BEDROCK \
      -u CLAUDE_CODE_USE_BEDROCK -u CLAUDE_CODE_USE_VERTEX -u CLAUDE_CODE_USE_FOUNDRY \
      -u OPENAI_API_KEY -u CODEX_API_KEY -u OPENAI_BASE_URL -u OPENAI_API_BASE \
      -u CODEX_HOME -u GUARD_ALLOWED_BASE_URL "$@"
}

say "== Claude lane guard (real guard, deterministic env) =="

L="$T/g1"; clean_env ANTHROPIC_API_KEY="$SENTINEL" bash "$LANE/guard_claude_lane.sh" >"$L" 2>&1; RC=$?
expect "G1 sentinel ANTHROPIC_API_KEY refused" 1 "$RC" "$L" "override route present in environment: ANTHROPIC_API_KEY"

L="$T/g2"; clean_env ANTHROPIC_BASE_URL="https://unapproved.example.invalid" bash "$LANE/guard_claude_lane.sh" >"$L" 2>&1; RC=$?
expect "G2 un-allowlisted ANTHROPIC_BASE_URL refused" 1 "$RC" "$L" "ANTHROPIC_BASE_URL"

# The regression that matters: the allowlist used to come from the environment, so a
# caller could set it equal to whatever endpoint it wanted and self-approve.
L="$T/g2b"; clean_env GUARD_ALLOWED_BASE_URL="https://unapproved.example.invalid" \
  ANTHROPIC_BASE_URL="https://unapproved.example.invalid" bash "$LANE/guard_claude_lane.sh" >"$L" 2>&1; RC=$?
expect "G2b caller-supplied allowlist cannot self-approve" 1 "$RC" "$L" "ANTHROPIC_BASE_URL"

# Green control: a protected host allowlist naming exactly the ambient base URL.
if [ -n "${ANTHROPIC_BASE_URL:-}" ] && [ ! -e "$ALLOWLIST" ]; then
  mkdir -p "$(dirname "$ALLOWLIST")" && printf '%s\n' "$ANTHROPIC_BASE_URL" > "$ALLOWLIST" \
    && chmod 644 "$ALLOWLIST" && touch "$T.allowlist-created"
fi
L="$T/g3"; clean_env bash "$LANE/guard_claude_lane.sh" >"$L" 2>&1; RC=$?
expect "G3 green control: clean env + protected allowlist passes" 0 "$RC" "$L" "GUARD_CLAUDE: PASS"

if [ -f "$T.allowlist-created" ]; then
  chmod 666 "$ALLOWLIST"
  L="$T/g3b"; clean_env bash "$LANE/guard_claude_lane.sh" >"$L" 2>&1; RC=$?
  expect "G3b world-writable allowlist refused" 1 "$RC" "$L" "world-writable"
  chmod 644 "$ALLOWLIST"
else
  say "  SKIP: G3/G3b allowlist cases (no ambient ANTHROPIC_BASE_URL, or allowlist pre-exists)"
fi

say "== Codex lane guard (real guard, isolated HOME) =="

# mkcfg: build an isolated HOME holding a crafted ~/.codex/config.toml, so config
# cases never touch the operator's real Codex configuration.
mkcfg() { mkdir -p "$T/$1/.codex"; printf '%s\n' "$2" > "$T/$1/.codex/config.toml"; echo "$T/$1"; }

H=$(mkcfg h_ok 'forced_login_method = "chatgpt"
cli_auth_credentials_store = "keyring"')
L="$T/g4"; clean_env HOME="$H" OPENAI_API_KEY="$SENTINEL" bash "$LANE/guard_codex_lane.sh" >"$L" 2>&1; RC=$?
expect "G4 sentinel OPENAI_API_KEY refused" 1 "$RC" "$L" "override route present in environment: OPENAI_API_KEY"

L="$T/g5"; clean_env HOME="$H" OPENAI_BASE_URL="https://sentinel.example.invalid/v1" bash "$LANE/guard_codex_lane.sh" >"$L" 2>&1; RC=$?
expect "G5 OPENAI_BASE_URL override refused" 1 "$RC" "$L" "override route present in environment: OPENAI_BASE_URL"

# openai_base_url is honoured by codex 0.151.0 even under forced_login_method="chatgpt",
# and a base_url anchor does not catch the prefixed key.
H2=$(mkcfg h_url 'forced_login_method = "chatgpt"
cli_auth_credentials_store = "keyring"
openai_base_url = "https://sentinel.example.invalid/v1"')
L="$T/g6"; clean_env HOME="$H2" bash "$LANE/guard_codex_lane.sh" >"$L" 2>&1; RC=$?
expect "G6 openai_base_url in config refused" 1 "$RC" "$L" "provider/endpoint override 'openai_base_url'"

H3=$(mkcfg h_prov 'forced_login_method = "chatgpt"
cli_auth_credentials_store = "keyring"
[model_providers.custom]
name = "custom"')
L="$T/g7"; clean_env HOME="$H3" bash "$LANE/guard_codex_lane.sh" >"$L" 2>&1; RC=$?
expect "G7 custom [model_providers] table refused" 1 "$RC" "$L" "[model_providers]"

# The key is cli_auth_credentials_store; its default is "file" and "auto" silently
# falls back to a plaintext auth.json, so both absence and "auto" must fail.
H4=$(mkcfg h_nostore 'forced_login_method = "chatgpt"')
L="$T/g8"; clean_env HOME="$H4" bash "$LANE/guard_codex_lane.sh" >"$L" 2>&1; RC=$?
expect "G8 absent cli_auth_credentials_store refused" 1 "$RC" "$L" "cli_auth_credentials_store"

H5=$(mkcfg h_auto 'forced_login_method = "chatgpt"
cli_auth_credentials_store = "auto"')
L="$T/g9"; clean_env HOME="$H5" bash "$LANE/guard_codex_lane.sh" >"$L" 2>&1; RC=$?
expect "G9 cli_auth_credentials_store=auto refused (plaintext fallback)" 1 "$RC" "$L" "cli_auth_credentials_store"

H6=$(mkcfg h_nopin 'cli_auth_credentials_store = "keyring"')
L="$T/g10"; clean_env HOME="$H6" bash "$LANE/guard_codex_lane.sh" >"$L" 2>&1; RC=$?
expect "G10 missing forced_login_method pin refused" 1 "$RC" "$L" "forced_login_method"

L="$T/g11"; clean_env HOME="$H" bash "$LANE/guard_codex_lane.sh" >"$L" 2>&1; RC=$?
expect "G11 logged-out Codex refused (real codex binary, clean config)" 1 "$RC" "$L" "codex is not logged in"

say "== Bridge proofs (stub pass-guards + stub codex; substitutions are recorded) =="
GP="$T/guard_pass.sh"; printf '#!/usr/bin/env bash\necho STUB-GUARD: PASS\nexit 0\n' >"$GP"; chmod +x "$GP"

# mkstub: write a fake codex that honours `-o FILE` (the real CLI's final-message
# flag) and emits BODY there, so stubs exercise the same path as the real binary.
mkstub() {
  cat >"$T/$1" <<STUB
#!/usr/bin/env bash
OUT=""
while [ \$# -gt 0 ]; do case "\$1" in -o) OUT="\$2"; shift 2;; *) shift;; esac; done
$2
STUB
  chmod +x "$T/$1"
}
emit() { printf 'printf "%%s" %s > "$OUT"\n' "$1"; }

mkstub codex-timeout 'sleep 30'
mkstub codex-killed  'kill -9 $$'
mkstub codex-empty   ': > "$OUT"'
mkstub codex-badjson "$(emit "'this is { not json'")"
mkstub codex-badsha  "$(emit "'{\"brief_sha256\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"verdict\":\"APPROVE\",\"blocking_items\":[],\"provider\":\"openai\",\"model\":\"stub\",\"utc\":\"2026-08-30T00:00:00Z\",\"notes\":\"stub\"}'")"
mkstub codex-quota   'echo "You have hit your usage limit reached for this billing period" >&2; exit 1'
mkstub codex-green   'H=$(sha256sum brief.md | cut -d" " -f1); printf "%s" "{\"brief_sha256\":\"$H\",\"verdict\":\"ADVISORY\",\"blocking_items\":[],\"provider\":\"openai\",\"model\":\"stub-green\",\"utc\":\"2026-08-30T00:00:00Z\",\"notes\":\"harness green control\"}" > "$OUT"'
# The brief itself defines a SUBSCRIPTION_QUOTA_EXHAUSTED rule, so an accepted verdict
# may legitimately mention quota. It must not be misread as the provider refusing.
mkstub codex-quotaword 'H=$(sha256sum brief.md | cut -d" " -f1); printf "%s" "{\"brief_sha256\":\"$H\",\"verdict\":\"APPROVE\",\"blocking_items\":[],\"provider\":\"openai\",\"model\":\"stub-quotaword\",\"utc\":\"2026-08-30T00:00:00Z\",\"notes\":\"the quota exhaustion halt and usage limit handling are correct\"}" > "$OUT"'
mkstub codex-trailing 'H=$(sha256sum brief.md | cut -d" " -f1); printf "%s" "{\"brief_sha256\":\"$H\",\"verdict\":\"APPROVE\",\"blocking_items\":[],\"provider\":\"openai\",\"model\":\"stub\",\"utc\":\"2026-08-30T00:00:00Z\",\"notes\":\"n\"} {\"verdict\":\"BLOCKING\"}" > "$OUT"'
mkstub codex-wrongprov 'H=$(sha256sum brief.md | cut -d" " -f1); printf "%s" "{\"brief_sha256\":\"$H\",\"verdict\":\"APPROVE\",\"blocking_items\":[],\"provider\":\"anthropic\",\"model\":\"stub\",\"utc\":\"2026-08-30T00:00:00Z\",\"notes\":\"n\"}" > "$OUT"'
mkstub codex-missingkey 'H=$(sha256sum brief.md | cut -d" " -f1); printf "%s" "{\"brief_sha256\":\"$H\",\"verdict\":\"APPROVE\",\"provider\":\"openai\",\"model\":\"stub\",\"utc\":\"2026-08-30T00:00:00Z\"}" > "$OUT"'

# bridge: run review_bridge.sh with stubbed guards and a named stub codex.
bridge() { # bridge <stub> <outdir>
  GUARD_CLAUDE_BIN="$GP" GUARD_CODEX_BIN="$GP" CODEX_BIN="$T/$1" BRIDGE_TIMEOUT=3 \
    bash "$LANE/review_bridge.sh" --brief "$BRIEF" --out "$2"
}

L="$T/b1"; bridge codex-timeout "$T/o1" >"$L" 2>&1; RC=$?; expect "B1 timeout child rejected" 1 "$RC" "$L" "timed out"
L="$T/b2"; bridge codex-killed  "$T/o2" >"$L" 2>&1; RC=$?; expect "B2 killed child rejected" 1 "$RC" "$L" "BRIDGE: FAIL"
L="$T/b3"; bridge codex-empty   "$T/o3" >"$L" 2>&1; RC=$?; expect "B3 empty final message rejected" 1 "$RC" "$L" "empty final message"
L="$T/b4"; bridge codex-badjson "$T/o4" >"$L" 2>&1; RC=$?; expect "B4 malformed JSON rejected" 1 "$RC" "$L" "not strict schema-valid JSON"
L="$T/b5"; bridge codex-badsha  "$T/o5" >"$L" 2>&1; RC=$?; expect "B5 hash-mismatched verdict rejected" 1 "$RC" "$L" "hash mismatch"
L="$T/b6"; bridge codex-quota   "$T/o6" >"$L" 2>&1; RC=$?; expect "B6 quota exhaustion halts rc=3, no fallback" 3 "$RC" "$L" "SUBSCRIPTION_QUOTA_EXHAUSTED"
L="$T/b7"; bridge codex-trailing "$T/o7" >"$L" 2>&1; RC=$?; expect "B7 trailing second object rejected" 1 "$RC" "$L" "not strict schema-valid JSON"
L="$T/b8"; bridge codex-wrongprov "$T/o8" >"$L" 2>&1; RC=$?; expect "B8 non-openai provider rejected" 1 "$RC" "$L" "not strict schema-valid JSON"
L="$T/b9"; bridge codex-missingkey "$T/o9" >"$L" 2>&1; RC=$?; expect "B9 missing required key rejected" 1 "$RC" "$L" "not strict schema-valid JSON"

# Regression for the quota false positive: a VALID verdict whose prose mentions quota
# and usage limits must be accepted, not misclassified as provider exhaustion.
L="$T/b10"; bridge codex-quotaword "$T/o10" >"$L" 2>&1; RC=$?
expect "B10 valid verdict mentioning quota is accepted, not misread" 0 "$RC" "$L" "BRIDGE: OK"

L="$T/b11"; bridge codex-green "$T/o11" >"$L" 2>&1; RC=$?
expect "B11 green control: valid matching verdict accepted" 0 "$RC" "$L" "BRIDGE: OK"
if [ -f "$T/o11/verdict-record.json" ] && python3 -m json.tool "$T/o11/verdict-record.json" >/dev/null 2>&1; then
  ok "B11b verdict record written and valid JSON"
else
  bad "B11b verdict record missing or invalid"
fi

L="$T/b12"; CODEX_BIN="$T/codex-green" BRIDGE_TIMEOUT=3 \
  clean_env bash "$LANE/review_bridge.sh" --brief "$BRIEF" --out "$T/o12" >"$L" 2>&1; RC=$?
expect "B12 default path uses REAL guards and refuses on a logged-out node" 1 "$RC" "$L" "guard refused launch"

say "== SUMMARY pass=$PASS fail=$FAIL =="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
