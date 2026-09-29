#!/usr/bin/env bash
# Mutation controls for check_hook.sh (C6, contract v5). Each mutant is a copy of the quarantined
# hook in a temp dir with one planted fault; the real hook file is never touched. check_hook.sh
# must FAIL on every mutant and PASS on the unmodified copy. A mutant whose sed changed nothing
# is itself a failure, so a control cannot pass vacuously.
# M1-M6 carried from v4; M7-M9 target malformed output (P1-DONE-C6-MALFORMED-OUTPUT-ACCEPTED).
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/../../../.." || exit 9
SRC=docs/plans/plan-to-done-v1.1/plan-to-done/hooks/planning-boundary.sh
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fail=0
mutant() { # $1 label  $2 expected (pass|fail)  $3 sed expression ("" = unmodified)
  local m="$TMP/hook.sh"; cp "$SRC" "$m"
  if [ -n "$3" ]; then
    sed -i.bak -e "$3" "$m"
    if cmp -s "$SRC" "$m"; then echo "FAIL $1: mutant did not change the hook"; fail=1; return; fi
  fi
  HOOK="$m" bash "$HERE/check_hook.sh" >/dev/null 2>&1; rc=$?
  if { [ "$2" = pass ] && [ $rc -eq 0 ]; } || { [ "$2" = fail ] && [ $rc -ne 0 ]; }; then
    echo "ok   $1 (check rc=$rc, want $2)"
  else
    echo "FAIL $1 (check rc=$rc, want $2)"; fail=1
  fi
}
mutant "unmodified hook"                          pass ''
mutant "M1 allow with a reason saying deny"       fail 's/permissionDecision:"deny",permissionDecisionReason:\$r/permissionDecision:"allow",permissionDecisionReason:"deny"/'
mutant "M2 deny() emits nothing (always allow)"   fail 's/^  jq -n --arg r "\$1" .*$/  :/'
mutant "M3 deny() answers ask"                    fail 's/permissionDecision:"deny"/permissionDecision:"ask"/'
mutant "M4 deny() prints plain text deny"         fail 's/^  jq -n --arg r "\$1" .*$/  echo "deny"/'
mutant "M5 deny() exits non-zero"                 fail '/^deny() {/,/^}/s/^  exit 0$/  exit 1/'
mutant "M6 hook denies everything"                fail 's/^case "\$TOOL" in$/deny "all"; case "$TOOL" in/'
mutant "M7 deny object followed by a NUL byte"    fail '/^deny() {/,/^}/s/^  exit 0$/  printf "\\0"; exit 0/'
mutant "M8 deny object followed by a second one"  fail '/^deny() {/,/^}/s/^  exit 0$/  echo "{}"; exit 0/'
mutant "M9 deny object followed by junk text"     fail '/^deny() {/,/^}/s/^  exit 0$/  echo junk; exit 0/'
exit $fail
