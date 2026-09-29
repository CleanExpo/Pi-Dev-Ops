by: eng-release
contributed: [eng-release]
categories:
  migration:     {state: PRESCRIBED, ref: "#migration-003-is-committed-but-not-applied", by: eng-release, blocking: true}
  observability: {state: PRESCRIBED, ref: "#nothing-observes-the-deploy-against-the-live-system", by: eng-release, blocking: true}
  failure_modes: {state: PRESCRIBED, ref: "#deploy-ordering-against-003-is-undefined", by: eng-release, blocking: true}
  budget:        {state: N/A, reason: "The release path this change adds is three DDL statements against one table plus a route that does no I/O — there is no metered resource here whose consumption scales with anything.", by: eng-release}
cross_domain:
  - "003 has no down path: line 2 drops 002's policy destructively, so rolling back the code lands on a schema that can no longer serve it — eng-rollback owns the reversal sequence"
  - "vitest.config.ts includes only lib/**/__tests__/** and app/**/__tests__/**, and the sole test file sits at __tests__/engine.test.ts, so the suite that is supposed to gate the engine matches zero files — eng-test owns it"
  - "public.user_tenant_access is read by the RLS predicate but created by no migration in the directory — eng-data owns whether it is a table, a view, or the wrong shape entirely"
  - "no package.json or lockfile exists beside vitest.config.ts, so no CI install step can pin a dependency tree — eng-supply-chain owns it"
  - "RESEND_API_KEY and ALERT_EMAIL each fail open to a console.error and a normal return, so an environment missing either produces output shaped identically to a healthy one — eng-observability owns the detection half"

## Migration 003 is committed but not applied

`003_rls_fix.sql` exists in the migrations directory and is absent from the applied ledger. This is the unconditional dispatch condition for this seat, and it is confirmed by the check rather than asserted.

Positive control first — the check can fail:

```
$ python3 ~/.claude/skills/engineering-requirements/scripts/migration_drift.py self-test
SELF-TEST PASS: the check reports drift, tolerates timestamp-length conventions,
reports out-of-band versions, and fails closed without a database.   # exit 0
```

Then the fixture:

```
$ python3 .../migration_drift.py check --root . --ref worktree \
    --applied-from-file supabase/APPLIED_LEDGER.txt
MIGRATION DRIFT
  1 migration(s) in the repository are NOT applied to the database:
    003_rls_fix.sql                                                   # exit 1
```

[VERIFIED] `supabase/APPLIED_LEDGER.txt:1-2` contains exactly `001` and `002`; there is no third line. [VERIFIED] `supabase/migrations/003_rls_fix.sql` exists on disk.

**Invocation caveat, stated because the evidence depends on it.** Without `--ref worktree` the check reads migrations from a git ref. This fixture path is not tracked in a git tree, so the repo-side set came back empty and the tool reported the drift *inverted* — "2 version(s) applied to the database with no file in the repository: 001, 002". Same exit code, opposite conclusion. Anyone wiring this into CI against an untracked or shallow-cloned path will get a confidently wrong direction. [VERIFIED] — both runs are above.

**What the gap actually means.** The ledger is the deployed truth, so what is live is `002_policies.sql:4`:

> `  FOR SELECT USING (true);`

together with `002_policies.sql:6`:

> `GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated;`

The spec gate at `spec.md:11` reads:

> - Tenants must not read each other's reports.

That gate is currently unmet in the deployed system, and the file that meets it is sitting in the repository looking merged. [VERIFIED] — quotes above. This is method position 4 exactly: a migration started and not finished, leaving two truths and no rule for which wins.

**And 003 cannot apply cleanly as written.** [VERIFIED] `supabase/migrations/003_rls_fix.sql:6`:

> `  USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));`

`grep -rn "user_tenant_access"` across the whole fixture returns that one line and nothing else — no migration creates the table. So `CREATE POLICY` raises `relation "public.user_tenant_access" does not exist`. If the runner wraps the file in a transaction the whole thing rolls back and the drift persists silently for another cycle. If it does not — and Supabase's CLI does not wrap statements that were split across a runner boundary — then `DROP POLICY IF EXISTS` on line 2 has already committed, `REVOKE` on line 8 never runs, and `reports` is left with RLS enabled and zero policies: a total read lockout for every tenant, with `anon` still holding the 002 grants. [INFERENCE] — mechanism is standard Postgres DDL failure inside a partially-transactional migration runner; I have watched this exact shape leave a table unreadable after a "failed" deploy that the pipeline reported as failed-and-retried.

**Prescription.** Do not add a fourth migration on top of a drifted ledger. Create the `user_tenant_access` table in a migration ordered before 003, wrap 003 explicitly in `BEGIN; … COMMIT;` so its failure mode is all-or-nothing rather than half-applied, apply it, and re-run the drift check with `--ref worktree` until it exits 0. Then make that check a required CI step so the next 003 cannot sit unapplied for a release cycle.

