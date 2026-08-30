#!/usr/bin/env bash
# test_bridge_failclosed.sh - red-then-green proof suite for the subscription-first
# guards and the deterministic review bridge. Every red case must be REFUSED with
# the right reason; the green controls prove the harness can pass at all.
#
# Sentinel values below are deliberately NOT key-shaped: the guards test for the
# PRESENCE of an override route, never its format, so a literal placeholder proves
# the same property without planting anything that reads as a credential.
#
# Stub guard/codex substitutions are a documented test mechanism - review_bridge.sh
# records every substituted binary path+sha256 in its verdict record by design, so
# a weakened guard is evidence rather than a silent bypass.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
LANE="$ROOT/scripts/estate"
BRIEF="${1:-$ROOT/docs/briefs/estate-librarian-v1.md}"
SENTINEL="GUARD-TEST-SENTINEL-NOT-A-CREDENTIAL"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
PASS=0; FAIL=0
say()  { printf '%s\n' "$*"; }
ok()   { PASS=$((PASS+1)); say "  PASS: $1"; }
bad()  { FAIL=$((FAIL+1)); say "  FAIL: $1"; }

expect_rc() { # expect_rc <name> <want_rc> <got_rc> <log>
  if [ "$3" -eq "$2" ]; then ok "$1 (rc=$3 as required)"; else bad "$1 (want rc=$2 got rc=$3)"; sed 's/^/    | /' "$4" | tail -3; fi
}

say "== Guard proofs (real guards, this node) =="

L="$T/g1"; RC=$(ANTHROPIC_API_KEY="$SENTINEL" GUARD_ALLOWED_BASE_URL="${ANTHROPIC_BASE_URL:-}" bash "$LANE/guard_claude_lane.sh" >"$L" 2>&1; echo $?)
expect_rc "G1 sentinel ANTHROPIC_API_KEY refused" 1 "$RC" "$L"

L="$T/g2"; RC=$(bash "$LANE/guard_claude_lane.sh" >"$L" 2>&1; echo $?)
expect_rc "G2 un-allowlisted ANTHROPIC_BASE_URL (gateway) refused" 1 "$RC" "$L"

L="$T/g3"; RC=$(GUARD_ALLOWED_BASE_URL="${ANTHROPIC_BASE_URL:-__unset__}" bash "$LANE/guard_claude_lane.sh" >"$L" 2>&1; echo $?)
expect_rc "G3 green control: clean env + allowlisted base URL passes" 0 "$RC" "$L"

L="$T/g4"; RC=$(OPENAI_API_KEY="$SENTINEL" bash "$LANE/guard_codex_lane.sh" >"$L" 2>&1; echo $?)
expect_rc "G4 sentinel OPENAI_API_KEY refused" 1 "$RC" "$L"

L="$T/g5"; RC=$(OPENAI_BASE_URL="https://sentinel.example.invalid/v1" bash "$LANE/guard_codex_lane.sh" >"$L" 2>&1; echo $?)
expect_rc "G5 base-URL override refused" 1 "$RC" "$L"

L="$T/g6"; RC=$(bash "$LANE/guard_codex_lane.sh" >"$L" 2>&1; echo $?)
expect_rc "G6 logged-out Codex refused (real codex binary)" 1 "$RC" "$L"

say "== Bridge proofs (stub pass-guards + stub codex; substitutions are recorded) =="
GP="$T/guard_pass.sh"; printf '#!/usr/bin/env bash\necho STUB-GUARD: PASS\nexit 0\n' >"$GP"; chmod +x "$GP"

mkstub() { printf '#!/usr/bin/env bash\n%s\n' "$2" >"$T/$1"; chmod +x "$T/$1"; }
mkstub codex-timeout 'sleep 30'
mkstub codex-killed  'kill -9 $$'
mkstub codex-empty   'exit 0'
mkstub codex-badjson 'echo "this is { not json"'
mkstub codex-badsha  'echo "{\"brief_sha256\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"verdict\":\"APPROVE\",\"provider\":\"openai\",\"model\":\"stub\",\"utc\":\"2026-08-30T00:00:00Z\",\"blocking_items\":[],\"notes\":\"stub\"}"'
mkstub codex-quota   'echo "You have hit your usage limit reached for this billing period" >&2; exit 1'
mkstub codex-green   'H=$(sha256sum brief.md | cut -d" " -f1); echo "{\"brief_sha256\":\"$H\",\"verdict\":\"ADVISORY\",\"provider\":\"openai\",\"model\":\"stub-green\",\"utc\":\"2026-08-30T00:00:00Z\",\"blocking_items\":[],\"notes\":\"harness green control\"}"'

bridge() { # bridge <stub> <outdir>
  GUARD_CLAUDE_BIN="$GP" GUARD_CODEX_BIN="$GP" CODEX_BIN="$T/$1" BRIDGE_TIMEOUT=3 \
    bash "$LANE/review_bridge.sh" --brief "$BRIEF" --out "$2"
}

L="$T/b1"; RC=$( bridge codex-timeout "$T/o1" >"$L" 2>&1; echo $? ); expect_rc "B1 timeout child rejected" 1 "$RC" "$L"
L="$T/b2"; RC=$( bridge codex-killed  "$T/o2" >"$L" 2>&1; echo $? ); expect_rc "B2 killed child rejected" 1 "$RC" "$L"
L="$T/b3"; RC=$( bridge codex-empty   "$T/o3" >"$L" 2>&1; echo $? ); expect_rc "B3 empty output rejected" 1 "$RC" "$L"
L="$T/b4"; RC=$( bridge codex-badjson "$T/o4" >"$L" 2>&1; echo $? ); expect_rc "B4 malformed JSON rejected" 1 "$RC" "$L"
L="$T/b5"; RC=$( bridge codex-badsha  "$T/o5" >"$L" 2>&1; echo $? ); expect_rc "B5 hash-mismatched verdict rejected" 1 "$RC" "$L"
L="$T/b6"; RC=$( bridge codex-quota   "$T/o6" >"$L" 2>&1; echo $? ); expect_rc "B6 quota exhaustion halts with code 3, no fallback" 3 "$RC" "$L"
L="$T/b7"; RC=$( bridge codex-green   "$T/o7" >"$L" 2>&1; echo $? ); expect_rc "B7 green control: valid matching verdict accepted" 0 "$RC" "$L"
if [ -f "$T/o7/verdict-record.json" ] && python3 -m json.tool "$T/o7/verdict-record.json" >/dev/null 2>&1; then
  ok "B7b verdict record written and valid JSON"
else
  bad "B7b verdict record missing or invalid"
fi

L="$T/b8"; RC=$( CODEX_BIN="$T/codex-green" BRIDGE_TIMEOUT=3 bash "$LANE/review_bridge.sh" --brief "$BRIEF" --out "$T/o8" >"$L" 2>&1; echo $? )
expect_rc "B8 default path uses REAL guards and refuses on a logged-out node" 1 "$RC" "$L"

say "== SUMMARY pass=$PASS fail=$FAIL =="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
