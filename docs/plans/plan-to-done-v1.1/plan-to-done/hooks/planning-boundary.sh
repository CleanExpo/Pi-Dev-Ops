#!/usr/bin/env bash
# PreToolUse hook: deterministic planning-only boundary for plan-to-done sessions.
# Denies Write/Edit outside the allowed planning paths and denies Bash commands that
# build, install, push, publish, or reach a model/vendor endpoint.
# Contract: reads the tool call as JSON on stdin; emits hookSpecificOutput.permissionDecision.
# Reference: https://code.claude.com/docs/en/hooks  (PreToolUse, permissionDecision deny/allow/ask)
# Keep this file OUTSIDE any path Claude can Write/Edit (managed settings or a read-only mount):
# permissions.deny rules alone do not protect hook files (anthropics/claude-code#11226).
set -euo pipefail
INPUT="$(cat)"
TOOL="$(printf '%s' "$INPUT" | jq -r '.tool_name // empty')"
ALLOWED="${PLAN_TO_DONE_ALLOWED_PATHS:-docs/plans/ .claude/handoffs/}"

deny() {
  jq -n --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  exit 0
}

case "$TOOL" in
  Write|Edit|MultiEdit|NotebookEdit)
    FP="$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // empty')"
    [ -z "$FP" ] && deny "plan-to-done: write with no file_path"
    ok=0
    for prefix in $ALLOWED; do
      case "$FP" in *"$prefix"*) ok=1;; esac
    done
    case "$FP" in *SKILL.md|*AGENTS.md|*CLAUDE.md|*/.claude/settings*|*/hooks/*) ok=0;; esac
    [ "$ok" -eq 1 ] || deny "plan-to-done: writes limited to planning paths ($ALLOWED); refused $FP"
    ;;
  Bash|PowerShell)
    CMD="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty')"
    if printf '%s' "$CMD" | grep -Eq 'git +(push|commit|merge|rebase)|gh +pr|npm +(publish|install|run|test)|pnpm|yarn|npx|pip +install|pytest|cargo|go +(build|test)|make|docker|vercel|railway|supabase|curl|wget|typesafe|systemone|ANTHROPIC_BASE_URL'; then
      deny "plan-to-done: build/install/push/network command blocked during planning: ${CMD:0:80}"
    fi
    ;;
esac
exit 0   # no decision: normal permission flow applies
