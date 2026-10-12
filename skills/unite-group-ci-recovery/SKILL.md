---
name: unite-group-ci-recovery
description: "How to ship PRs cleanly across the Unite-Group portfolio (Synthex, Pi-Dev-Ops, Disaster-Recovery, DR-NRPG, RestoreAssist, ATO, CARSI, CCW-CRM, Unite-Hub, synthex-mcp-app) without repeating the same CI, Vercel, Supabase and convention traps (failure modes from PRs 295–299, 2026-05-25). Use when opening a PR against any Unite-Group repo, or when a check shows skipping unexpectedly, a Vercel sandbox build fails or hits OOM exit 137, a Supabase migration will not apply, or a pre-existing red check blocks a PR."
---

# Unite-Group CI Recovery Playbook

## When to use

Always load this BEFORE opening a PR against any Unite-Group repo, and again any time you see:
- A check marked `skipping` that you expected to run
- A `Vercel – *-sandbox` failure
- A Supabase migration that won't apply
- An OOM (exit 137) build failure
- A pre-existing red check on a PR you didn't cause

## 0 — TL;DR pre-flight checklist (run before opening any PR)

| ✓ | Check |
|---|---|
| □ | Branch name starts with `feature/agent-` (NOT `fix/`, `feat/`, `docs/`, `chore/`) — see §1 |
| □ | PR body includes all 4 required fields: `Agent ID:`, `Task ID:`, `Verifier ID:`, `Agentic Layer:` — see §1 |
| □ | If migration: it has been **applied to prod via the Supabase MCP `apply_migration` tool** (NOT the CLI `--linked -f`) and verified before opening the PR — see §3 |
| □ | If migration touches a new table: cross-check that **all FK targets exist on prod** (e.g. via `to_regclass()`) — see §3.3 |
| □ | If schema.prisma touched: `npx prisma format && npx prisma validate && npx prisma generate` all green locally |
| □ | `npm run type-check` clean |
| □ | `npm run build` clean with `JWT_SECRET=<placeholder>` env (required by the OAuth route at build time — see §2.1) |
| □ | Relevant `npx jest` suites pass |
| □ | Linear issue ID referenced in the PR body (or "Resolves SYN-XXX") |

If any box is unchecked, you will hit one of the recurring failures below.

## 1 — Agent PR conventions (THIS IS WHY YOUR CHECKS KEEP SKIPPING)

**Scope:** these conventions apply where `.github/workflows/agent-pr-checks.yml` exists. **Today that's only Synthex.** Pi-Dev-Ops and other Unite-Group repos have their own CI workflow sets (e.g. Pi-Dev-Ops has `Frontend (tsc + eslint + build)`, `Pi CEO API smoke test`, `Python (pytest + ruff)` — no agent-pr-checks gate). Following the convention on a Pi-Dev-Ops PR is harmless but won't unblock different checks there.

**To check per repo:**
```bash
ls .github/workflows/agent-pr-checks.yml 2>/dev/null && echo "agent-pr-checks present" || echo "no agent-pr-checks workflow"
```

When the workflow IS present, it runs 5 jobs (`validate-agent-metadata`, `run-quality-checks`, `security-scan`, `update-pr-status`, the detector itself), **all gated on `if: needs.detect-agent-pr.outputs.is_agent_pr == 'true'`**.

The detector ONLY returns true when:

```yaml
if [[ "${{ github.head_ref }}" == feature/agent-* ]]; then
  echo "is_agent=true"
else
  echo "is_agent=false"
fi
```

**This is intentional configuration**, not a bug. The org wants autonomous-agent PRs to go through an explicit metadata + quality gate. If your branch doesn't match the pattern, ALL those checks return `skipping` and you lose the agent-specific QA coverage.

### Required branch naming

| Branch prefix | Triggers agent-pr-checks? |
|---|:-:|
| `feature/agent-<short-desc>` | ✅ YES |
| `feature/agent-<task-id>-<desc>` | ✅ YES |
| `fix/...`, `feat/...`, `docs/...`, `chore/...` | ❌ NO — all 5 agent-PR jobs skip |

**Use `feature/agent-` for every PR you open from an autonomous session.** For bug-fix PRs include the nature in the description, not the prefix.

### Required PR body fields

`validate-agent-metadata` greps the PR body for these literal strings — all 4 are required or the job fails:

```
Agent ID: <slug or claude session id>
Task ID: <Linear ticket like SYN-975, or internal task id>
Verifier ID: <who reviewed the diff — for solo runs, this is "self-verified via /code-review">
Agentic Layer: <which layer wrote this — "planner", "builder", "verifier", or "ship-it">
```

Append these to every PR body — under `## Agent metadata` works. Example:

```markdown
## Agent metadata
- Agent ID: claude-opus-5-5-<session-id-prefix>
- Task ID: SYN-975
- Verifier ID: self-verified via /code-review (3 finder angles + 1 verifier per finding)
- Agentic Layer: builder
```

### Other intentional skips you can leave alone

- **`CodeQL`** — skips when no scanned-language files changed; runs on push to main otherwise. Leave it.
- **`Supabase Preview`** — only fires when Supabase preview-branch migration changes are detected. Skipping on a docs PR is correct.
- **`run-quality-checks` / `validate-agent-metadata` / `security-scan` / `update-pr-status`** — fix by adopting branch + metadata convention above. NOT a workflow bug.

## 2 — Vercel sandbox patterns

Read references/vercel-sandbox-patterns.md when a Vercel build or sandbox fails (JWT_SECRET at build, OOM exit 137, vercel pull missing Sensitive vars, rootDirectory).

