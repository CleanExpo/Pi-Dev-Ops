#!/usr/bin/env bash
# audit-workflows.sh — flag GitHub Actions minute-bloat in a repo's workflows.
# Usage: audit-workflows.sh [repo-dir]   (defaults to CWD)
# Read-only. Exits 0 always; findings go to stdout. Private-repo GitHub Free
# gets 2000 min/month; Windows bills 2x, macOS 10x. This finds what burns it.
set -euo pipefail
DIR="${1:-.}"
WF="$DIR/.github/workflows"
[ -d "$WF" ] || { echo "no .github/workflows in $DIR"; exit 0; }

echo "# Actions minute-bloat audit: $WF"
for f in "$WF"/*.yml "$WF"/*.yaml; do
  [ -e "$f" ] || continue
  echo "## $(basename "$f")"
  found=0
  note() { echo "  - $1"; found=$((found+1)); }
  grep -Eq 'runs-on:.*windows' "$f" && note "windows runner (2x minutes) — fold into ubuntu, or gate to only-when-needed?"
  grep -Eq 'runs-on:.*macos'   "$f" && note "macos runner (10x minutes) — biggest burner; justify or drop"
  if grep -q '^[[:space:]]*push:' "$f" && grep -q '^[[:space:]]*pull_request:' "$f"; then
    grep -q 'branches:' "$f" || note "push + pull_request, no branch filter — PRs run every job twice"
  fi
  grep -q 'concurrency:' "$f" || note "no concurrency block — superseded runs keep burning (add cancel-in-progress)"
  grep -Eq 'paths:|paths-ignore:' "$f" || note "no paths filter — docs-only commits still run full CI"
  grep -q 'schedule:' "$f" && note "scheduled cron — burns minutes on a timer even with no PRs"
  grep -q 'matrix:' "$f" && note "matrix fan-out — each combination is a separately billed job"
  [ "$found" -eq 0 ] && echo "  - clean"
done

echo
echo "# When quota is already exhausted (private repo, 0 min left) — do NOT rerun, it's futile:"
echo "  1. wait for monthly reset (free, slow)"
echo "  2. make repo public -> unlimited free hosted minutes (founder security call)"
echo "  3. self-hosted runner -> free minutes on your own machine (needs runs-on edit)"
echo "  4. raise spending limit / add card (costs money; last resort)"
