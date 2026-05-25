---
name: unite-group-ci-recovery
description: How to ship PRs cleanly across the Unite-Group portfolio (Synthex, Pi-Dev-Ops, Disaster-Recovery, DR-NRPG, RestoreAssist, ATO, CARSI, CCW-CRM, Unite-Hub, synthex-mcp-app) without falling into the same CI / Vercel / Supabase / convention traps every session. Captures the recurring failure modes I hit 2026-05-25 across PRs #295–#299 so future agents don't relearn them.
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
- Agent ID: claude-opus-4-7-<session-id-prefix>
- Task ID: SYN-975
- Verifier ID: self-verified via /code-review (3 finder angles + 1 verifier per finding)
- Agentic Layer: builder
```

### Other intentional skips you can leave alone

- **`CodeQL`** — skips when no scanned-language files changed; runs on push to main otherwise. Leave it.
- **`Supabase Preview`** — only fires when Supabase preview-branch migration changes are detected. Skipping on a docs PR is correct.
- **`run-quality-checks` / `validate-agent-metadata` / `security-scan` / `update-pr-status`** — fix by adopting branch + metadata convention above. NOT a workflow bug.

## 2 — Vercel sandbox patterns

The Unite-Group org has TWO Vercel projects per repo: `<repo>` (production) and `<repo>-sandbox` (preview/sandbox). Sandboxes have a documented history of brittleness — 5 of them were broken at the start of this session per memory item SBX.

### 2.1 JWT_SECRET required at build time

Synthex's `/api/auth/oauth/github/callback` route reads `process.env.JWT_SECRET` at module init. Next.js's "Collecting page data" phase executes that module, so **`npm run build` will fail without JWT_SECRET set** with:

```
Error: JWT_SECRET must be set in production environment
  ... in app/api/auth/oauth/github/callback/route.ts
