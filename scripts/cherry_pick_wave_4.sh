#!/usr/bin/env bash
# scripts/cherry_pick_wave_4.sh — RA-1858 cherry-pick prep
#
# Slices the 11 sandbox commits on feature/wave-4-resume into 11 separate
# feature branches against `main`, one per Linear ticket. Each branch is
# stand-alone — committed but NOT pushed. Run with `--push` to push them
# (still no PRs auto-opened).
#
# Usage:
#   bash scripts/cherry_pick_wave_4.sh           # local branches only
#   bash scripts/cherry_pick_wave_4.sh --push    # push all to origin
#   bash scripts/cherry_pick_wave_4.sh --pr      # push + open draft PRs
#                                                # (requires `gh auth login`)
#
# Source: /tmp/pi-ceo-workspaces/wave-4-resume on feature/wave-4-resume
# Target: <Pi-Dev-Ops working tree> — defaults to /Users/phill-mac/Pi-CEO/
#         Pi-Dev-Ops; override with $TARGET_REPO env.
#
# Idempotent: existing branches are skipped (delete first if you want to
# re-create them).

set -euo pipefail

SANDBOX="${SANDBOX:-/tmp/pi-ceo-workspaces/wave-4-resume}"
TARGET_REPO="${TARGET_REPO:-/Users/phill-mac/Pi-CEO/Pi-Dev-Ops}"
PUSH=0
OPEN_PR=0

for arg in "$@"; do
  case "$arg" in
    --push)  PUSH=1 ;;
    --pr)    PUSH=1; OPEN_PR=1 ;;
    --help)
      sed -n '2,18p' "$0"; exit 0 ;;
    *)
      echo "❌ Unknown arg: $arg"; exit 1 ;;
  esac
done

# Ordered list: (sandbox_commit, ticket_id, branch_name, pr_title)
# `feat/wave4-RA-1859-...` style branch names; PR titles are pulled from
# the commit subject by `git log --format=%s`.
declare -a SLICES=(
  # ── Wave 4 Phase A foundations (the 9 children) ───────────────────
  "b12be04 RA-1859  feat/wave4-cfo-stripe-xero"
  "21e1bf4 RA-1867  feat/wave4-debate-runner"
  "5628b95 RA-1860  feat/wave4-cmo-growth"
  "33e0747 RA-1861  feat/wave4-cto-dora"
  "1d61192 RA-1862  feat/wave4-cs-tier1"
  "fdfd0c6 RA-1863  feat/wave4-daily-6pager"
  "f87d063 RA-1864  chore/wave4-honcho-setup-helper"
  "9eb9669 RA-1865  feat/wave4-kanban-adapter"
  "02e258f RA-1866  feat/wave4-voice-composer"
  # ── Track 1 wire-up + Xero shim (last night) ──────────────────────
  "870fc03 RA-1858  feat/wave4-orchestrator-wireup"
  "9325bb1 RA-1859b feat/wave4-xero-shim"
  # ── 1→2→4 sweep (this morning) ────────────────────────────────────
  "a80acc3 RA-1860b feat/wave4-google-ads-cmo"
  "62cb48f RA-1861b feat/wave4-github-actions-cto"
  "785d50d RA-1863b feat/wave4-six-pager-chunking"
  # ── #1+#2+#3 final pass (this morning) ────────────────────────────
  "ee6efc7 RA-1862b feat/wave4-cs-zendesk-intercom"
  "62055b8 RA-1859c feat/wave4-oauth-refresh-sidecar"
  # NOTE: the docs/script commits (CLAUDE.md + this script itself) are
  # intentionally NOT sliced — cherry-pick them manually onto the wireup
  # branch with: git cherry-pick <docs-hash>. Chicken-and-egg otherwise
  # (the slice list lives inside the commit that would update it).
)

if [ ! -d "$TARGET_REPO/.git" ]; then
  echo "❌ TARGET_REPO=$TARGET_REPO is not a git repo"; exit 1