## Nothing observes the deploy against the live system

This is the question this seat exists to ask: what single observation, taken against the live system after the deploy, would prove this change is in effect — and does anything in the pipeline make it?

Nothing does, and the one endpoint that looks like it might is actively misleading. [VERIFIED] `app/api/health/route.ts:4`:

> `    version: process.env.NEXT_PUBLIC_APP_VERSION || "1.0.0",`

Two failures in one line. First, the fallback: when `NEXT_PUBLIC_APP_VERSION` is unset — a fresh environment, a renamed secret, a build that missed the var because `NEXT_PUBLIC_*` is inlined at build time and not at runtime — the route returns `"1.0.0"`, a plausible-looking version, and `"status": "ok"`. A deploy that shipped nothing and a deploy that shipped everything return byte-identical bodies. Second, the value is a version string, not a build SHA, so even when it is set it cannot distinguish two deploys of the same version tag, which is precisely the rollback-and-redeploy case where you most need to know which revision is serving traffic.

Nothing in this endpoint touches the database, so it reports `ok` whether or not 003 applied. [VERIFIED] — the route body is seven lines and its only I/O is `new Date()`.

Against `spec.md:14`:

> - Deploy is repeatable and observable.

There is no artifact in the repository that implements the second half. `find` over the fixture returns twelve files: no `.github/`, no workflow, no `vercel.json`, no `Dockerfile`, no `.env.example`, no post-deploy script. [VERIFIED] — full file listing enumerated; the tree is `spec.md`, `vitest.config.ts`, four `lib/*`, one route, three migrations, one ledger, one test.

**Prescription.** Health reports the two facts that distinguish deploys, and fails rather than defaults:

- `build`: the commit SHA, injected at build time, with **no fallback** — if the var is absent the route returns 503. A health endpoint that cannot identify its own build is unhealthy, not fine.
- `schema`: the max version from `supabase_migrations.schema_migrations`, read live on each call.

Then add a post-deploy step that fetches the live URL and asserts `build === $GITHUB_SHA` and `schema === ` the max version in `supabase/migrations/` at that SHA, failing the deploy on mismatch. That is the observation against the running system that the pipeline's own exit code cannot substitute for. Without it a promoted-alias step that silently no-ops is indistinguishable from a successful one.

[UNCONFIRMED] — whether the deployed instance currently serves a real version or the `"1.0.0"` literal. `curl -s "$APP_URL/api/health"` answers it in one call.

## Deploy ordering against 003 is undefined

003 is an ordering-sensitive migration and there is no file in the repository that fixes its order relative to the application deploy. This is a decision made silently: someone will pick an order at deploy time, and the two orders have different, opposite blast radii.

**Migration first, then app.** `003_rls_fix.sql:8`:

> `REVOKE ALL ON public.reports FROM anon;`

The instant this commits, every request still authenticating as `anon` loses all access to `reports` — not degraded, revoked. The currently-deployed code was written against `002_policies.sql:6`, which grants `anon` full DML. Any surface holding an anon session during the window between the migration and the app rollout gets hard errors. [VERIFIED] — both grant and revoke quoted.

**App first, then migration.** New code assumes tenant scoping is enforced by the database while `USING (true)` is still the live policy, so every authenticated caller reads every tenant's reports for the width of the window. [VERIFIED] `002_policies.sql:4` quoted above. This is the direction that breaches `spec.md:11` rather than merely erroring, and it is the direction most pipelines default to because deploying the app is the fast step.

Neither window is bounded by anything, because there is no pipeline artifact defining the steps at all — see the file enumeration in the section above.

**Prescription.** Make 003 expand-then-contract so neither order can hurt. Split it: a first migration that creates `user_tenant_access` and adds the tenant-scoped `SELECT` policy *alongside* the permissive one (both policies present, permissive union means no window of denial); deploy the application; then a second migration that drops `"Anon read access"` and runs the `REVOKE`. Gate the second on the health endpoint reporting the expected build SHA, so the contract step cannot run against code that has not landed. Record the required order in the pipeline file, not in a runbook — method position 11: a fix that lives in someone's memory is not a fix.

[INFERENCE] — expand/contract is the standard remedy for a mid-deploy schema window; the specific hazard here is not inferred, it is the literal semantics of the `REVOKE` and the `USING (true)` predicate quoted above.

---

**Method note.** My domain instinct wanted a fourth finding under `rollback` — 003's destructive `DROP POLICY` with no down path is on this seat's own list of what bites. The contract's three-claim cap and "stay in your lane" win, and eng-rollback owns it; it is handed over in `cross_domain` above with the mechanism rather than dropped.
