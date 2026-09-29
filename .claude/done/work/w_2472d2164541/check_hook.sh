#!/usr/bin/env bash
# Live deny/allow test of the quarantined plan-to-done boundary hook (C6, contract v4).
# Replaces v1's check, which grepped all output for the word "deny" and so accepted a hook
# answering permissionDecision:"allow" with a reason mentioning deny (P1-DONE-C6-FALSE-DENIAL-PROOF).
#
# The verdict is read from the decision field, never from free text:
#   deny  = hook exit 0 AND output is JSON with hookSpecificOutput.hookEventName == "PreToolUse"
#           AND hookSpecificOutput.permissionDecision == "deny"
#   allow = hook exit 0 AND (no output at all, OR that JSON with permissionDecision == "allow")
#   anything else (non-zero exit, malformed JSON, missing or other decision) = error, never a pass.
# Cases 1, 3, 4, 5 are positive controls (must deny). Cases 7 and 8 pin the known package defect
# PKG-2 (substring path match, RA-7819): ALLOWED today, and this fails if that changes silently.
# HOOK may be overridden so check_hook_controls.sh can run this against planted mutants.
set -uo pipefail
cd "$(dirname "$0")/../../../.." || exit 9
HOOK="${HOOK:-docs/plans/plan-to-done-v1.1/plan-to-done/hooks/planning-boundary.sh}"
fail=0
verdict() { # stdin: hook output; $1: hook exit code
  local out; out="$(cat)"
  [ "$1" -eq 0 ] || { echo "error:exit$1"; return; }
  [ -z "$out" ] && { echo allow; return; }
  printf '%s' "$out" | jq -er '
    if (.hookSpecificOutput.hookEventName == "PreToolUse")
       and (.hookSpecificOutput.permissionDecision == "deny" or .hookSpecificOutput.permissionDecision == "allow")
    then .hookSpecificOutput.permissionDecision else error("bad") end' 2>/dev/null || echo "error:shape"
}
run() { # $1 expected (deny|allow)  $2 label  $3 json
  out="$(printf '%s' "$3" | bash "$HOOK" 2>/dev/null)"; rc=$?
  got="$(printf '%s' "$out" | verdict "$rc")"
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
