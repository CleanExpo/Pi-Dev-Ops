by: eng-release
contributed: [eng-release]
categories:
  migration:       {state: PRESCRIBED, ref: "#migration-merged-but-never-applied", by: eng-release, blocking: true}
  failure_modes:   {state: PRESCRIBED, ref: "#003-references-a-table-no-migration-creates", by: eng-release, blocking: true}
  observability:   {state: PRESCRIBED, ref: "#nothing-observes-the-deployed-schema", by: eng-release, blocking: true}
  interface_contract: {state: N/A, reason: "The drift here is between the migration directory and the applied ledger; no route signature, exported type or payload shape changes, so there is no caller to break.", by: eng-release}
  budget:          {state: N/A, reason: "This repo carries no CI config, no scheduled job and no metered external call on the deploy path, so there is no release-side number to hold under a ceiling.", by: eng-release}
cross_domain:
  - "003 has no down migration and its predecessor is a policy you must never restore — eng-rollback owns what the 3am sequence actually is"
  - "the tenant predicate in 003 (auth.uid() against user_tenant_access) may itself be wrong or unindexed — eng-authz owns the policy, eng-performance the plan"
  - "vitest.config.ts includes only lib/**/__tests__/** and app/**/__tests__/**, which does not match __tests__/engine.test.ts at the repo root — the one test that exists is never collected; eng-test owns it"
  - "there is no package.json or lockfile beside vitest.config.ts, so nothing pins what CI would install — eng-supply-chain owns it"

## migration merged but never applied

The repo's migration directory and its applied ledger disagree, and they disagree about the one migration that enforces the spec's tenancy gate.

I ran the bench's drift check, positive control first:

`python3 ~/.claude/skills/engineering-requirements/scripts/migration_drift.py self-test` → `SELF-TEST PASS: the check reports drift, tolerates timestamp-length conventions, reports out-of-band versions, and fails closed without a database.` (exit 0). A drift check that has never failed is indistinguishable from one that cannot fail; this one demonstrably fails. [VERIFIED]

`... check --root <fixture> --applied-from-file supabase/APPLIED_LEDGER.txt --json` → exit **1**, `"missing_from_database": [{"version": "003", "file": "003_rls_fix.sql"}]`, `repo_migration_count: 3`, `applied_count: 2`. [VERIFIED]

The ledger is two lines: `supabase/APPLIED_LEDGER.txt:1-2` — `001` / `002`. [VERIFIED]

That means the policy in force in the database is the one 002 installed, verbatim at `supabase/migrations/002_policies.sql:3-6`:

```
CREATE POLICY "Anon read access" ON public.reports
  FOR SELECT USING (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated;
```

[VERIFIED]

`spec.md:11` states the gate: `- Tenants must not read each other's reports.` [VERIFIED] With 003 unapplied, that sentence is false in the running system and true in the repo. Every reviewer reading `003_rls_fix.sql` will conclude tenancy is fixed; the deployed schema grants unauthenticated `SELECT` across all tenants. This is the exact shape I have been paged for: merged and applied treated as one fact.

**Prescribed:**
1. The deploy pipeline gains an apply-gate that runs the drift check against the target database's ledger before the app image is promoted, and treats **exit 1 and exit 2 alike as a failed deploy**. Exit 2 ("cannot determine") must not be a skip — a check that cannot see the ledger is the state in which drift hides.
2. Ordering is stated explicitly: migrations apply and the check returns 0 *before* traffic moves to the new revision. Today nothing in this repo declares an order, so the order is whatever the pipeline happens to do.
3. The ledger records a checksum per version, not a bare `001`/`002`. A ledger keyed on filename alone cannot tell you that a file was edited after it ran, which is how repo and schema diverge permanently and silently.

**What would overturn this:** a run of the drift check against the real production ledger returning exit 0. I checked against the ledger file committed in this repo; if that file is a stale artifact rather than the source of truth, name the real ledger and re-run. That is the observation, and nothing in the repo currently makes it.

## 003 references a table no migration creates

`supabase/migrations/003_rls_fix.sql:6` — `USING (tenant_id IN (SELECT tenant_id FROM public.user_tenant_access WHERE user_id = auth.uid()));` [VERIFIED]

`grep -rn "user_tenant_access"` across the whole fixture returns exactly that one line. [VERIFIED] No migration creates `public.user_tenant_access`; 001 creates only `public.reports` (`supabase/migrations/001_init.sql:1`). The Prisma schema does not contain it either — `lib/schema.prisma` defines `User`, `Inspection`, `AuditLog` and no tenant-access join table, while carrying `tenantId String` on `Inspection` (`lib/schema.prisma:10`), a second and unreconciled model of tenancy. [VERIFIED]

