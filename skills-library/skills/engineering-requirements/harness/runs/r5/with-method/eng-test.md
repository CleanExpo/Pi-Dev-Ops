by: eng-test
contributed: [eng-test]
categories:
  test_oracle:   {state: PRESCRIBED, ref: "#zero-test-files-are-collected", by: eng-test, blocking: true}
  invariants:    {state: PRESCRIBED, ref: "#the-two-gates-have-no-executable-assertion", by: eng-test, blocking: true}
  failure_modes: {state: PRESCRIBED, ref: "#two-of-three-classify-branches-have-no-oracle", by: eng-test}
cross_domain:
  - "003_rls_fix.sql is in the repo but not in APPLIED_LEDGER.txt, so prod still runs 002's USING (true) - eng-release owns the ledger drift, eng-authz owns whether the 003 predicate is correct"
  - "drainQueue writes nextAttemptAt but never reads it, so a pending entry is retried on the very next drain with no backoff - eng-concurrency owns the ordering/retry defect itself"
  - "sendEmail swallows every failure and runWatchdog returns alerted:true after a dropped mail, so the alert path can be dead while reporting success - eng-observability owns the detection gap"

## Zero test files are collected

The repository contains exactly one test file, `__tests__/engine.test.ts`, and the vitest config collects neither of the two directories it would need to live in.

[VERIFIED] `vitest.config.ts:4-5` —
> `"lib/**/__tests__/**/*.test.ts",`
> `"app/**/__tests__/**/*.test.ts",`

[VERIFIED] The only test file is at fixture-root `__tests__/engine.test.ts`, not under `lib/` or `app/`. `ls -R` over the fixture returns exactly one `__tests__` directory, at the root, alongside `lib/`, `app/`, `supabase/`, `spec.md` and `vitest.config.ts`.

[VERIFIED] `find . -name "package.json" -o -name "*.yml" -o -name "*.yaml"` over the fixture returns nothing. There is no `test` script, no `vitest` dependency, and no CI workflow, so nothing in the repository invokes a runner at all.

Concrete scenario: an engineer changes `classify` to return `{ category: 1 }` for sewage, runs the suite, and sees no failure — because no test executed. `passWithNoTests` is unset in the config; vitest's default is to exit non-zero on an empty collection, so the first person to see "No test files found" resolves it by adding `--passWithNoTests` to the CI invocation rather than by fixing the glob, and the repository is then permanently green with zero assertions. [INFERENCE] — this is the standard resolution I have seen applied to that exact message, because it makes the red pipeline go away in one flag and the glob mismatch is invisible from the error text.

This directly contradicts `spec.md:15`:
> `- Tests gate the classification engine.`

Nothing gates it.

**Prescribed:**
1. Add `"__tests__/**/*.test.ts"` to `include`, or move the file to `lib/__tests__/engine.test.ts`. Prefer moving the file — one canonical location beats a third glob.
2. Set `passWithNoTests: false` explicitly in `vitest.config.ts` so the empty-collection failure is a stated policy that survives someone adding the flag.
3. Add a package manifest with a `test` script and a CI step that runs it. A test suite no pipeline invokes is documentation.
4. Assert collection, not just passes: the CI step must fail if the collected-file count is zero. A count is the cheapest oracle for "the oracle exists".

[UNCONFIRMED] The exact confirmation is `npx vitest run --reporter=verbose` from the fixture root and reading the collected-file list. I am read-only and did not run it.

Per method 1, the boring fix is the whole fix here: correct the glob and wire a `test` script. My instinct is to demand mutation testing on `classify` as the real oracle; the method wins and that is deferred until the suite executes at all, because mutation scores on a suite that collects nothing are meaningless.

## The two gates have no executable assertion

`spec.md` states two hard gates as prose. Neither exists as anything a test could fail on.

[VERIFIED] `spec.md:8` —
> `- A report may not be distributed unless its verification checklist is complete.`

