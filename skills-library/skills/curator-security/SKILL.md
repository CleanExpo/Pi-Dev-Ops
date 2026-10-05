---
name: curator-security
description: "Prevents the three recurring security failures distilled from portfolio incidents across dr-nrpg, synthex, ccw-crm, and Pi-Dev-Ops: (1) secrets exposed in tracked docs/runbooks/scripts, (2) environment variable misreads in Vercel Next.js API routes causing silent auth failures, and (3) CI breakage when hardcoded fallback secrets are removed without pre-validating the env is populated. Run this gate before any PR that touches .env files, API route handlers, secret references, or CI/CD configuration."
owner_role: security-reviewer
status: active
---

# curator-security — Portfolio Security Gate

## Why this exists

Three lessons with real production impact were recorded between 2026-04-10
and 2026-04-16 for the "unknown" repo grouping (portfolio-wide scope):

1. Pi-SEO scan found 6 exposed API keys inside docs/, runbooks/, and
   scripts/ across dr-nrpg, synthex, and ccw-crm. The keys were live and
   rotatable — not stale. No prior gate caught them because detect-secrets
   was not wired into CI for those repos at the time.

2. Next.js API routes on Vercel read `process.env.ANTHROPIC_API_KEY`
   directly. Vercel injects env vars with a trailing newline. An untrimmed
   key causes HTTP 401 on every call — silently, because the SDK surfaces
   no hint about the whitespace. The fix is one `.trim()` call and costs
   nothing.

3. Removing a hardcoded fallback secret from code (e.g. a default
   `ADMIN_JWT_SECRET`) without first confirming the real env var is set in
   every deployment target causes CI to turn red and blocks the sprint.

## When to use

- Any PR that adds, edits, or removes references to secrets, API keys, or
  JWT configuration.
- Any PR touching a Next.js API route that reads `process.env.*`.
- Any PR that removes a hardcoded default value for a secret.
- Any time `detect-secrets` has not been run in the current CI pipeline for
  a portfolio repo.
- After a new runbook, doc, or script is added to a repo.

## When NOT to use

- Pure frontend PRs that touch no server-side env reading or secret config.
- Documentation-only PRs where no code or scripts are changed.
- Repos already gated by a stricter security scanner in CI (confirm first).

## Pipeline

Run these steps in order. Stop and file a blocking Linear ticket on first
failure — do not proceed to the next step.

### Step 1 — Secret scan

```bash
pip install detect-secrets --quiet
detect-secrets scan --all-files \
  --exclude-files '\.git/.*' \
  --exclude-files 'node_modules/.*' \
  > .secrets.baseline
detect-secrets audit .secrets.baseline
```

If any NEW finding is not marked as a false-positive in the baseline, the
PR is blocked. Rotate the leaked credential before re-running.

For each finding in docs/, runbooks/, or scripts/:
- Remove the value from the tracked file.
- Replace with a redacted placeholder: `[REDACTED — see 1Password vault]`.
- Add the real value to 1Password and reference it via `op://vault/item/field`.
- Commit the rotation and the updated `.secrets.baseline` together.

### Step 2 — Env var read safety in Next.js routes

For every file matching `app/api/**/*.ts` or `pages/api/**/*.ts`, check
for direct env reads:

```bash
grep -rn "process\.env\." app/api pages/api 2>/dev/null | \
  grep -v "\.trim()"
```

Each hit is a candidate for silent failure on Vercel. For each hit,
confirm one of the following is true before marking safe:

a) The value is read only for boolean checks (no HTTP request downstream).
b) A `.trim()` call is present on the same expression.
c) A shared `makeClient()` wrapper already applies `.trim()` centrally.

If none apply, add `.trim()` to the read site. Example pattern:

```typescript
const apiKey = (process.env.ANTHROPIC_API_KEY ?? "").trim();
if (!apiKey) throw new Error("ANTHROPIC_API_KEY not set");
```

Do not add `.trim()` to values that are passed to libraries expecting exact
binary strings (e.g., raw buffer keys). Confirm the library contract first.

### Step 3 — Hardcoded fallback removal safety check

When a PR removes a default value from a secret-bearing env var, run this
checklist before merging:

```
[ ] Confirm the env var is set in Railway production (Railway dashboard or
    `railway variables list`).
[ ] Confirm the env var is set in Vercel production
    (`vercel env ls --environment=production`).
[ ] Confirm the env var is set in GitHub Actions secrets if CI uses it
    (`gh secret list`).
[ ] Run `npm run build` (or `npx tsc --noEmit`) locally with the var unset
    to confirm the build fails fast with a clear error, not silently.
[ ] Confirm the CI job that uses the secret has the correct secret name
    mapped in the workflow yaml (exact case match).
```

If any box is unchecked, set the var in the missing target before merging.
A missing secret discovered post-deploy requires a hotfix; this checklist
costs 5 minutes.

### Step 4 — Post-scan report

Emit a short report to the PR body or Linear ticket:

```
Security gate: curator-security
Scanned: <date>
Secrets found: <N> (N new / M whitelisted)
Env var trim issues: <N>
Fallback removal checklist: PASS / BLOCKED on <item>
Overall: PASS / BLOCKED
```

## Agent tool-surface review checks

When a PR configures an agent's tool permissions — bash allow/deny lists,
PreToolUse hooks, `permission_mode`, MCP tool sets — apply these checks,
distilled from live whitelist-defeat demos:

- **Arbitrary-code escape hatches:** one whitelisted command that can run code
  defeats the whole list. `npm test` executed an arbitrary script via a temp
  package.json, deleted the evidence, and omitted the exploit from its summary.
  Vet every allowed command (`npm run`, python, node, bun, any interpreter)
  against "can this execute code the operator didn't write?"
- **Non-bash destructive primitives:** the Write tool truncated a protected
  file to zero bytes without touching bash. Auditing bash alone is not auditing
  the destructive surface — enumerate every tool that can mutate state.
- **Reversibility axis:** classify each reachable action as reversible (file
  writes under git — recoverable) or irreversible (cloud resource deletes, prod
  migrations, credential revocation). The gate's job is to drive irreversible
  reach to zero, not to prevent every mistake.
- **Prod-CLI reach:** no allowed command may be a CLI with production-asset
  access (gcloud, aws, vercel, railway, supabase) unless a human gate sits in
  front of it.

[[delete-bash-tool-agentic-security-indydevdan-2026-07-14-ingest]]

## Verification

After the gate runs, confirm the following before marking the ticket done:

1. `detect-secrets scan` exits 0 with no unreviewed findings.
2. `grep -rn "process\.env\." app/api pages/api | grep -v "\.trim()"` is
   empty or every remaining hit is documented as safe in the PR body.
3. Railway, Vercel, and GitHub Actions each show the expected secret set.
4. CI is green (`gh pr checks <PR_NUMBER> --watch`).
5. If a credential was rotated: confirm the old value is revoked at the
   provider (Anthropic console, GitHub PAT settings, etc.).
