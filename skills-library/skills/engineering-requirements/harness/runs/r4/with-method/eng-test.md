by: eng-test
contributed: [eng-test]
categories:
  test_oracle:  {state: PRESCRIBED, ref: "#no-collected-test-suite", by: eng-test, blocking: true}
  invariants:   {state: PRESCRIBED, ref: "#gates-are-prose-not-assertions", by: eng-test, blocking: true}
  failure_modes:{state: PRESCRIBED, ref: "#sync-queue-has-no-runnable-seam", by: eng-test, blocking: true}
cross_domain:
  - "003_rls_fix.sql is absent from APPLIED_LEDGER.txt while 002 granted anon full DML — eng-release owns the ledger gap, eng-authz owns the policy"
  - "drainQueue selects on the status index and never reads nextAttemptAt, so the computed backoff is written but never honoured — eng-concurrency owns the retry semantics"
  - "nothing in the repo reports that the suite collected zero files, so CI green is indistinguishable from CI absent — eng-observability owns the signal"
  - "notify.sendEmail swallows every failure by design, so an alert that never sent looks identical to one that did — eng-observability owns whether that is acceptable"

## No collected test suite

The spec's own completion criterion is a test gate:

> - Tests gate the classification engine.

`[VERIFIED]` `spec.md:15`. Nothing gates it. The runner's include patterns are `[VERIFIED]` `vitest.config.ts:4-5`:

> `"lib/**/__tests__/**/*.test.ts",`
> `"app/**/__tests__/**/*.test.ts",`

The only test file in the repository is `__tests__/engine.test.ts` at the root. `[VERIFIED]` — `find . -name '*.test.ts'` returns exactly that one path, and `find . -path './lib/*/__tests__/*.test.ts' -o -path './app/*/__tests__/*.test.ts'` returns nothing. Neither pattern is anchored anywhere the file lives. There is also no `package.json` and no CI workflow anywhere in the tree, so no `test` script exists and nothing invokes the runner at all.

The second, independent hole is that the one test — even after the glob is fixed — has no oracle for two of three branches. `[VERIFIED]` `lib/engine.ts:2-4`:

> `if (input.source === "sewage") return { category: 3 };`
> `if (input.source === "greywater") return { category: 2 };`
> `return { category: 1 };`

against a single assertion, `[VERIFIED]` `__tests__/engine.test.ts:6`:

> `expect(classify({ source: "sewage" }).category).toBe(3);`

Delete line 3 and `greywater` falls through to `category: 1`; the suite stays green. `[INFERENCE]` — the mechanism is a branch with no assertion, and category is the value that drives the insurer-facing report, so the silent downgrade of a greywater job to category 1 ships behind a passing build.

**Prescribed.** Three things, in this order:

1. Change the include patterns to cover the real layout — `"**/__tests__/**/*.test.ts"` — and add a `package.json` `test` script that CI runs. Set `passWithNoTests: false` explicitly so an empty collection is a red build rather than a quiet one; a runner that can report success on zero files is not a gate.
2. Add a case per branch of `classify`, including the fall-through, plus the unknown-source input, asserting the whole returned object rather than `.category` alone so an added field is visible.
3. Adopt the mutation check as the acceptance test for this work, not a nice-to-have: stub `classify` to `return { category: 1 }` and confirm the suite goes red. `[UNCONFIRMED]` — I am read-only and cannot run it. The exact command a human runs is `npx vitest run` before and after that one-line stub; if both runs are green the gate does not exist regardless of what the config says.

Per method item 6, the recurring version of this comment is a rule, not a correction: the glob-vs-layout mismatch will recur every time a directory moves. The rule is a CI assertion that the collected test-file count is greater than zero, which fails loudly on the next move.

## Gates are prose not assertions

Section 2 states three gates as English:

> - A report may not be distributed unless its verification checklist is complete.
> - Offline capture must survive poor connectivity and retry.
> - Tenants must not read each other's reports.

