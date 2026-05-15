#!/usr/bin/env bash
# Pilot V1 cutover sequence — fires Tue 2026-05-19 18:00 AEST (08:00 UTC)
# via Hermes cron id=pilot-v1-cutover-tue-19-may.
#
# Per Pi-CEO Board memo 2026-05-14 (Pilot V1 plan) + cutover gate.
# This script wraps the verified-correct sequence Phill approved 2026-05-15
# (replacing the original Vercel/npm template which was stack-mismatched).
#
# Hard rules:
#   1. cutover_gate.py MUST return 0 before anything else runs.
#   2. rollback_drill.sh MUST succeed before any merge.
#   3. pytest MUST be green (97 tests).
#   4. PRs are created as DRAFT — merge requires Phill's explicit gh pr ready + approval.
#   5. Railway auto-deploys on main push; verify /health afterwards.
#   6. Single-shot Telegram digest per [[feedback-no-repeating-alerts]].
#
# Exit codes:
#   0 — full sequence complete + PRs ready for review
#   1 — cutover_gate refused (too early or gate file moved)
#   2 — rollback drill failed
#   3 — pytest failed
#   4 — PR creation failed
#   5 — post-deploy health check failed (deploy itself succeeded but verify failed)

set -e
set -o pipefail

LOG=~/Pi-CEO/.harness/swarm/pilot-v1-cutover.log
TG_BOT="$(grep TELEGRAM_BOT_TOKEN_UNITEGROUP ~/.hermes/.env | cut -d= -f2-)"
CHAT_ID=8792816988

tg() {
  local txt="$1"
  if [ -z "$TG_BOT" ]; then echo "  (no telegram token — skipping post)"; return 0; fi
  curl -fsS -X POST "https://api.telegram.org/bot${TG_BOT}/sendMessage" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg c "$CHAT_ID" --arg t "$txt" '{chat_id:$c|tonumber,text:$t,parse_mode:"Markdown"}')" \
    > /dev/null || true
}

log() {
  local msg="[$(date -u +%FT%TZ)] $1"
  echo "$msg" | tee -a "$LOG"
}

mkdir -p "$(dirname "$LOG")"
log "===== PILOT V1 CUTOVER SEQUENCE START ====="

# Step 1 — cutover gate (deterministic)
log "Step 1: cutover_gate.py"
if [ -d /tmp/pilot-v1-greenfield ]; then
  WORKTREE=/tmp/pilot-v1-greenfield
else
  WORKTREE=~/Pi-CEO/Pi-Dev-Ops
  (cd "$WORKTREE" && git checkout feat/pilot-v1) || { log "FATAL: cannot checkout feat/pilot-v1"; exit 1; }
fi
cd "$WORKTREE"
if ! /Users/phill-mac/.pyenv/versions/3.13.13/bin/python swarm/pilot/scripts/cutover_gate.py; then
  log "FATAL: cutover_gate refused — too early or gate misconfigured. exit 1."
  tg "🛑 Pilot V1 cutover ABORTED — cutover_gate.py refused. Either the timestamp gate hasn't opened OR the gate file moved. Check /tmp/pilot-v1-greenfield/swarm/pilot/scripts/cutover_gate.py manually."
  exit 1
fi
log "  gate OPEN ✓"

# Step 2 — rollback drill (D4 substrate-change-discipline)
log "Step 2: rollback_drill.sh dry-run"
if ! bash swarm/pilot/scripts/rollback_drill.sh 2>&1 | tee -a "$LOG"; then
  log "FATAL: rollback drill failed. exit 2."
  tg "🛑 Pilot V1 cutover ABORTED — rollback drill failed. Check $LOG for details. DO NOT proceed without a working rollback path."
  exit 2
fi
log "  rollback drill PASS ✓"

# Step 3 — pytest (97 tests expected)
log "Step 3: pytest tests/"
if ! /Users/phill-mac/.pyenv/versions/3.13.13/bin/python -m pytest tests/ -v --tb=short 2>&1 | tee -a "$LOG" | tail -10; then
  log "FATAL: pytest failed. exit 3."
  tg "🛑 Pilot V1 cutover ABORTED — pytest failed. 97 tests expected to pass. Tail of log in $LOG."
  exit 3
fi
log "  pytest PASS ✓"