```

Fixes:
- **For local builds**: `JWT_SECRET=any-string npm run build` (the value isn't validated, only its presence)
- **For Vercel project**: add `JWT_SECRET` env var via Vercel Dashboard → project → Settings → Environment Variables (Production scope). User added it to `synthex-sandbox` 2026-05-25 — was the JWT_SECRET fix that turned the sandbox green on PRs #296, #297, #299.

If a NEW Vercel project gets created (sandbox spin-up for a new repo), this gap will re-appear.

### 2.2 OOM (exit 137) on sandbox builds

Symptom in Vercel logs:
```
Error: Command "npm run build:vercel" exited with 137
At least one "Out of Memory" ("OOM") event was detected during the build.
```

Cause: sandbox projects use the default build machine size which has less RAM headroom than production. `NODE_OPTIONS=--max-old-space-size=7680 next build --webpack` plus TypeScript checking on the full Synthex codebase can saturate it. Production builds succeed because they use a larger machine.

What to do:
1. If sandbox OOMs and production passed: it's environmental — document in a PR comment + admin-merge if your PR is docs/test only
2. Permanent fix is "Enable Enhanced Builds" in Vercel project settings (UI work, not code). Tracked in [DR-852](https://linear.app/unite-group/issue/DR-852) per memory item SBX.

### 2.3 `vercel pull` skips Sensitive vars

GHA workflows that do `vercel pull && vercel build` will SILENTLY miss env vars marked Sensitive in the Vercel project. The Vercel native git integration handles them fine; the CLI doesn't. Often misdiagnosed as "missing env vars" — actually the workflow architecture is wrong. Per memory `reference_vercel_pull_skips_sensitive`.

### 2.4 `vercel.json` `rootDirectory` is ignored

`rootDirectory` is project-level only — must be set in Vercel UI, never in `vercel.json`. Sandbox projects often inherit a default `rootDirectory` that doesn't match the app subdirectory. Per memory `reference_vercel_rootdirectory_project_level`.

## 3 — Supabase migration playbook

### 3.1 Use the MCP `apply_migration` tool, NOT the CLI for multi-statement files

The Supabase CLI's `supabase db query --linked -f <file>` wraps the file body in JSON for the Management API. **Multi-statement migrations (especially with `DO $$ ... $$` blocks or PL/pgSQL functions) break with:**

```
Failed to run sql query: ERROR: 42601: syntax error at or near "["
LINE 1: [
        ^
```

The `[` is the start of the JSON wrapper hitting Postgres as raw SQL.

**Correct path for multi-statement migrations:**

```typescript
mcp__21d7de5d-7115-4af8-a6c3-2b86769b05fb__apply_migration({
  project_id: "znyjoyjsvjotlzjppzal",  // Synthex; see reference_supabase_project_ids
  name: "add_marketing_agent",          // snake_case, no date prefix
  query: "<full multi-statement SQL>"
})
```

The CLI is fine for one-off inline SELECTs (`supabase db query --linked "SELECT ..."`). Avoid it for `-f <file>` unless the file is a single statement.

### 3.2 Standing Supabase auth (granted 2026-05-25)

The user granted standing authorization for SQL ops on linked projects. Per memory `feedback_standing_supabase_auth`:
- Routine reads, idempotent DDL with `IF NOT EXISTS`, RLS adds: proceed
- Show the SQL inline before applying any non-trivial migration
- Pause for genuinely destructive ops (`DROP TABLE`, `TRUNCATE`, `DELETE` without narrow WHERE)
- Pause for prod writes to customer-owned data

### 3.3 Prereq detection — always check FK targets exist before applying

The 2026-05-25 trap: PR #295's `20260525_add_marketing_agent` had a FK to `marketing_agency_qa_reports`. That table was declared in `prisma/schema.prisma` but **never had a CREATE TABLE in any migration file** (latent gap going back months). Apply failed with:

```
ERROR: 42P01: relation "public.marketing_agency_qa_reports" does not exist
```

**Before applying any migration with FKs to other tables, run a `to_regclass()` check** to confirm targets exist on the target DB:

```sql
SELECT to_regclass('public.<parent_table>')::text AS parent;
```

If null, write a prereq migration that creates the missing table(s) first. See PR #297 for the template (`20260524_add_marketing_agency_core_tables`).

### 3.4 Project ID quick reference

Always verify the project ID matches the repo before any DDL. From memory `reference_supabase_project_ids`:

| Repo | Project ID |
|---|---|
| Pi-CEO / Pi-Dev-Ops | `zbryrmxmgfmslqzizsto` |
| Synthex | `znyjoyjsvjotlzjppzal` |
| Disaster-Recovery | `zwzbglqzmpyfzdkblxyf` |
| RestoreAssist | `oxeiaavuspvpvanzcrjc` |
| Unite-Group | `lksfwktwtmyznckodsau` |
| ATO | `xwqymjisxmtcmaebcehw` |
| DR-NRPG | `lccqasmurmsisnnjqqmr` (separate org `jobkjtecrxliqfnrcssa`) |
| CARSI | `ofzafxvxobjggjisrbsa` (separate org `pmsatfzevrriaylbsifp`) |

`pwwwhoaxxtkmowifpuwf` (NodeJS Starter V1) is NOT a real project — it's where the single-project MCP `c879c796` is bound. Never write to it expecting it to be Pi-CEO. The 2026-05-24 incident applied a migration here by mistake.

## 4 — Admin-merge discipline

Admin-merge is OK **only** when:
1. The failing check has been **proven environmental** with logs (see §2 for sandbox examples)
2. The same check is failing on **main** prior to your PR (proves it's pre-existing)
3. Your PR is **docs / test-only / migration-only** with no production runtime change, OR
4. The user has explicitly said "100% green merged" or "merge it" giving standing consent

Always:
- Post a PR comment documenting the failure analysis BEFORE admin-merging
- Reference the Linear ticket tracking the fix (DR-852 for sandbox env-vars, DR-851 for DR DB direct connection)
- Use `gh pr merge <N> --squash --admin --delete-branch`

Never admin-merge:
- Code changes (even tiny) when a Build / Type Check / Unit Tests check is red — that's your change failing
- When a security scan is red — investigate first
- Without leaving a comment explaining why

## 5 — Migration prereq detection workflow

Before opening a PR that adds a Prisma migration:

```bash
# 1. List existing tables on prod for any new schema you reference
supabase db query --linked "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'marketing_agency_%' ORDER BY table_name;"

# 2. Cross-check vs prisma schema declarations
grep -E "^model MarketingAgency" prisma/schema.prisma | wc -l

# 3. If counts don't match → there's a latent gap; write a prereq migration first
```

## 6 — Skipping checks reference

| Check | Repo where it lives | Why it skips | Fix |
|---|---|---|---|
| `validate-agent-metadata` | Synthex | Branch != `feature/agent-*` | Adopt convention (§1) |
| `run-quality-checks` | Synthex | Branch != `feature/agent-*` | Adopt convention (§1) |
| `security-scan` (lowercase, from agent-pr-checks) | Synthex | Branch != `feature/agent-*` | Adopt convention (§1). The Title-Case `Security Scan` from `security.yml` runs on all PRs — different check |
| `update-pr-status` | Synthex | Branch != `feature/agent-*` | Adopt convention (§1) |
| `Supabase Preview` | Synthex | No supabase/migrations diff for preview branch | Intentional — leave alone unless you're touching `supabase/migrations/*.sql` |
| `CodeQL` | Synthex | Path filter or push-only trigger | Intentional — leave alone |
| `Smoke test (prod)` | Pi-Dev-Ops | Only fires on push to main (not on PRs) | Intentional — leave alone |

## 7 — Standing memories to reference

- [[feedback_standing_supabase_auth]] — SQL ops consent
- [[reference_supabase_project_ids]] — project ID table
- [[reference_dr_db_not_reachable]] — DR prod DB needs direct connection (DR-851)
- [[reference_vercel_rootdirectory_project_level]] — rootDirectory is UI-only
- [[reference_vercel_pull_skips_sensitive]] — sensitive env vars + GHA pitfall
- [[feedback_close_verification_gaps]] — don't surface "should I wait" when you can verify yourself
- [[feedback_act_on_own_recommendations]] — state the rec then execute
- [[feedback_verify_red_checks_before_dismissing]] — prove environmental before calling pass
- [[project_synthex_positioning]] — Synthex = Primary Marketing Agency; agentic features go INSIDE Synthex

## 8 — Worked example: applying this skill to "fix a small bug in Synthex"

1. Open Linear, identify ticket (e.g. SYN-XXX)
2. Cut branch: `git checkout -b feature/agent-syn-xxx-short-desc`
3. Make changes
4. Run pre-flight checklist (§0)
5. Open PR with full metadata block (§1)
6. Watch CI via Monitor poll loop
7. If sandbox fails: check §2 for known patterns, document + admin-merge if environmental
8. If migration fails: §3 (run prereq detection + use MCP not CLI)
9. Once green, squash-merge + delete branch
10. Update Linear ticket to Done + drop comment with the PR URL

## 9 — Verification

This skill is working when:
- No PR opens with a non-`feature/agent-*` prefix
- No PR opens without all 4 metadata fields
- No agent re-runs `supabase db query --linked -f` on a multi-statement migration
- Migration prereq detection happens BEFORE the migration is applied
- Sandbox failures get one-comment-then-admin-merge treatment (not 3 round-trips of "should I?")