[VERIFIED] `spec.md:10` —
> `- Tenants must not read each other's reports.`

[VERIFIED] Nothing in the fixture implements or asserts either one. `lib/` contains only `engine.ts`, `notify.ts`, `schema.prisma` and `sync-queue.ts`; `app/api/` contains only `health/route.ts`, which returns a static `status: "ok"`. There is no distribution path and no checklist field, in the Prisma models or in `001_init.sql`, whose columns are `id`, `tenant_id`, `body`, `created_at`.

The tenant gate is the dangerous one, because it is a negative claim. "The cross-tenant query returned no rows" is produced identically by working isolation and by a test that queried the wrong table, authenticated as the wrong role, or ran against a database where the fixture rows were never inserted. Concrete scenario: a test seeds tenant A's report, authenticates as tenant B, selects, gets zero rows, and passes — while it was actually authenticating as `anon`, which `003` revokes and `002` grants. The test passes for the wrong reason and keeps passing after isolation breaks.

**Prescribed:**
1. Every tenant-isolation test carries a **positive control in the same test**: tenant A's own read must return the row before tenant B's read is asserted empty. A test where both reads are empty is a failed test, not a passing one.
2. Add a deliberately-failing control that is asserted to fail: run the same cross-tenant read with RLS bypassed (service role) and assert it *does* return the row. This proves the query and fixture are capable of returning data, which is the only thing that makes the zero-row result mean anything.
3. Isolation tests must run against the same applied-migration state as production. Today `003` is on disk but not in `APPLIED_LEDGER.txt`, so a suite run against a freshly-migrated local database tests a policy production does not have, and passes while production is open. The test asserts the repository, not the system.
4. Express the checklist gate as a database-level assertion (a `CHECK` or a trigger on the distribution transition), not an application-layer `if`. Per method 8, prefer the failure that cannot be committed to the one a code path can route around; an application guard is bypassed by every future writer, including the backfill script nobody has written yet.

eng-authz owns whether the `003` predicate expresses tenancy correctly. My claim is narrower and does not contradict theirs: whatever the predicate says, there is currently no test that could distinguish it working from it being absent.

## Two of three classify branches have no oracle

`classify` has three outcomes; the one test asserts one of them.

[VERIFIED] `lib/engine.ts:2-4` —
> `  if (input.source === "sewage") return { category: 3 };`
> `  if (input.source === "greywater") return { category: 2 };`
> `  return { category: 1 };`

[VERIFIED] `__tests__/engine.test.ts:6` —
> `    expect(classify({ source: "sewage" }).category).toBe(3);`

The specific edit that leaves the suite green: delete line 3 of `engine.ts`. Greywater then falls through to `return { category: 1 }` and every assertion in the repository still holds. The same is true of any change to the fallback. (This is moot until the collection bug above is fixed, at which point it becomes the live gap.)

The fallback is also a silent decision the author may not have noticed making: an unrecognised or absent `source` is classified as category 1, the *lowest* severity, in a system whose output is a report distributed to insurers. A typo'd or newly-added source string downgrades a category 3 contamination to category 1 and the report goes out looking clean. Nothing logs the fallback, so the misclassification travels all the way to the insurer before anyone can notice. [INFERENCE] — the mechanism is a permissive default on an enum-shaped input with no closed set; I have seen it fail exactly where a new upstream value is introduced by a mobile client that ships ahead of the server.

**Prescribed:**
1. One assertion per branch, including the fallback, plus `classify({ source: "" })` and an assertion for a source not in the set.
2. Make the fallback loud rather than silent: either type `source` as a union so an unknown value cannot compile (method 8), or throw/flag on unrecognised input so the default is a decision someone made rather than one the control flow made. Then assert that behaviour.
3. Once the suite executes, run mutation testing on this module specifically. It is five lines and pure — the cheapest possible place to prove the suite has an oracle at all before trusting it anywhere else.
