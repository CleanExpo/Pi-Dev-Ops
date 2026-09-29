by: eng-test
contributed: [eng-test]
categories:
  test_oracle:   {state: PRESCRIBED, ref: "#no-test-actually-runs", by: eng-test, blocking: true}
  invariants:    {state: PRESCRIBED, ref: "#gates-are-prose-not-assertions", by: eng-test, blocking: true}
  failure_modes: {state: PRESCRIBED, ref: "#sync-conflict-is-a-branch-no-test-can-reach", by: eng-test}
cross_domain:
  - "003_rls_fix.sql is absent from APPLIED_LEDGER.txt, so the tenant policy in force is still 002's USING (true) — eng-release owns the ledger drift, eng-authz owns the policy"
  - "notify.ts swallows every send failure into console.error and returns void, so a caller can never learn mail was dropped — eng-observability owns whether that is the right contract"
  - "drainQueue's storage collaborators (put/getAll/markFailed/removeEntry/count) are ambient `declare function` stubs with no implementation anywhere in the repo — eng-contract owns whether that module is real"

## No test actually runs

The spec's third done-condition is:

> - Tests gate the classification engine.

Nothing gates it. The one test file in the repo is at the repository root:

`__tests__/engine.test.ts:5` — `it("returns category 3 for sewage", () => {` [VERIFIED]

The runner is configured to look in two places, neither of which is the repository root:

`vitest.config.ts:4` — `"lib/**/__tests__/**/*.test.ts",` [VERIFIED]
`vitest.config.ts:5` — `"app/**/__tests__/**/*.test.ts",` [VERIFIED]

Both globs require a `lib/` or `app/` path segment before `__tests__`. The file sits at `__tests__/engine.test.ts` with no parent segment at all — I listed the tree and it is the only test file in the repo (`find . -name "*.test.*"` returns exactly one path). Collection is therefore empty. [VERIFIED]

Whether that empty collection reads as red or green I cannot tell from here, and that ambiguity is itself the finding: there is no `package.json` in the fixture, so there is no recorded test invocation and no CI step to read. Vitest's default on zero collected files is a non-zero exit, but `--passWithNoTests` is a single flag that many pipelines carry precisely to stop that noise, and under it this repo reports success having verified nothing. [UNCONFIRMED] — run `npx vitest run --reporter=verbose` from the fixture root and read the collected-file count; the number that matters is files collected, not tests passed.

This is the exact shape my seat exists to catch: a done-condition satisfied by a file existing rather than by an assertion executing. The prescription:

1. Fix the glob or move the file, and prove the fix with a positive control — make `classify` return `{ category: 1 }` unconditionally and confirm the suite goes **red**. A green run after that edit means the oracle is still absent no matter what the config says.
2. Never allow `passWithNoTests` in the gating invocation. Assert a floor instead: the run must collect at least one file, and CI should fail on zero.

Second-order, once it does run: the single assertion covers one of three branches. `lib/engine.ts:3` — `if (input.source === "greywater") return { category: 2 };` [VERIFIED] and the fallthrough `return { category: 1 };` at line 4 can both be deleted, or their values transposed, and the suite stays green. For a function whose output drives insurer-facing categorisation, the table needs one case per branch plus an unknown-source case that pins the default — today the default is a silent decision (any unrecognised string becomes category 1) that no test records as intentional. [INFERENCE]

## Gates are prose, not assertions

Section 2 states three gates. Grounded as English, none is currently expressible as something a test can fail on.

> - A report may not be distributed unless its verification checklist is complete.

There is no checklist anywhere in the repo to be complete. `lib/schema.prisma` models `User`, `Inspection` and `AuditLog` and carries no checklist, no completeness flag, and no distribution state; `supabase/migrations/001_init.sql` creates `public.reports` with `id, tenant_id, body, created_at` and nothing else. [VERIFIED] So the gate cannot be violated in a test because the concept it guards does not exist yet — which means when it is built, it will be built without the test that defines it.

> - Tenants must not read each other's reports.

This one carries the more dangerous failure: a naive test of it passes against a broken system. The obvious test — authenticate, read reports, assert you got your own — returns your own rows correctly under `002_policies.sql`'s `FOR SELECT USING (true)` as well as under the fixed policy, because your own rows are a subset of all rows. [VERIFIED, `supabase/migrations/002_policies.sql`] A test that cannot distinguish the two states is not evidence of isolation.

Prescribe, before either gate is called done:

- **Isolation:** a two-tenant fixture. Seed tenant A and tenant B, authenticate as A, assert the count of B's rows returned is zero **and** that A's own rows are returned non-empty. The second half is the positive control — without it, a query against a typo'd table name returns zero B rows and looks like a pass. Then prove the test is real by running it against the `002` policy and confirming it fails.
- **Distribution:** an assertion phrased as the negation — `distribute()` on a report with an incomplete checklist raises and writes no distribution row — not "distribute works when the checklist is complete". The happy path passes if the check is deleted; the negation does not.
- **Offline retry:** `lib/sync-queue.ts:28` — `if (entry.retryCount >= MAX_RETRY_COUNT) {` and the backoff index at line 15 — `RETRY_BACKOFF_MS[Math.min(entry.retryCount, 4)]` [VERIFIED]. The boundary worth pinning is retryCount 4 → 5: the last attempt must be made and the entry must then be marked failed rather than dropped or retried forever. Write it against a fake clock, not a `sleep`; a `sleep` long enough to pass on your laptop is a flake on a loaded CI runner.

## Sync conflict is a branch no test can reach

`lib/sync-queue.ts` reports a conflict state that nothing can ever produce:

`lib/sync-queue.ts:48` — `const conflictCount = await count(db, "conflict");` [VERIFIED]
`lib/sync-queue.ts:49` — `if (conflictCount > 0) return "SYNC_CONFLICT";` [VERIFIED]

The entry type admits only two statuses:

`lib/sync-queue.ts:7` — `status: "pending" | "failed";` [VERIFIED]

`grep -rn "conflict"` across the fixture returns only those two lines — no writer ever sets `"conflict"`, and the type would reject one that tried. [VERIFIED] So `conflictCount` is structurally always 0, `SYNC_CONFLICT` is dead, and a technician whose capture genuinely conflicts server-side is shown `SYNCED` or `PENDING_SYNC` and keeps working on stale state. The damage travels until an insurer receives a report built from the losing side of a conflict, which is not a signal that comes back quickly.

I claim `failure_modes` here from the test-oracle angle and note that eng-failure may reach the same category by another route — the chair should merge rather than pick.

The test-side prescription is that this is exactly the class of bug a mocked-storage test hides: mock `count` to return 1 for `"conflict"` and `getSyncStatus` returns `SYNC_CONFLICT` beautifully, proving only that the mock was configured. The test that has an oracle drives the real store — write an entry through the same path production uses, then assert the status. If no such path can be written because `count` and `put` are ambient `declare` stubs with no implementation, that is the answer to whether this module is testable today, and it is no. [INFERENCE — the drift between a permissive mock and a real client is invisible until the first production conflict, which is the first time anyone finds out the branch never fired.]
