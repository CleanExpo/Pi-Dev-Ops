#!/usr/bin/env bash
# estate-protection-audit.sh — audit CleanExpo repos against the PR-merge standard.
#
# Standard (SPM spec 2026-07-13, session 0226d4fc):
#   - default branch protection: required checks present where CI exists,
#     enforce_admins=true, NO required reviews, strict=false
#   - repo settings: allow_auto_merge=true, allow_update_branch=true,
#     delete_branch_on_merge=true
#
# Read-only. Exit 0 = every audited repo matches; exit 1 = drift found.
# Usage: scripts/estate-protection-audit.sh [repo ...]   (defaults to the active set)

set -euo pipefail

REPOS=("$@")
if [ ${#REPOS[@]} -eq 0 ]; then
  REPOS=(Unite-Group RestoreAssist CARSI Synthex Disaster-Recovery DR-NRPG CCW-CRM Pi-Dev-Ops ATO skills-library NEXUS brain-1 oh-my-codex NodeJS-Starter-V1)
fi

drift=0

for repo in "${REPOS[@]}"; do
  meta=$(gh api "repos/CleanExpo/$repo" 2>/dev/null) || { echo "?? $repo: unreadable"; drift=1; continue; }
  branch=$(jq -r .default_branch <<<"$meta")
  visibility=$(jq -r .visibility <<<"$meta")

  repo_issues=()
  [ "$(jq -r .allow_auto_merge <<<"$meta")" = "true" ] || repo_issues+=("auto_merge=off")
  [ "$(jq -r .allow_update_branch <<<"$meta")" = "true" ] || repo_issues+=("update_branch=off")
  [ "$(jq -r .delete_branch_on_merge <<<"$meta")" = "true" ] || repo_issues+=("delete_on_merge=off")

  prot=$(gh api "repos/CleanExpo/$repo/branches/$branch/protection" 2>/dev/null || true)
  if [ -z "$prot" ]; then
    if [ "$visibility" = "private" ]; then
      repo_issues+=("protection-unreadable(private/free-plan)")
    else
      repo_issues+=("no-branch-protection")
    fi
  else
    [ "$(jq -r '.required_pull_request_reviews != null' <<<"$prot")" = "false" ] || repo_issues+=("required-reviews-present(deadlock)")
    [ "$(jq -r '.required_status_checks.strict // false' <<<"$prot")" = "false" ] || repo_issues+=("strict=true(merge-train)")
    [ "$(jq -r '.enforce_admins.enabled // false' <<<"$prot")" = "true" ] || repo_issues+=("enforce_admins=off")
  fi

  if [ ${#repo_issues[@]} -eq 0 ]; then
    echo "OK $repo [$branch]"
  else
    echo "DRIFT $repo [$branch]: ${repo_issues[*]}"
    drift=1
  fi
done

exit $drift
