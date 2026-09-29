by: eng-test
contributed: [eng-test]
categories:
  test_oracle: {state: PRESCRIBED, ref: "#the-suite-matches-zero-test-files", by: eng-test, blocking: true}
cross_domain:
  - "003_rls_fix.sql is in the migrations directory but the ledger records only 001 and 002 — eng-release owns the drift; I only claim that it makes a green test meaningless"
  - "the permissive `FOR SELECT USING (true)` policy from 002 is the live tenant boundary until 003 lands — eng-authz owns whether that is acceptable"
  - "getSyncStatus branches on a `conflict` status that the exported `Entry` type cannot express — eng-contract owns whether the type or the branch is wrong"
  - "spec §2 names three gates but no code in this repo implements the checklist gate at all — eng-contract / eng-failure own the missing implementation"

## The suite matches zero test files

**State: PRESCRIBED — blocking.** Spec §3 says the change is done when "Tests gate the classification engine." Nothing in this repo gates anything, and the failure is not that the tests are weak — it is that they do not run.

### The only test file is excluded by the runner's own config

`vitest.config.ts:3-6` replaces vitest's default `include` with two globs, neither of which the single test file can match:

> `include: [` / `"lib/**/__tests__/**/*.test.ts",` / `"app/**/__tests__/**/*.test.ts",`

The one test lives at `__tests__/engine.test.ts` — repo root, not under `lib/` or `app/`. `[VERIFIED]` `vitest.config.ts:4` quoted above; `__tests__/engine.test.ts:2` reads `import { classify } from "../lib/engine";`, and that `../` is the proof of location: the file sits one directory above `lib/`, so no `lib/**/` prefix can ever reach it. There is no `lib/__tests__/` or `app/**/__tests__/` directory in the tree.

`[UNCONFIRMED]` — whether this currently shows as red or green depends on invocation, and I cannot run it. With zero matched files `vitest run` exits 1 with "No test files found"; with `--passWithNoTests` it exits 0 and prints a green summary. There is no `package.json` and no CI workflow in this fixture, so I cannot tell which is in force, and that ambiguity is itself the finding: nobody can currently state whether the classification gate passed or was skipped. The command that settles it: `npx vitest run --reporter=verbose` from the fixture root, and read the file count, not the exit code.

**Prescription:** the include globs must match the tests that exist (or the test must move to `lib/__tests__/`), and CI must assert a **minimum test-file count**, not just an exit code. A suite that can silently collapse to zero files and still exit 0 is the single most common way a "tests gate X" claim becomes false without anyone editing a test.

### Nobody has proved the suite can fail

This is the cheapest evidence and it has not been taken. `[INFERENCE]` — the mechanism: a negative result (green) from a suite of zero tests is indistinguishable from a negative result from a passing suite. The positive control is one edit:

Change `lib/engine.ts:2` from `return { category: 3 }` to `return { category: 9 }` and run the suite. If it stays green, or reports "no test files", there is no oracle for the classification engine and never was. Until someone has done that and seen red, "tests gate the classification engine" is an assertion, not an observation. I have seen this exact shape ship three times: a config `include` narrowed during a directory reshuffle, the suite quietly emptied, and the gap found months later when a real regression walked through a green build.

### Even wired up, one assertion covers one of three branches

`__tests__/engine.test.ts:6` is the entire suite:

> `expect(classify({ source: "sewage" }).category).toBe(3);`

`classify` has three outcomes. `[VERIFIED]` `lib/engine.ts:3` reads `if (input.source === "greywater") return { category: 2 };` — delete that line and the suite is still green, because greywater falls through to the default and no test observes it. `[VERIFIED]` `lib/engine.ts:4` reads `return { category: 1 };` — change `1` to `7` and the suite is still green. Two surviving mutants out of three branches, in a five-line function, on the one component the spec singles out as needing a test gate.

**Prescription:** one case per branch plus one unknown-source case, and — since this is a *classification* engine whose output category presumably drives remediation scope and billing — a table-driven test whose cases are the same list the domain uses, so adding a source without adding a classification fails the build.

### The two gates the spec calls non-negotiable have no test at all, and one of them cannot be tested honestly without a positive control

Spec §2 states two invariants. `grep -rniE "checklist|verif"` across the fixture returns exactly one hit — `spec.md:8` itself. There is no test, and no code, for "A report may not be distributed unless its verification checklist is complete."

Tenant isolation is the more dangerous one, because the obvious test is the kind that passes while proving nothing:

- **The negative result needs a positive control.** "Queried as tenant B, got 0 rows" is produced identically by working RLS, a typo'd table name, an unauthenticated client, and an empty fixture. The test must first assert that the *same client, same query, same code path* returns N>0 rows for tenant A, then 0 for tenant B. Without the first half it is a test that passes when the database is empty.
- **The fixture database is not the production database.** `[VERIFIED]` `supabase/APPLIED_LEDGER.txt` contains only `001` and `002`, while `supabase/migrations/003_rls_fix.sql:2` reads `DROP POLICY IF EXISTS "Anon read access" ON public.reports;`. A test harness that builds its fixture by applying every file in `migrations/` tests a schema with 003 applied — a schema that, per the ledger, does not exist in the deployed environment, where `002_policies.sql:3-4` (`CREATE POLICY "Anon read access" ... FOR SELECT USING (true)`) is still the live policy. So a green tenant-isolation test would be evidence about the developer's machine and evidence of nothing about the tenant boundary customers are behind. The oracle must bind to the deployed schema: run the isolation assertion as a post-deploy check against the target environment, not only in CI against a freshly-migrated throwaway.

`[INFERENCE]` on the offline-capture gate: `lib/sync-queue.ts` has no test, and the naive one is a no-assertion test. `drainQueue` returns `Promise<void>`; `await drainQueue(db)` resolving proves only that nothing threw, and it resolves identically if the loop body is deleted. A real oracle needs fake timers and a fetch stub, and must assert the *observable state transition* — after five non-ok responses, `retryCount` is 5 and `nextAttemptAt` advanced by the specific backoff values in `RETRY_BACKOFF_MS`; on the sixth drain the entry is `failed`, not retried. Note that `lib/sync-queue.ts:15` indexes `RETRY_BACKOFF_MS[Math.min(entry.retryCount, 4)]` while `MAX_RETRY_COUNT = 5` at line 3 — whether the last backoff is ever used is exactly the kind of off-by-one an assertion on elapsed delay catches and an assertion on "it resolved" does not.