`[VERIFIED]` `spec.md:7-9`. None is written as something a test could evaluate — no function, no predicate, no fixture. The category asks for an assertion someone could test, and there is not one for any of the three.

The third is the one that bites, and it bites in my speciality rather than eng-authz's. A tenancy test that queries as tenant B and asserts zero rows is exactly the negative result with no positive control: it passes identically when RLS works, when the query names the wrong table, when the fixture inserted nothing, and when the connection was never authenticated as B. The repository makes that concrete — `[VERIFIED]` `supabase/migrations/002_policies.sql:6`:

> `GRANT SELECT, INSERT, UPDATE, DELETE ON public.reports TO anon, authenticated;`

and the ledger records only `001` and `002` as applied, so the fix in `003` is not live. `[INFERENCE]` A zero-row isolation test written today would pass against a database where cross-tenant reads are wide open, because a broken test and a secure database produce byte-identical output.

**Prescribed.** Every isolation assertion carries a positive control in the same test body: seed one row for tenant A and one for tenant B, assert as A that A's row **is** returned (this is the control — if it fails, the harness is broken and the negative half means nothing), then assert B's row is not. Same shape for the checklist gate: assert a complete checklist **does** distribute before asserting an incomplete one does not. For offline capture, the control is that a queued entry drains successfully on a healthy endpoint before any retry assertion is trusted.

Grounded in the failure I have watched most often: the first isolation test anyone writes returns zero rows on day one and is never re-examined, because nobody ever proved it could return non-zero.

## Sync queue has no runnable seam

`drainQueue` calls five collaborators that have no runtime binding. `[VERIFIED]` `lib/sync-queue.ts:54-58`:

> `declare function put(db: IDBDatabase, e: Entry): Promise<void>;`
> `declare function getAll(i: IDBIndex, s: string): Promise<Entry[]>;`
> `declare function markFailed(db: IDBDatabase, id: string): Promise<void>;`
> `declare function removeEntry(db: IDBDatabase, id: string): Promise<void>;`
> `declare function count(db: IDBDatabase, s: string): Promise<number>;`

`declare` emits no JavaScript. `[INFERENCE]` The first call into `drainQueue` reaches `getAll` and throws a `ReferenceError`; the module compiles cleanly and fails only when executed. This is the exact failure class the type system was supposed to catch and cannot, because `declare` is the escape hatch that tells it not to look — method item 8 applies against the code as written.

The test consequence is what puts this in my lane. These are module-scope free functions, not parameters and not imports, so there is no seam: a test cannot inject them, `vi.mock` has no module specifier to intercept, and the only way to make a test pass is to stop calling the real code path. Whatever test gets written here will encode the stub's contract rather than IndexedDB's — the drift my seat exists to catch, and it is invisible until a technician's captured readings fail to sync in the field.

Note also that `getSyncStatus` counts `"conflict"` (`lib/sync-queue.ts:50`) while the `Entry` type admits only `"pending" | "failed"` (`lib/sync-queue.ts:7`) — `[VERIFIED]`. `SYNC_CONFLICT` is therefore unreachable and untestable, and no assertion in the repo would notice.

**Prescribed.** Take the collaborators as an injected dependency object — `drainQueue(db, store)` where `store` is a typed interface — and provide one real IndexedDB-backed implementation plus one in-memory implementation for tests. That gives the module a runtime binding and gives tests a seam that is the same interface production uses, so a shape the real store would reject cannot pass in a test. Then write the drain tests against the in-memory store: success removes the entry, non-ok increments retry, five failures mark failed. Reconcile the `Entry` status union with the states `getSyncStatus` reads before writing an assertion against it, or delete the unreachable branch.

Method item 1 over my own instinct, stated once as required: my instinct is a fake-IndexedDB library, and the boring version — one injected interface with two implementations — is the one to try first and the one this prescription names.
