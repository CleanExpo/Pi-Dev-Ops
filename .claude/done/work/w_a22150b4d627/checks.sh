#!/bin/sh
# Criterion recipes for RA-7559. Usage: checks.sh C2|C3|C4|C6. Exit code is the evidence.
set -u
case "$1" in
  C2)  # no donectl runtime file is tracked
    hits=$(git ls-files .claude/done | grep -E '(^|/)(ACTIVE\.json|state\.json|notes\.jsonl)$')
    [ -z "$hits" ] || { echo "tracked runtime files:"; echo "$hits"; exit 1; } ;;
  C3)  # ignore rules: runtime ignored, evidence not ignored
    git check-ignore -q .claude/done/ACTIVE.json || exit 1
    git check-ignore -q .claude/done/work/w_x/state.json || exit 1
    git check-ignore -q .claude/done/work/w_x/notes.jsonl || exit 1
    git check-ignore -q .claude/done/work/w_x/contract.json && exit 1
    git check-ignore -q .claude/done/work/w_x/lock.json && exit 1
    exit 0 ;;
  C4)  # CI runs pytest over tests/ on pull_request
    grep -q 'run: pytest tests/' .github/workflows/ci.yml || exit 1
    grep -q 'pull_request:' .github/workflows/ci.yml || exit 1 ;;
  C6)  # no contract.json / lock.json tracked on the base was dropped
    base=be518374d6abae8f241956979792e2ad82da6b3f
    missing=$(git ls-tree -r --name-only "$base" .claude/done | grep -E '/(contract|lock)\.json$' | while read -r f; do git ls-files --error-unmatch "$f" >/dev/null 2>&1 || echo "$f"; done)
    [ -z "$missing" ] || { echo "dropped evidence:"; echo "$missing"; exit 1; } ;;
  *) echo "unknown criterion $1"; exit 2 ;;
esac
