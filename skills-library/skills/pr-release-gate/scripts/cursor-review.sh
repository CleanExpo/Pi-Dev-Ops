#!/bin/zsh
# Usage: cursor-review.sh <review-worktree> <brief-file> <log-file>
# Runs Cursor as the independent reviewer inside a disposable worktree; Cursor writes
# ./reviewer-report.json itself. Hard 40-minute ceiling.
WT="$1"; BRIEF="$2"; LOG="$3"
PROMPT="$(< "$BRIEF")"
cd "$WT" || exit 3
perl -e 'alarm 2400; exec @ARGV' /Users/phillmcgurk/.local/bin/cursor-agent --print --force --output-format text "$PROMPT" > "$LOG" 2>&1
rc=$?
echo "cursor exit=$rc"
if [ -s "$WT/reviewer-report.json" ]; then
  python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print('report:',d.get('reviewer_agent'),d.get('verdict'),d.get('head_sha'),'blocking',len(d.get('blocking_findings',[])))" "$WT/reviewer-report.json"
else
  echo "NO REPORT WRITTEN"
fi
