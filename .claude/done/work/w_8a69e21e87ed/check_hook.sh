#!/usr/bin/env bash
# Live deny/allow test of the quarantined plan-to-done boundary hook, with real jq.
# Cases 1 and 5 are positive controls (the hook must deny). Cases 7 and 8 pin the
# known package defect PKG-2 (substring path match): they are ALLOWED today, and this
# script fails if that ever changes silently in either direction.
set -uo pipefail
HOOK="docs/plans/plan-to-done-v1.1/plan-to-done/hooks/planning-boundary.sh"
fail=0
run() { # $1 expected (deny|allow)  $2 label  $3 json
  out="$(printf '%s' "$3" | bash "$HOOK")"
  if printf '%s' "$out" | grep -q '"deny"'; then got=deny; else got=allow; fi
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
