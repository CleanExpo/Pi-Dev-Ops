#!/usr/bin/env bash
# Red-capable loop for: ideas_inbox_drain.yml pushes directly to a protected branch.
#
# Asserts the exact symptom: the workflow's push target is a branch that now
# requires pull-request review, so the job's `git push` will be rejected.
#
# Deterministic (two API/file reads, no network state), fast (~2s), agent-runnable,
# and mutates nothing — it never pushes.
#
# RED  = exit 1  (workflow will be rejected)
# GREEN= exit 0  (workflow will succeed)
set -uo pipefail

WF="${WF:-/d/Pi-Dev-Ops/.github/workflows/ideas_inbox_drain.yml}"
REPO="${REPO:-CleanExpo/Pi-Dev-Ops}"
BRANCH="${BRANCH:-main}"

echo "== loop: ideas_inbox_drain push-to-protected-branch =="

# 1. Does the workflow push, and to where?
if ! grep -qE '^\s*git push\s*$' "$WF"; then
  echo "GREEN: workflow no longer contains a bare 'git push'"
  exit 0
fi
# a bare `git push` after checkout@v4 with no ref: targets the default branch
if grep -qE 'ref:\s*\S+' "$WF"; then
  echo "GREEN: workflow checks out an explicit non-default ref"
  exit 0
fi
echo "  workflow: bare 'git push' + default-branch checkout -> targets '$BRANCH'"

# 2. Does that branch require review?
REVIEWS=$(gh api "repos/$REPO/branches/$BRANCH/protection" \
  --jq '.required_pull_request_reviews.required_approving_review_count // 0' 2>/dev/null)  # fail-open-ok: the captured value is validated as numeric on the next lines and exits 2 if not
# An unreadable protection state must never read as "no protection". Fail loud,
# not green — a broken query looks identical to a clean result otherwise.
if ! [[ "$REVIEWS" =~ ^[0-9]+$ ]]; then
  echo "ERROR: could not read protection for '$BRANCH' (got: ${REVIEWS:-<empty>})."
  echo "       Refusing to report GREEN from an unreadable check."
  exit 2
fi
echo "  branch '$BRANCH': required approving reviews = $REVIEWS"

# 3. Assert
if [ "${REVIEWS:-0}" -ge 1 ]; then
  echo "RED: workflow pushes directly to '$BRANCH', which requires $REVIEWS review(s)."
  echo "     The scheduled job's 'git push' will be rejected by branch protection."
  exit 1
fi
echo "GREEN: '$BRANCH' does not require review; the push would succeed"
exit 0