fi
if [ ! -d "$SANDBOX/.git" ]; then
  echo "❌ SANDBOX=$SANDBOX is not a git repo"; exit 1
fi

cd "$TARGET_REPO"
echo "🎯 Target repo: $TARGET_REPO"
echo "📦 Sandbox:     $SANDBOX"
echo ""

# Make sure the sandbox commits are reachable from $TARGET_REPO. The
# recovery branch was already pushed to origin so we can fetch it back.
# But the post-recovery commits live ONLY in the sandbox until we cherry-
# pick them. Add the sandbox as a temporary remote.
SANDBOX_REMOTE="sandbox-$(date +%s)"
git remote add "$SANDBOX_REMOTE" "$SANDBOX"
trap 'git remote remove "$SANDBOX_REMOTE" 2>/dev/null || true' EXIT
git fetch "$SANDBOX_REMOTE" feature/wave-4-resume

git checkout main
git pull --ff-only origin main || {
  echo "⚠ Could not fast-forward main from origin — continuing on local main"
}

for slice in "${SLICES[@]}"; do
  read -r commit ticket branch <<< "$slice"

  if git rev-parse --verify --quiet "$branch" >/dev/null; then
    echo "⏭  $branch already exists locally — skipping"
    continue
  fi

  if ! git cat-file -e "$commit" 2>/dev/null; then
    echo "❌ $commit not reachable in $TARGET_REPO — sandbox fetch failed?"
    continue
  fi

  echo "🍒 $ticket: cherry-pick $commit → $branch"
  git checkout -b "$branch" main
  if ! git cherry-pick -x "$commit"; then
    echo "❌ Cherry-pick conflict on $commit — resolve manually then re-run."
    git cherry-pick --abort 2>/dev/null || true
    git checkout main
    git branch -D "$branch" 2>/dev/null || true
    continue
  fi

  if [ "$PUSH" -eq 1 ]; then
    git push -u origin "$branch"
  fi

  if [ "$OPEN_PR" -eq 1 ]; then
    if ! command -v gh >/dev/null 2>&1; then
      echo "⚠ gh CLI not found — skipping PR creation for $branch"
    else
      pr_title=$(git log -1 --format=%s "$commit")
      gh pr create \
        --base main --head "$branch" \
        --title "$pr_title" \
        --body "$(cat <<EOF_PR
## Summary

Cherry-picked from \`feature/wave-4-resume\` sandbox commit \`$commit\`.

Linked to **$ticket** under epic [RA-1858](https://linear.app/unite-group/issue/RA-1858).

See sandbox progress comment on the ticket for full file list, smoke-test results, and acceptance verification.

## Test plan

- [ ] CI green on this branch
- [ ] Smoke gate: \`pytest tests/test_*.py -q\` (Wave-4 subset)
- [ ] Review the engine + bot + skill diff for the relevant senior agent
- [ ] Verify env-flag activation matches the table in \`CLAUDE.md\` § Senior-Agent Topology

## Source

- Sandbox: \`/tmp/pi-ceo-workspaces/wave-4-resume\` on \`feature/wave-4-resume\`
- Recovery snapshot: \`recovery/2026-05-02-pre-meltdown-snapshot\` (\`ed60618\`, already on origin)

🤖 Generated by \`scripts/cherry_pick_wave_4.sh\`
EOF_PR
)" \
        --draft
    fi
  fi

  git checkout main
  echo ""
done

echo ""
echo "✅ Cherry-pick complete."
git branch | grep "feat/wave4-\|chore/wave4-" || true
echo ""
if [ "$PUSH" -eq 0 ]; then
  echo "Branches are local-only. Re-run with --push to push to origin."
fi
if [ "$OPEN_PR" -eq 0 ]; then
  echo "No PRs opened. Re-run with --pr to push + open all 11 as drafts."
fi
