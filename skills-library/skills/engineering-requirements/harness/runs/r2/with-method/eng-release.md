by: eng-release
contributed: [eng-release]
categories:
  migration:     {state: PRESCRIBED, ref: "#migration-never-applied",   by: eng-release, blocking: true}
  observability: {state: PRESCRIBED, ref: "#no-post-deploy-observation", by: eng-release, blocking: true}
  rollback:      {state: PRESCRIBED, ref: "#no-down-path-for-003",       by: eng-release, blocking: true}
cross_domain:
  - "vitest's include globs do not match __tests__/engine.test.ts at the repo root, so the suite runs zero tests and still exits green — eng-test owns the oracle"
  - "because 003 is unapplied, the live policy is 002's USING (true) plus a DELETE grant to anon; whether that predicate is right is eng-authz's call, I only assert it is what is running"
  - "runWatchdog returns {alerted:false} and no error when ALERT_EMAIL is unset, so the alert path fails silently — eng-observability owns detection of the detector"

## Migration never applied

`003_rls_fix.sql` is in the repository and is not in the applied ledger. This is the seeded case my seat exists for: "merged" and "applied" are two separate facts, and only one of them has happened.

- `[VERIFIED]` `supabase/APPLIED_LEDGER.txt:1-2` records exactly `001` and `002` — the file's entire contents are the two lines `001` and `002`.
- `[VERIFIED]` `supabase/migrations/003_rls_fix.sql:1` — `-- Tenant-scoped replacement for the permissive policy in 002.` The file exists on disk; nothing records it as run.
- `[VERIFIED]` drift check, exit 1: `python3 ~/.claude/skills/engineering-requirements/scripts/migration_drift.py check --root <fixture> --ref worktree --applied-from-file <fixture>/supabase/APPLIED_LEDGER.txt` → `1 migration(s) in the repository are NOT applied to the database: 003_rls_fix.sql`. Positive control run first: `self-test` → `SELF-TEST PASS: the check reports drift...`, so the exit 1 is a real failure and not a check that cannot fail.
- Note on tool defaults: the same check with its default `--ref origin/main` reported the *inverse* (001 and 002 "applied out of band") because this fixture path is not on `origin/main`. Anyone wiring this into CI must pin `--ref` to the ref that is actually deployed, or the check will report drift in the wrong direction and be dismissed as noise.

