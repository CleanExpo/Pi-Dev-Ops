#!/usr/bin/env bash
# Daily mirror: ~/.claude/hooks/ → Pi-Dev-Ops/claude-hooks-mirror/
# Per Pi-CEO Board substrate-discipline 2026-05-15: load-bearing hooks
# must be version-controlled, not left as on-disk-only artefacts.
set -e
SRC="$HOME/.claude/hooks/"
DST="$HOME/Pi-Dev-Ops/claude-hooks-mirror/"
rsync -av --delete \
  --exclude='__pycache__' \
  --exclude='*.pyc' --exclude='*.pyo' \
  --exclude='*.log' \
  --exclude='state.json' --exclude='session_start.json' --exclude='progress_throttle.json' \
  --exclude='.DS_Store' \
  "$SRC" "$DST" > /dev/null
cd "$HOME/Pi-Dev-Ops"
if git status --short claude-hooks-mirror/ | grep -q .; then
  git add claude-hooks-mirror/
  git -c commit.gpgsign=false commit -q -m "chore(hooks): nightly mirror sync of ~/.claude/hooks/ ($(date +%Y-%m-%d))" >/dev/null
  git push -q 2>&1 | tail -3
  echo "[$(date -u +%FT%TZ)] hooks-sync committed + pushed"
else
  echo "[$(date -u +%FT%TZ)] hooks-sync no changes"
fi
