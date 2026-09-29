by: eng-test
contributed: [eng-test]
categories:
  test_oracle:   {state: PRESCRIBED, ref: "#no-executable-oracle-for-the-classification-engine", by: eng-test, blocking: true}
  invariants:    {state: PRESCRIBED, ref: "#both-spec-gates-are-prose-with-no-assertion", by: eng-test, blocking: true}
  failure_modes: {state: PRESCRIBED, ref: "#the-watchdog-reports-success-on-a-path-where-nothing-was-sent", by: eng-test}
cross_domain:
  - "003_rls_fix.sql is on disk but absent from supabase/APPLIED_LEDGER.txt, so 002's permissive policy is what is live — eng-release owns the ledger gap, eng-authz owns the policy"
  - "AuditLog cascades from Inspection which cascades from User, so deleting a user destroys the audit trail that would prove what happened — eng-data owns the cascade"
  - "drainQueue holds an IDB read transaction across an awaited fetch, and IndexedDB auto-commits a transaction at the end of the microtask turn — eng-concurrency owns whether the loop's writes are still in scope"
  - "getSyncStatus branches on count(db, \"conflict\") but Entry.status is typed \"pending\" | \"failed\", so nothing can ever write a conflict row and SYNC_CONFLICT is unreachable — eng-contract owns the type/runtime divergence"

## No executable oracle for the classification engine

Spec §3 says the change is done when "Tests gate the classification engine." Nothing gates it. Two independent reasons, and each alone is sufficient.

**The one test file is not inside either include glob.** `vitest.config.ts:4-5` `[VERIFIED]`:

> `"lib/**/__tests__/**/*.test.ts",`
> `"app/**/__tests__/**/*.test.ts",`

The only test in the repo is `__tests__/engine.test.ts` at the repository root — confirmed by `find . -name "*.test.ts"` returning exactly that one path `[VERIFIED]`. A pattern anchored at `lib/` or `app/` cannot match a path whose first segment is `__tests__`, so the configured runner resolves zero files `[INFERENCE]`. Which way that fails is *not* determinable from here: Vitest's `passWithNoTests` defaults to false, so a bare `vitest run` should exit non-zero — but this fixture has no `package.json` and no CI workflow anywhere `[VERIFIED — find over the fixture and its parent returned no package.json, no *.yml, no *.yaml]`, so nothing declares how the suite is invoked. If any wrapper passes `--passWithNoTests` (common, and the usual response to exactly this error), the build is green with zero assertions executed. `[UNCONFIRMED]` — run `npx vitest run --reporter=verbose` from the fixture root and read the file count in the header; a header reading `Test Files 0` is the whole finding.

**Even once it runs, one branch of three is asserted.** `__tests__/engine.test.ts:6` `[VERIFIED]`:

> `expect(classify({ source: "sewage" }).category).toBe(3);`

`lib/engine.ts:3` `[VERIFIED]`:

> `if (input.source === "greywater") return { category: 2 };`

Delete that line and the suite stays green: greywater falls through to the `category: 1` default, and category is what determines the contamination class in a report distributed to insurers. A silent 2→1 downgrade is the highest-consequence edit possible to this file and is the specific edit no existing test detects.

**Prescription** (grounded in the mutation test above, not in a coverage target):
1. Fix the include globs to cover the actual test root, or move the file. Then add a check that fails the build when the resolved test-file count is zero — the failure that just occurred must not be able to recur silently. Per method §6, the finding is the absence of the check, not the glob.
2. Assert all three branches of `classify`, including the fallthrough for an unrecognised `source`. The fallthrough returning `category: 1` is a silent decision — an unknown contaminant currently classifies as the *least* hazardous class, and nothing records that anyone chose that over throwing.
3. Before trusting the suite, stub `classify` to `return { category: 1 }` and confirm the run goes red. A suite that stays green against that stub has no oracle regardless of how many tests it contains.

## Both spec gates are prose with no assertion

Spec §2 states two hard gates:

> - A report may not be distributed unless its verification checklist is complete.
> - Tenants must not read each other's reports.

Neither exists as anything a test could execute. `grep` over the fixture finds no checklist field, no distribution path, and no test touching either concern — the only test is the `classify` one above `[VERIFIED]`. The checklist gate has no column in `001_init.sql`, whose `reports` table is `id`, `tenant_id`, `body`, `created_at` `[VERIFIED]`, so today the invariant cannot even be *stated* against the schema, let alone tested. That is an invariant with no representation, which is the state in which it gets violated without anyone learning it was.

The tenancy gate carries the sharper trap, and it is the one specific to my seat. When someone writes the isolation test, it will assert that a query as tenant B returns zero of tenant A's reports. **Zero rows is the same observation as a broken test.** A misconfigured client, an unauthenticated session, a typo'd table name, and a correctly-enforced policy all return zero rows, and three of those four are green for the wrong reason. This repo makes that concrete: `002_policies.sql` grants `SELECT` to `anon` under `USING (true)` `[VERIFIED]` and `003_rls_fix.sql` is not in `APPLIED_LEDGER.txt`, which lists only `001` and `002` `[VERIFIED]` — so the live database is almost certainly wide open while a test written today could still report green.

**Prescription:** the isolation test must contain a positive control in the same file. Assert first that tenant A's own client *does* return the row (proving the query, the client and the fixture all work), then that tenant B's returns zero. Without the first assertion the second proves nothing. Same rule for the checklist gate: assert the distribute path *succeeds* on a complete checklist before asserting it refuses an incomplete one. Both tests must be run once against the pre-fix state — against `002`'s `USING (true)` the isolation test must go red, and if it does not, the test is measuring nothing.

## The watchdog reports success on a path where nothing was sent

`lib/notify.ts:27-28` `[VERIFIED]`:

> `await sendEmail({ to, subject: \`${problems.length} job(s) unhealthy\` });`
> `alerted = true;`

`sendEmail` is documented at `lib/notify.ts:3` as never throwing `[VERIFIED]`:

> `* Fire-and-forget: reports errors loudly but never throws, so callers do not fail.`

and returns `Promise<void>` on all four paths — missing key, non-2xx, thrown fetch, success `[VERIFIED, lib/notify.ts:4-21]`. So `alerted: true` means "`ALERT_EMAIL` was set", not "an alert was delivered". With `RESEND_API_KEY` unset the function logs to `console.error` and returns, and `runWatchdog` still reports `alerted: true`.

The test-oracle consequence: `expect((await runWatchdog(["job-a"])).alerted).toBe(true)` passes in an environment with no API key, no network, and no mail sent. It is an assertion that cannot fail for the reason it appears to be checking, and it will be written, because it is the obvious test for this function. The failure it is supposed to protect against — nobody hears about unhealthy jobs — is the exact failure it will be green through. This is worse than having no test, because it converts an unmonitored path into a documented-as-monitored one.

**Prescription:** have `sendEmail` return a discriminated result (`{sent: true}` / `{sent: false, reason: "no_api_key" | "non_2xx" | "network"}`) and have `runWatchdog` set `alerted` from it. Per method §8, that makes the difference between "attempted" and "delivered" a type the caller cannot ignore rather than a convention. The test then asserts `reason: "no_api_key"` in the unconfigured case — an assertion that distinguishes the two states, which the current signature makes impossible for any test to do.

**Where the method overruled my instinct:** my instinct was to also claim `observability` for the dropped-alert path, since a watchdog that cannot report its own failure is an observability hole. Method §13 and the contract's lane rule win — `eng-observability` owns it, and I have kept only the half that is about what an assertion can and cannot distinguish.