The concrete consequence, with state and timing: right now, in the running database, `[VERIFIED]` `supabase/migrations/002_policies.sql:4` — `  FOR SELECT USING (true);` and `002_policies.sql:6` — `GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated;`. Any holder of the anon key can read and delete every tenant's report. The repository reads as if that was fixed in February; the database has never seen the fix. `spec.md:11` — `- Tenants must not read each other's reports.` is a gate the code satisfies and the deployment does not.

**Prescription.** Grounded in the failure the drift script was written from (a correct security migration committed and unapplied for five and a half months):

1. Apply `003` as a discrete, observed step — not as a side effect of the next deploy — and record the ledger row. Do not author `004` on top of a drifted ledger.
2. Make the drift check a required CI gate on every PR touching `supabase/migrations/**`, pinned to the deployed ref, and a scheduled run against production. Treat exit 2 (`CANNOT DETERMINE`) as red. It already prints its own reasoning: a check that cannot reach the database and reports "skipped" is the fail-open it exists to catch. Per method §6, the finding here is not the missing row — it is the absence of the check, so the rule is what gets prescribed.
3. Store a checksum per migration, not a filename. A ledger keyed on `003` alone cannot tell you the file was edited after it ran.

`[UNCONFIRMED]` I cannot see the pipeline that would run any of this. A `find` over the fixture at depth 3 for `*.yml`, `*.yaml`, `.env*`, `Dockerfile*`, `package.json` and `*.toml` returned nothing; the tree is `spec.md`, `vitest.config.ts`, `__tests__/`, `app/`, `lib/`, `supabase/`. Either the fixture is an excerpt or `spec.md:13` — `- Deploy is repeatable and observable.` has no mechanism behind it at all. The human check is `ls .github/workflows/ && cat package.json` in the real repository; if that is empty, this finding is upgraded from "the gate is missing" to "there is no pipeline to gate".

## No post-deploy observation

The question my seat asks: what single observation, taken against the live system after the deploy, would prove this change is in effect — and does anything in the pipeline make it? Here the answer is that the one endpoint that could make that observation is built so that it cannot fail.

`[VERIFIED]` `app/api/health/route.ts:4` — `    version: process.env.NEXT_PUBLIC_APP_VERSION || "1.0.0",`

The `|| "1.0.0"` fallback is the whole finding. Concrete scenario: the env var is never set in the deploy target (it is not set anywhere I can find in this tree). A smoke test hits `/api/health`, gets `{"status":"ok","version":"1.0.0"}`, and passes. It returns exactly the same body if the deploy silently no-opped, if a promoted alias still points at last week's revision, or if the container is serving the previous build. A fresh deploy and a stale one are byte-identical at the only endpoint anyone checks. `status: "ok"` is a literal — it is not derived from anything, so it cannot ever be `"degraded"`.

Nothing in the health payload reports schema state either, which is why `003` could sit unapplied indefinitely with every check green.

**Prescription** (grounded in "verify by observing the running system, not by the pipeline's exit code"):

- Drop the fallback. Read the build SHA from an env var injected at build time and fail the route (500, or `status: "unknown"`) when it is absent. An unset version is a deploy defect, and a default converts that defect into a passing check.
- Add the applied-migration tail to the payload — the max `version` from the ledger — so one `curl` compares running code against running schema.
- Make the post-deploy step assert `health.version === $DEPLOYED_SHA` against the live URL and fail the deploy when it does not match. Until something compares the returned SHA to the one just built, the deploy is verified by its own exit code.

## No down path for 003

`003` is a one-way door and there is no reverse file for it.

- `[VERIFIED]` `supabase/migrations/003_rls_fix.sql:2` — `DROP POLICY IF EXISTS "Anon read access" ON public.reports;`
- `[VERIFIED]` `supabase/migrations/003_rls_fix.sql:7` — `REVOKE ALL ON public.reports FROM anon;`

The 3am scenario, with ordering: `003` is applied, then the release is found bad and the code is rolled back. Rolling back code does not restore a dropped policy or a revoked grant — the schema no longer serves the version you just rolled back to. Any request path still using the anon key starts failing on the *migration's* timing, not the deploy's, and the two steps are independent, so the failure window is however long sits between them.

The reverse case is worse and is the one to plan for: `003` also depends on `public.user_tenant_access`, referenced at `003_rls_fix.sql:6` — `  USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));`. `[VERIFIED]` no migration in this directory creates that table: `001_init.sql` creates only `public.reports` (`001_init.sql:1` — `CREATE TABLE public.reports (`), and `002` creates no tables. If `user_tenant_access` does not exist in the target database, applying `003` fails partway — after the `DROP POLICY` on line 2, because there is no explicit transaction wrapper — leaving `reports` with RLS enabled, the old permissive policy gone, and the new policy never created. That state serves nothing to anyone and has no recorded ledger row to roll forward or back from.

**Prescription:**

1. Wrap `003` in `BEGIN; ... COMMIT;` so a mid-file failure cannot leave the table policy-less.
2. Verify `public.user_tenant_access` exists in the target before applying, or create it in an earlier migration. `[UNCONFIRMED]` from here — the human check is `\d public.user_tenant_access` against the target database.
3. Write the down file: recreate the prior policy and grants explicitly. If the team's position is that restoring `USING (true)` must never happen, say that in the migration as a comment and make the rollback plan "roll forward" — but say it, because "roll back the code" is currently the implicit plan and it does not work here.

`eng-rollback` may answer this category as well; I am not overwriting them. If we differ, the chair should take my line only on the transaction wrapper and the missing `user_tenant_access` dependency, which are specific to how this migration file is written.

**What would overturn all three findings** (method §2): a ledger row for `003` in the production database with a checksum matching the file, plus one post-deploy `curl` transcript showing a build SHA that changes between releases. Either of those, and the corresponding finding is dead.
