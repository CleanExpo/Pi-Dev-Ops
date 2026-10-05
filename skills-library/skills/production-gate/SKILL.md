---
name: production-gate
description: "Executes the production merge after Phill's explicit approval. Verifies CI, confirms scope, merges to main, triggers deployment, closes mandate. Called when Phill says \"approve PR-[number]\" to Margot. Model: claude-sonnet-5 (production operation — senior tier)"
allowed-tools: Bash, Read
model: claude-sonnet-5
---

# Production Gate — Merge to Main

**Trigger:** Phill McGurk says "approve PR-[number]" or "proceed with [mandate]"

## Pre-merge checklist (automated)

```bash
# 1. Check CI
gh pr checks [PR_NUMBER] --repo CleanExpo/[REPO]
# If failing: STOP. Report. Do not override without explicit "proceed anyway".

# 2. Verify feature branch (safety check)
gh pr view [PR_NUMBER] --repo CleanExpo/[REPO] --json headRefName

# 3. Confirm mandate exists
curl -s "https://lksfwktwtmyznckodsau.supabase.co/rest/v1/board_mandates?pr_number=eq.[PR_NUMBER]" \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY"
```

## Merge
```bash
gh pr merge [PR_NUMBER] --merge --repo CleanExpo/[REPO] --delete-branch
```

## Post-merge (2 min later)
- Update mandate status: 'merged'
- Update Linear: Done
- Check Vercel deployment
- Report: "✅ Live. Mandate closed."
