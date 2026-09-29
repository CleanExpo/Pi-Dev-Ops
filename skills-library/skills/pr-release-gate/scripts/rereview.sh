#!/bin/zsh
# Provision a review worktree, then run the Cursor review in it.
# Usage: rereview.sh <review-worktree> <brief> <log>
WT="$1"
env -C "$WT" python3 /Users/phillmcgurk/.claude/skills/pr-release-gate/scripts/pr_release_gate.py provision > "$3.provision" 2>&1 || { echo "provision failed"; tail -5 "$3.provision"; exit 1; }
zsh "$(dirname "$0")/cursor-review.sh" "$WT" "$2" "$3"