So 003 does not merely lag the ledger — as written it **cannot apply**. `CREATE POLICY` resolves its `USING` expression at creation time and will error with `relation "public.user_tenant_access" does not exist`.

The failure state is worse than either end state, and this is the part that travels. 003 opens with a destructive statement before the one that fails:

`supabase/migrations/003_rls_fix.sql:2` — `DROP POLICY IF EXISTS "Anon read access" ON public.reports;` [VERIFIED]

If this migration is applied by any runner that does not wrap the file in a single transaction — `psql -f` without `--single-transaction`, a statement-splitting runner, or a retry that resumes mid-file — the `DROP` commits, the `CREATE POLICY` aborts, and `public.reports` is left with RLS enabled (from 002) and **no SELECT policy at all**. Reports become unreadable to every authenticated user: a full read outage on the product's primary object, produced by a migration whose stated purpose was to tighten a policy. [INFERENCE] — mechanism is non-atomic DDL application; I have watched exactly this turn a policy tightening into an outage when the runner split on semicolons.

**Prescribed:**
1. `user_tenant_access` gets a migration of its own that lands and is recorded *before* 003, with the backfill that populates it. A policy that depends on a table nobody created is a half-finished migration with two truths and no rule for which wins.
2. Every migration file is applied inside an explicit transaction, and the pipeline asserts that — `BEGIN;`/`COMMIT;` in the file, or a runner flag that is checked, not assumed. State which, in the repo, so the next author does not have to guess.
3. Reconcile the two tenancy models before 003 lands. `reports.tenant_id` (SQL) and `Inspection.tenantId` (Prisma) are separately declared and separately owned; the RLS predicate reads the first and the application writes the second. eng-data owns which is canonical; I am flagging only that 003 cannot be applied safely until that is answered.

**What would overturn this:** `\dt public.user_tenant_access` on the target database returning a table. If it exists in production but not in version control, the schema was changed out of band and that is a larger finding than this one — say so rather than quietly adding the file.

## nothing observes the deployed schema

The single observation that would prove a deploy is in effect does not exist here, and the endpoint that looks like it provides one actively conceals the failure.

`app/api/health/route.ts:4` — `version: process.env.NEXT_PUBLIC_APP_VERSION || "1.0.0",` [VERIFIED]

The fallback is the defect. If `NEXT_PUBLIC_APP_VERSION` is unset — a fresh environment, a renamed variable, a build that did not receive it, a rollback to a revision predating it — the endpoint returns `"1.0.0"` and reports `status: "ok"`. A container still serving the previous build and a container serving the new one return byte-identical bodies. Any smoke test polling `/api/health` for a healthy response passes against the stale revision. `NEXT_PUBLIC_` also means this is inlined at build time, so it describes the image that was built, never the database that image is talking to. [VERIFIED for the line; [INFERENCE] for the build-time inlining, which is Next.js's documented behaviour for that prefix.]

Nothing anywhere in this repo reports schema state. There is no endpoint, log line, or check that exposes the applied migration version, which is why 003 can sit unapplied indefinitely with every dashboard green. `spec.md:13` asks for exactly this — `- Deploy is repeatable and observable.` [VERIFIED] — and states it as a goal without naming the observation that satisfies it.

**Prescribed:**
1. `/api/health` returns the build SHA from a variable with **no fallback**. Absent or unresolvable ⇒ non-200. A version field that degrades to a plausible literal is worse than no version field, because it converts a detectable failure into a silent one.
2. The same response carries the highest applied migration version, read from the ledger at request time — not from the build. This is the observation that distinguishes "code deployed" from "schema migrated", and it is the one this repo has no way to make.
3. The post-deploy step hits the live URL of the promoted revision and asserts the returned SHA equals the SHA just deployed. Not the pipeline's exit code — a promoted-alias step that silently no-ops looks identical to success from inside the pipeline, and only an assertion made from outside it can tell the difference.
4. An alert fires on drift as a standing condition, not only at deploy time: the check from `#migration-merged-but-never-applied` runs on a schedule against production. Drift that appears between deploys is invisible to a deploy-time-only gate.

**What would overturn this:** show me a post-deploy step, anywhere, that reads a value from the running system and compares it to the commit being deployed. I found none in the repo; there is no `.github/`, no deploy config, and no CI file of any kind (`ls -la` of the fixture root returns only `__tests__`, `app`, `lib`, `spec.md`, `supabase`, `vitest.config.ts`). [VERIFIED]