## 3 — Supabase migration playbook

Read references/supabase-migration-playbook.md when applying or debugging a Supabase migration, or needing project IDs and the standing auth grant.

## 4 — Admin-merge discipline

### When admin-merge IS OK

1. The failing check has been **proven environmental** with **actual log evidence**, not by reflex/ticket-citation
2. The same check is failing on **main** prior to your PR (proves it's pre-existing)
3. Your PR is **docs / test-only / migration-only** with no production runtime change, OR
4. The user has explicitly said "100% green merged" or "merge it" giving standing consent

Always:
- Post a PR comment documenting the failure analysis BEFORE admin-merging
- Reference the **correct, specific** Linear ticket — not a vaguely-related one
- Use `gh pr merge <N> --squash --admin --delete-branch`

Never admin-merge:
- Code changes (even tiny) when a Build / Type Check / Unit Tests check is red — that's your change failing
- When a security scan is red — investigate first
- Without leaving a comment explaining why

### PRE-RULE — check branch protection FIRST (added 2026-05-25 after the rule-against-nothing incident)

Before invoking the STOP rule or any admin-merge logic, **check whether the failing status check is actually a hard block**. Many Unite-Group repos have zero required-status-checks configured — failing checks show as a GitHub UI warning ("yellow banner: 1 check failing, merge anyway?") but a plain `gh pr merge --squash` still works.

```bash
gh api repos/<owner>/<repo>/branches/main/protection 2>/dev/null \
  | jq '{required: .required_status_checks.contexts, reviews: .required_pull_request_reviews.required_approving_review_count, enforce_admins: .enforce_admins.enabled}'
```

Also check newer-style rulesets (separate API):
```bash
gh api repos/<owner>/<repo>/rulesets --jq '[.[] | {id, name, enforcement}]'
```

**Interpretation:**
- `required.contexts: []` AND no rulesets enforcing checks → the failing check is **UI noise, not a hard block**. A plain `gh pr merge --squash` will work. Do NOT use `--admin`. Inform the user the check is non-blocking but recommend fixing the underlying cause anyway (file the Linear ticket, but ship the PR).
- `required.contexts: [<check-name>]` → the check IS a hard block. Apply the STOP rule below.
- Rulesets present with `enforcement: "active"` → check the ruleset's contexts; same logic.

**Confirmed today (2026-05-25):**
- Pi-Dev-Ops main: `required.contexts: []`, no rulesets, no enforce_admins → all CI is UI-noise level. The 7-PR admin-merge cycle was theater.
- Synthex main: status not checked in this session — assume hard block until verified per-repo.

The STOP rule below ONLY applies when a hard block exists. When it's UI-noise, surface the failure honestly ("X check is red but doesn't block; recommend fixing via [ticket]") and proceed with normal merge — that's the honest, non-reflexive path.

### STOP rule — chronic-broken-check escalation (added 2026-05-25 after 7-PR admin-merge incident)

**Before admin-merging past any failing check, count consecutive failures of that exact check on that exact project.**

- If the same check has failed on **≥5 consecutive deployments / PRs**, you do NOT admin-merge with "environmental" reasoning. The check is *chronically broken*, not flaking. Doing so trains you (and the user) to ignore signal — the exact pathology this skill was meant to prevent.
- Instead, **propose ONE of**:
  1. **Remove the check from required status checks** on the branch protection rule (GitHub → Settings → Branches → main rule → required checks). Stops the false-block immediately. Re-add when the check is fixed.
  2. **Disable / delete the broken Vercel project** if it's no longer serving a purpose.
  3. **Surface the actual root cause** (not the symptom) and ship the fix.
- Open a Linear ticket *separate from any "we'll get to it" parent ticket* that captures THIS specific failure with logs + a UI-recipe fix. Do not cite a vaguely-related ticket (e.g. "DR-852 documented") if the specific failure mode is different.

**Concrete example from 2026-05-25:**
Pi-Dev-Ops `Vercel – pi-dev-ops-sandbox` failed 20 consecutive deployments (PRs #262–#268). All 7 PRs got admin-merged with "DR-852 documented" comments. The root cause was actually `framework: null` on the Vercel project settings (NOT one of DR-852's 5 sandboxes) — fixable in 2 minutes via Vercel UI. Should have been escalated at PR #262 (first failure). [RA-5261](https://linear.app/unite-group/issue/RA-5261) captures the specific fix; [RA-5262](https://linear.app/unite-group/issue/RA-5262) captures the systemic prevention (nightly CI script to detect framework-drift across all sandboxes).

### How to use this skill agentically (added 2026-05-25)

Read references/agentic-investigator.md when you are about to admin-merge a failing check and should spawn an investigator agent first.

## 5 — Migration prereq detection workflow

Read references/migration-prereq-workflow.md when a migration references tables that may not exist on prod.

## 6 — Skipping checks reference

Read references/skipping-checks-reference.md when a check shows skipping and you need to know whether that is intentional.

## 7 — Standing memories to reference

Read references/standing-memories.md when you need the standing memories this playbook relies on.

## 8 — Worked example: applying this skill to "fix a small bug in Synthex"

Read references/worked-example.md when you want a worked example of applying this playbook to a small Synthex bug fix.

## 9 — Verification

This skill is working when:
- No PR opens with a non-`feature/agent-*` prefix
- No PR opens without all 4 metadata fields
- No agent re-runs `supabase db query --linked -f` on a multi-statement migration
- Migration prereq detection happens BEFORE the migration is applied
- Sandbox failures get one-comment-then-admin-merge treatment (not 3 round-trips of "should I?")
