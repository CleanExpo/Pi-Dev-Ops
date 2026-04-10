#!/usr/bin/env bash
# hook_build_logs.sh — Claude PostToolUse hook for build-log inspection
#
# Claude calls this after every Bash tool use, passing tool input via CLAUDE_TOOL_INPUT.
# When the command was a `git push origin` or `smoke_test.py` run, this script
# calls check_build_logs.py and prints a report directly into the Claude conversation.
#
# Always exits 0 — hooks must not block Claude.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Extract the command string from the JSON Claude passes in CLAUDE_TOOL_INPUT
CMD=$(python3 - <<'PYEOF'
import sys, json, os
try:
    data = json.loads(os.environ.get("CLAUDE_TOOL_INPUT", "{}"))
    print(data.get("command", ""))
except Exception:
    print("")
PYEOF
)

# Decide if we should trigger
IS_PUSH=$(echo "$CMD" | grep -cE 'git push.*origin' || true)
IS_VERCEL=$(echo "$CMD" | grep -cE 'vercel\s+--prod|vercel\s+deploy' || true)
IS_SMOKE=$(echo "$CMD" | grep -cE 'smoke_test\.py' || true)

if [ "$IS_PUSH" -eq 0 ] && [ "$IS_VERCEL" -eq 0 ] && [ "$IS_SMOKE" -eq 0 ]; then
    exit 0
fi

if [ "$IS_VERCEL" -gt 0 ]; then
    TRIGGER="post-vercel-deploy"
elif [ "$IS_PUSH" -gt 0 ]; then
    TRIGGER="post-git-push"
else
    TRIGGER="post-smoke-test"
fi

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  build-log-agent  ·  trigger: $TRIGGER"
echo "╚══════════════════════════════════════════════════╝"

# After a push, give Vercel ~30s to register & start the build.
# After smoke test, the current production deploy is already stable — inspect immediately.
if [ "$TRIGGER" = "post-git-push" ]; then
    echo "  Waiting 35s for Vercel to register the new deployment…"
    sleep 35
elif [ "$TRIGGER" = "post-vercel-deploy" ]; then
    echo "  Waiting 10s for Vercel deployment to fully register…"
    sleep 10
fi

python3 "$SCRIPT_DIR/check_build_logs.py" 2>&1
STATUS=$?

if [ $STATUS -eq 2 ]; then
    echo ""
    echo "⚠  Build errors detected — review the report above and fix before next push."
elif [ $STATUS -eq 3 ]; then
    echo ""
    echo "✖  Deployment is in ERROR state — roll back or redeploy immediately."
fi

exit 0
