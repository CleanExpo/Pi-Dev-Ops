by: eng-test
contributed: [eng-test]
categories:
  test_oracle: {state: PRESCRIBED, ref: "#test-oracle-the-suite-does-not-collect-the-only-test-file", by: eng-test, blocking: true}
  invariants:  {state: PRESCRIBED, ref: "#invariants-the-three-gates-are-prose-with-no-executable-assertion", by: eng-test, blocking: true}
cross_domain:
  - "003_rls_fix.sql selects from public.user_tenant_access, which no migration creates — eng-data owns whether that table exists"
  - "the ledger records 001 and 002 while migrations/ holds three files, so the tenant-scoping fix may be unapplied in prod — eng-release owns that"
  - "drainQueue increments retry on !response.ok, so a POST that succeeded server-side but returned 502 is re-POSTed — eng-concurrency owns the idempotency question"
  - "getSyncStatus reads a 'conflict' status that Entry's union does not permit and no writer produces — eng-concurrency owns whether the state is real or dead"
  - "notify.ts swallows every send failure into console.error and returns void — eng-observability owns whether a dropped alert is detectable"

## test oracle — the suite does not collect the only test file

The single test file lives at `__tests__/engine.test.ts`, at the repo root. The config collects
only two globs, both of which require a `lib/` or `app/` ancestor directory above `__tests__`:

`[VERIFIED]` `vitest.config.ts:4-5` — `"lib/**/__tests__/**/*.test.ts",` / `"app/**/__tests__/**/*.test.ts",`
`[VERIFIED]` `find . -name "*.test.ts"` returns exactly one path, `./__tests__/engine.test.ts`, which
matches neither glob because there is no `lib/` or `app/` segment before `__tests__`.

So the number of test cases that execute is zero. This is the concrete scenario: a developer deletes
the body of `classify` and pushes; the classification engine is now unimplemented and nothing in this
repo observes it. `spec.md:16` — "- Tests gate the classification engine." — is not true today; the
gate is open and reports as absent, not as failing.

`[UNCONFIRMED]` whether that surfaces as a red run or a silent pass depends on the invocation, and
this repo does not define one — there is no `package.json` and no CI workflow file (`find . -name
package.json -o -name "*.yml" -o -name "*.yaml"` returns nothing). Vitest's default
`passWithNoTests` is false, so a bare `vitest run` should exit non-zero with "No test files found";
a `--passWithNoTests` flag in whatever pipeline actually calls it converts that into a green build
with no oracle at all. Run `npx vitest run --reporter=verbose` and read the collected-file count
before trusting any green from this repo.

**Prescription.** Fix the glob or move the file, then prove the fix with a positive control: make
`classify` return `{ category: 99 }`, run the suite, and confirm it goes red. A test config change
verified only by a green run is the same null result the broken config already produces.

### the assertion that survives the mutation

Even collected, the one test has an oracle for one of three branches:

`[VERIFIED]` `__tests__/engine.test.ts:6` — `expect(classify({ source: "sewage" }).category).toBe(3);`
`[VERIFIED]` `lib/engine.ts:3` — `if (input.source === "greywater") return { category: 2 };`
`[VERIFIED]` `lib/engine.ts:4` — `return { category: 1 };`

The specific edit that would not fail this test: delete line 3 of `engine.ts`. Greywater then
classifies as category 1 instead of 2, every greywater report downgrades a hazard class on a document
sent to insurers, and the suite stays green. A second surviving edit: change line 4 to
`return { category: 2 }` — unknown sources silently upgrade, still green.

**Prescription.** One case per branch plus one for an unrecognised source, and a case pinning the
category of an empty/undefined `source` — `classify({ source: "" })` currently returns 1 by falling
through, which is a decision nobody wrote down. `[INFERENCE]` Line coverage will read as 100% the
moment the sewage test runs alongside a call that touches the other lines; coverage counts execution,
not verification, so do not use it as the acceptance signal here. If the classification output drives
an insurer-facing hazard category, this is the file to run mutation testing against.

## invariants — the three gates are prose with no executable assertion

`spec.md` states three gates, each phrased as a prohibition, and none has a test that could fail:

`[VERIFIED]` `spec.md:9` — "- A report may not be distributed unless its verification checklist is complete."
`[VERIFIED]` `spec.md:11` — "- Tenants must not read each other's reports."
`[VERIFIED]` `spec.md:10` — "- Offline capture must survive poor connectivity and retry."

`[VERIFIED]` `grep -rn "checklist" .` returns nothing; there is no code implementing the distribution
gate and therefore nothing to test. `[VERIFIED]` `lib/sync-queue.ts` has no accompanying test file
(the `find` above returned one test file in the whole repo), so the retry path in `drainQueue` — five
backoff steps, a `MAX_RETRY_COUNT` cutoff, a catch that increments — has never been exercised by an
assertion.

The tenancy gate is the one that will bite, and it will bite as a *false green*. `[INFERENCE]` The
natural test someone writes for `spec.md:11` is: authenticate as tenant B, `SELECT * FROM reports`,
assert zero rows. That assertion passes identically when (a) the policy is correct, (b) the policy was
never applied because `003_rls_fix.sql` is not in the ledger, (c) the query errors because
`public.user_tenant_access` does not exist and the harness swallows it, and (d) the fixture inserted
no tenant-A rows in the first place. Four states, one green. This is exactly the negative-result-
without-positive-control failure: a passing isolation test is evidence of nothing until the same test
run first proves it can see rows it is allowed to see.

**Prescription — restate each gate as a falsifiable assertion and pair every negative with a positive
control:**

1. *Isolation.* Same test, two assertions in order: as tenant A, `SELECT` returns exactly the N rows
   seeded for tenant A (the positive control — if this is 0, the test is broken, fail it); then as
   tenant B, the same query returns 0. Add a third case asserting the `anon` role gets 0 rows, since
   `002_policies.sql:4` granted `USING (true)` and `003` revokes it — a test that does not distinguish
   those two migration states cannot tell you which one production is running.
2. *Distribution gate.* A test that constructs a report with an incomplete checklist and asserts the
   distribute call *throws or returns a refusal*, not merely that it "does not send" — asserting the
   absence of a side effect on a mock passes when the function body is empty.
3. *Retry.* `drainQueue` with a fetch stub returning 500 asserts `nextAttemptAt` advanced by exactly
   `RETRY_BACKOFF_MS[retryCount]` and that the entry is still `pending`; a sixth pass asserts it
   becomes `failed`. Assert on the persisted entry, not on the stub's call count — call count is an
   assertion about the mock's configuration. `[INFERENCE]` These must drive fake timers rather than
   `sleep`; a `sleep` standing in for the backoff makes the suite order- and load-sensitive and it
   will flake first in CI under parallelism.

These are `blocking` because the repo currently cannot distinguish "the gates hold" from "nothing
checks the gates", and `spec.md:12-16` treats tests as a done-criterion.
