#!/usr/bin/env bash
# Live deny/allow test of the quarantined plan-to-done boundary hook (C6, contract v6).
# v1 grepped output for "deny" (P1-DONE-C6-FALSE-DENIAL-PROOF); v4 read the decision field but
# captured stdout with $(...), which drops NUL bytes before validation
# (P1-DONE-C6-MALFORMED-OUTPUT-ACCEPTED); v5 accepted NaN/Infinity, which JSON.parse rejects
# (P1-DONE-C6-NONSTANDARD-JSON-ACCEPTED). The hook's stdout goes straight to a file and
# hook_verdict.py classifies the raw bytes: exactly one strict JSON object (Python with the
# non-standard constants refused AND node JSON.parse), or nothing.
# Cases 1, 3, 4, 5 are positive controls (must deny). Cases 7 and 8 pin the known package defect
# PKG-2 (substring path match, RA-7819): ALLOWED today, and this fails if that changes silently.
# HOOK may be overridden so check_hook_controls.sh can run this against planted mutants.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/../../../.." || exit 9
HOOK="${HOOK:-docs/plans/plan-to-done-v1.1/plan-to-done/hooks/planning-boundary.sh}"
OUT="$(mktemp)"; trap 'rm -f "$OUT"' EXIT
fail=0
run() { # $1 expected (deny|allow)  $2 label  $3 json
  printf '%s' "$3" | bash "$HOOK" >"$OUT" 2>/dev/null; rc=$?
  got="$(python3 "$HERE/hook_verdict.py" "$OUT" "$rc")" || got="error:verdict"
  if [ "$got" = "$1" ]; then echo "ok   $2 -> $got"; else echo "FAIL $2 -> $got (want $1)"; fail=1; fi
}
run deny  "1 write outside planning path"      '{"tool_name":"Write","tool_input":{"file_path":"app/server/main.py"}}'
run allow "2 write inside docs/plans/"         '{"tool_name":"Write","tool_input":{"file_path":"docs/plans/x/intent.md"}}'
run deny  "3 write SKILL.md inside plans"      '{"tool_name":"Write","tool_input":{"file_path":"docs/plans/x/SKILL.md"}}'
run deny  "4 write with no file_path"          '{"tool_name":"Write","tool_input":{}}'
run deny  "5 bash git push"                    '{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}'
run allow "6 bash read-only ls"                '{"tool_name":"Bash","tool_input":{"command":"ls docs"}}'
run allow "7 PKG-2 ../ traversal (defect)"     '{"tool_name":"Write","tool_input":{"file_path":"docs/plans/../../app/server/main.py"}}'
run allow "8 PKG-2 nested docs/plans (defect)" '{"tool_name":"Write","tool_input":{"file_path":"app/docs/plans/evil.py"}}'
exit $fail
