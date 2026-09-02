#!/usr/bin/env bash
# test_dep_gate.sh - red-then-green proof suite for scripts/estate/dep_gate.sh (RA-7408).
#
# WHY THIS FILE IS NOT OPTIONAL. RA-7120 made it a standing rule here: "a control
# never observed rejecting anything is indistinguishable from a control that does not
# fire." RA-7408 is literally about a gate that never fired because it did not exist.
# Shipping it without a proof it can refuse would repeat the defect in a new shape.
#
# Every red case asserts the exit code AND the named reason, so a case cannot pass
# because some unrelated check failed first — the failure mode that let three
# earlier estate designs each look correct while leaking (RA-7383).
#
# The GREEN CONTROLS matter more than the red cases. A gate that refuses everything
# scores full marks on refusals alone. G1 proves the binding checks genuinely pass
# (reaching the not-implemented stage, a distinct refusal), and G2 proves a correctly
# hash-bound waiver is honoured. Without those two, this suite would certify a brick.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
GATE="$ROOT/scripts/estate/dep_gate.sh"
T="$(mktemp -d)"
PASS=0; FAIL=0
trap 'rm -rf "$T"' EXIT

say()  { printf '%s\n' "$*"; }
ok()   { PASS=$((PASS+1)); say "  PASS: $1"; }
bad()  { FAIL=$((FAIL+1)); say "  FAIL: $1"; }

SHA40="0123456789abcdef0123456789abcdef01234567"
SHA40B="fedcba9876543210fedcba9876543210fedcba98"

# write_manifest <file> <dependency_gate-json> [artifact] [sha256]
# Fixtures omit the artifact binding unless a case is exercising it, so stage 0 is
# skipped and each case tests exactly one property.
write_manifest() {
  local out="$1" dg="$2" art="${3:-}" sha="${4:-}"
  python3 - "$out" "$dg" "$art" "$sha" <<'PY'
import json, sys
out, dg, art, sha = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
doc = {"dependency_gate": json.loads(dg)}
if art:
    doc["artifact"] = art
if sha:
    doc["sha256"] = sha
open(out, "w").write(json.dumps(doc, indent=2))
PY
}

# run_gate <manifest> -> sets RC and OUT
run_gate() {
  OUT="$(DEP_GATE_MANIFEST="$1" bash "$GATE" 2>&1)"; RC=$?
}

# expect <name> <want_rc> <want_substring>
expect() {
  local name="$1" want_rc="$2" pat="$3"
  if [ "$RC" -ne "$want_rc" ]; then
    bad "$name (want rc=$want_rc got rc=$RC)"; printf '    | %s\n' "$OUT"; return
  fi
  if ! printf '%s' "$OUT" | grep -qF "$pat"; then
    bad "$name (rc ok but reason missing: '$pat')"; printf '    | %s\n' "$OUT"; return
  fi
  ok "$name"
}

# A fully-satisfied binding set, reused as the base for green controls and mutated
# one field at a time for the red cases.
full_dg() {
  cat <<JSON
{
  "upstream_repo": "https://github.com/example/llm-wiki",
  "upstream_commit_full": "$SHA40",
  "vendoring_manifest": "vendor/llm-wiki",
  "upstream_tree_digest": "$SHA40B",
  "integration_commit": "$SHA40",
  "u1_u2_tests": "tests/u1_ingest.sh, tests/u2_query.sh"
}
JSON
}

say "── RA-7408 dep_gate proof suite"
say ""
say "RED — each binding refused by name"

# R1-R6: drop one required field at a time from an otherwise complete set.
for f in upstream_repo upstream_commit_full vendoring_manifest upstream_tree_digest integration_commit u1_u2_tests; do
  full_dg | python3 -c '
import json,sys
d=json.load(sys.stdin); d.pop(sys.argv[1],None); print(json.dumps(d))
' "$f" > "$T/dg.json"
  write_manifest "$T/m.json" "$(cat "$T/dg.json")"
  run_gate "$T/m.json"
  expect "missing $f is refused by name" 2 "$f"
done

say ""
say "RED — placeholders are not answers"

# R7: the REAL manifest's prose form. Exact-equality matching would read a paragraph
# of explanation as a satisfied binding; this is why `unresolved` matches substrings.
full_dg | python3 -c '
import json,sys
d=json.load(sys.stdin)
d["upstream_commit_full"]="UNRESOLVED_AFTER_FULL_HISTORY_SEARCH - nvk/llm-wiki bare-cloned 2026-08-30, prefix absent"
print(json.dumps(d))
' > "$T/dg.json"
write_manifest "$T/m.json" "$(cat "$T/dg.json")"
run_gate "$T/m.json"
expect "a prose UNRESOLVED value is refused, not read as satisfied" 2 "upstream_commit_full is unresolved"

# R8: the short form RA-7381 is about.
full_dg | python3 -c '
import json,sys
d=json.load(sys.stdin); d["upstream_commit_full"]="d7751c0a"; print(json.dumps(d))
' > "$T/dg.json"
write_manifest "$T/m.json" "$(cat "$T/dg.json")"
run_gate "$T/m.json"
expect "an 8-char short commit is refused where 40 hex is required" 2 "not a 40-hex commit"