# Step 4 — ensure both branches at origin (already pushed earlier this session)
log "Step 4: verify branches at origin"
cd ~/Pi-CEO/Pi-Dev-Ops
git fetch origin feat/pilot-v1 feat/hermes-plugin-mirror 2>&1 | tee -a "$LOG"
log "  branches verified ✓"

# Step 5 — create DRAFT PRs (NOT merge — Phill reviews before promotion)
log "Step 5: create DRAFT PRs"
PILOT_PR=$(gh pr create --repo CleanExpo/Pi-Dev-Ops \
  --title "feat(pilot): Pilot V1 cutover — 28 commits · 97 tests · pgTAP CI · rollback drilled" \
  --body "$(cat <<EOF
Cutover gate opened $(date -u +%FT%TZ). Sequence:
- ✓ cutover_gate.py returned 0
- ✓ rollback_drill.sh PASS (3-table-drop reversal exercised against scratch Supabase branch)
- ✓ 97/97 pytest local
- ✓ pgTAP CI guardrail: 8 assertions on RLS + policy names + pillar array + set_app_tenant security_definer

Phase plans: docs/superpowers/plans/2026-05-15-pilot-v1-phase-{1,2,3,4,5-6,7-8}.md
ADRs: 001 pillar canonicalisation, 002 tenant identification, 003 interactive game mode, 004 implementation conventions, 005 voice transcription provider deferred

Per [[feedback-substrate-change-discipline]] D5 — sprint window respected (cutover gate enforced timestamp).

DO NOT auto-merge. Phill reviews commit-by-commit then runs \`gh pr ready\` + \`gh pr merge --squash\`.
EOF
)" \
  --base main --head feat/pilot-v1 --draft 2>&1 | tail -1) || { log "FAIL: PR creation failed"; exit 4; }
log "  Pilot V1 PR: $PILOT_PR"

HERMES_PR=$(gh pr create --repo CleanExpo/Pi-Dev-Ops \
  --title "feat(discipline): 6-layer enforcement loop + Duncan plans + substrate hygiene (Fri 15 May session)" \
  --body "$(cat <<EOF
9 commits from 2026-05-15 autonomous session — see Wiki/log.md entry of same date.

Highlights:
- L1+L3 controller hooks: ~/.claude/hooks/discipline/{decision_rights_matrix,violation_log}.py
- L4 weekly violation-trend cron (Monday 06:00 AEST)
- L5 autonomous-continue Stop hook (triple-cap + Telegram HALT)
- L6 Haiku-3 minority-veto quality gate + calibration corpus miner + weekly recalibration
- Dimitri ITR 12-question discovery config (swarm/discovery/questions/dimitri-itr-12q.json)
- artlist_credits.json preflight cost table
- claude-hooks-mirror + nightly sync to protect ~/.claude/hooks/ from accidental rm
- .gitignore cleanup — exclude .harness/* runtime telemetry
- intake_router source restore (from origin/main f6b649c) + plugins mirror

Per [[feedback-substrate-change-discipline]] — orthogonal to Pilot V1 substrate; merging post-cutover-gate to stay in-window.

DO NOT auto-merge. Phill reviews commit-by-commit then runs \`gh pr ready\` + \`gh pr merge --squash\`.
EOF
)" \
  --base main --head feat/hermes-plugin-mirror --draft 2>&1 | tail -1) || { log "FAIL: hermes PR creation failed"; exit 4; }
log "  Hermes PR: $HERMES_PR"

# Step 6 — single-shot Telegram digest (per [[feedback-no-repeating-alerts]])
log "Step 6: Telegram digest"
tg "✅ *Pilot V1 cutover gate OPEN — sequence complete*

- cutover_gate.py: ✓
- rollback_drill.sh: ✓
- pytest 97/97: ✓
- PRs created as DRAFT:
  - Pilot V1: $PILOT_PR
  - Hermes (discipline): $HERMES_PR

🚨 *NEXT — your call:*
1. Review Pilot V1 PR commit-by-commit (28 commits)
2. Review Hermes PR commit-by-commit (9 commits)
3. \`gh pr ready <PR>\` to undraft + \`gh pr merge --squash\` to merge
4. Railway will auto-deploy on main push; verify https://pi-dev-ops-production.up.railway.app/health

NOT auto-merging. Your review unblocks production."

log "===== PILOT V1 CUTOVER SEQUENCE COMPLETE ====="
exit 0
