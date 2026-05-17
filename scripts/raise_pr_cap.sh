#!/usr/bin/env bash
# scripts/raise_pr_cap.sh — RA-3019
#
# Operator helper: set TAO_SWARM_MAX_DAILY_PRS in Railway + redeploy in one
# command. The actual enforced cap is auto-clamped to
# SAFE_FALLBACK_MAX_DAILY_PRS (3) by swarm/config.py:effective_max_daily_prs()
# until `green_merge_counter.json` shows >= 20 consecutive supervised green
# merges. Setting this env var above 3 only takes effect after that gate.
#
# Usage:
#   scripts/raise_pr_cap.sh <N>            # set env + redeploy
#   scripts/raise_pr_cap.sh <N> --dry-run  # print commands, take no action
#   scripts/raise_pr_cap.sh --show         # show current value
#
# Recommended progression (per board): 3 → 5 → 8 → 12, advancing only when
# evaluator-pass-rate sustains for a full week at the current cap.

set -euo pipefail

show_usage() {
    cat <<EOF
Usage: $0 <N> [--dry-run]
       $0 --show

Sets TAO_SWARM_MAX_DAILY_PRS in the Railway service and triggers a redeploy.
EOF
}

if [ "$#" -lt 1 ]; then show_usage; exit 1; fi

if [ "$1" = "--show" ]; then
    if ! command -v railway >/dev/null 2>&1; then
        echo "ERROR: railway CLI not installed (npm i -g @railway/cli)" >&2
        exit 2
    fi
    # Strip the value if your env contains secret-looking values; this only
    # prints the one knob we care about.
    railway variables 2>/dev/null \
        | grep -E '^TAO_SWARM_MAX_DAILY_PRS\s*=' \
        || echo "TAO_SWARM_MAX_DAILY_PRS is unset (defaults to 3)"
    exit 0
fi

NEW_CAP="$1"
DRY_RUN=0
[ "${2:-}" = "--dry-run" ] && DRY_RUN=1

if ! [[ "$NEW_CAP" =~ ^[0-9]+$ ]]; then
    echo "ERROR: cap must be a non-negative integer (got: $NEW_CAP)" >&2
    show_usage
    exit 1
fi

if [ "$NEW_CAP" -gt 50 ]; then
    echo "REFUSING: $NEW_CAP > 50 looks like a misconfiguration." >&2
    echo "If you really mean it, set the env var via the Railway dashboard." >&2
    exit 1
fi

if ! command -v railway >/dev/null 2>&1; then
    echo "ERROR: railway CLI not installed (npm i -g @railway/cli)" >&2
    exit 2
fi

set_cmd="railway variables --set TAO_SWARM_MAX_DAILY_PRS=$NEW_CAP"
deploy_cmd="railway redeploy"

if [ "$DRY_RUN" -eq 1 ]; then
    echo "DRY-RUN — would execute:"
    echo "  $set_cmd"
    echo "  $deploy_cmd"
    exit 0
fi

echo ">>> Setting TAO_SWARM_MAX_DAILY_PRS=$NEW_CAP"
$set_cmd

echo ">>> Triggering Railway redeploy"
$deploy_cmd

echo
echo "Done. The new cap is effective AFTER the redeploy completes."
echo "Note: the cap auto-clamps to SAFE_FALLBACK_MAX_DAILY_PRS=3 until"
echo "      .harness/swarm/green_merge_counter.json shows consecutive_green >= 20."
echo "Verify post-deploy:"
echo "  curl -sS \$PIDEVOPS_URL/api/swarm/status | jq .pr_quota"