# R9: a candidate must not be promoted to a binding.
write_manifest "$T/m.json" '{"upstream_repo_candidate": "https://github.com/nvk/llm-wiki"}'
run_gate "$T/m.json"
expect "upstream_repo_candidate alone does not satisfy upstream_repo" 2 "candidate, not a confirmation"

# R10: non-https upstream.
full_dg | python3 -c '
import json,sys
d=json.load(sys.stdin); d["upstream_repo"]="git@github.com:example/llm-wiki.git"; print(json.dumps(d))
' > "$T/dg.json"
write_manifest "$T/m.json" "$(cat "$T/dg.json")"
run_gate "$T/m.json"
expect "a non-https upstream_repo is refused" 2 "not an https URL"

say ""
say "RED — the waiver cannot approve itself"

# R11: the abuse this control exists for — a waiver asserted with no record file.
full_dg | python3 -c '
import json,sys
d=json.load(sys.stdin); d["d1_decision_record"]="docs/decisions/d1.md"; print(json.dumps(d))
' > "$T/dg.json"
write_manifest "$T/m.json" "$(cat "$T/dg.json")"
run_gate "$T/m.json"
expect "a waiver with no recorded sha256 is a candidate, not a decision" 2 "unbound waiver is a candidate"

# R12: record named but absent.
full_dg | python3 -c '
import json,sys
d=json.load(sys.stdin)
d["d1_decision_record"]="docs/decisions/does-not-exist.md"
d["d1_decision_record_sha256"]="'"$SHA40B"'"
print(json.dumps(d))
' > "$T/dg.json"
write_manifest "$T/m.json" "$(cat "$T/dg.json")"
run_gate "$T/m.json"
expect "a waiver naming a missing record file is refused" 2 "which does not exist"

# R13: record exists but its digest does not match — a tampered or stale waiver.
mkdir -p "$T/docs/decisions"
printf 'D1: standalone-build waiver\n' > "$T/docs/decisions/d1.md"
full_dg | python3 -c '
import json,sys
d=json.load(sys.stdin)
d["d1_decision_record"]="docs/decisions/d1.md"
d["d1_decision_record_sha256"]="'"$SHA40B"'"
print(json.dumps(d))
' > "$T/dg.json"
write_manifest "$T/m.json" "$(cat "$T/dg.json")"
DEP_GATE_ROOT="$T" DEP_GATE_MANIFEST="$T/m.json" bash "$GATE" >"$T/o" 2>&1; RC=$?; OUT="$(cat "$T/o")"
expect "a waiver whose record does not match its digest is refused" 2 "not hash-bound"

say ""
say "RED — a tampered manifest is not trusted"

# R14: the artifact binding is broken. DEP_GATE_ROOT points the gate's relative-path
# resolution at the fixture tree; without it the gate looks under the real repo root
# and this case passes for the wrong reason ("file is missing" rather than "hash
# binding broken"). That mistake was live until the suite caught it.
mkdir -p "$T/docs/briefs"
printf 'brief body\n' > "$T/docs/briefs/fake-brief.md"
write_manifest "$T/m.json" "$(full_dg)" "docs/briefs/fake-brief.md" "$SHA40B"
DEP_GATE_ROOT="$T" DEP_GATE_MANIFEST="$T/m.json" bash "$GATE" >"$T/o" 2>&1; RC=$?; OUT="$(cat "$T/o")"
expect "a broken hash binding is refused before the bindings are read" 2 "hash binding broken"

say ""
say "GREEN CONTROLS — without these, a gate that refuses everything would pass"

# G1: every binding well-formed. Must reach stage 3 and refuse THERE, with a
# different reason. This is what proves the binding checks pass rather than the gate
# simply saying no to everything.
write_manifest "$T/m.json" "$(full_dg)"
run_gate "$T/m.json"
expect "a complete binding set reaches the not-implemented stage (bindings DID pass)" 2 "full-history verification is not implemented"

# G2: a correctly hash-bound waiver is honoured — exit 0, the one passing state
# reachable today. Proves the waiver path is a real path and not decoration.
REAL_SHA="$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$T/docs/decisions/d1.md")"
full_dg | python3 -c '
import json,sys
d=json.load(sys.stdin)
d["d1_decision_record"]="docs/decisions/d1.md"
d["d1_decision_record_sha256"]=sys.argv[1]
print(json.dumps(d))
' "$REAL_SHA" > "$T/dg.json"
write_manifest "$T/m.json" "$(cat "$T/dg.json")"
DEP_GATE_ROOT="$T" DEP_GATE_MANIFEST="$T/m.json" bash "$GATE" >"$T/o" 2>&1; RC=$?; OUT="$(cat "$T/o")"
expect "a hash-bound waiver is honoured (exit 0)" 0 "DEPENDENCY_WAIVED_BY_D1"

say ""
say "GREEN CONTROL — the real manifest, today"

# G3: the live manifest must refuse, and for the RA-7381 reason. If this ever starts
# passing without the founder inputs arriving, something has gone wrong.
OUT="$(bash "$GATE" 2>&1)"; RC=$?
expect "the live manifest is BLOCKED_DEPENDENCY today" 2 "BLOCKED_DEPENDENCY"

say ""
say "── summary  pass=$PASS fail=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
