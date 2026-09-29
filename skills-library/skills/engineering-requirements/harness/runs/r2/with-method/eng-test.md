by: eng-test
contributed: [eng-test]
categories:
  test_oracle: {state: PRESCRIBED, ref: "#test-oracle", by: eng-test, blocking: true}
cross_domain:
  - "app/api/health/route.ts returns status:\"ok\" unconditionally — it never reads the DB or the queue, so it is a liveness check that cannot fail; eng-observability owns whether that is the detection surface"
  - "supabase/APPLIED_LEDGER.txt lists 001 and 002 while migrations/ holds 003_rls_fix.sql — eng-release owns the ledger/directory disagreement"
  - "lib/sync-queue.ts:49 branches on a \"conflict\" status that the Entry union at :7 does not permit, so SYNC_CONFLICT is unreachable — eng-contract owns whether the type or the branch is wrong"

## Test oracle

The spec's third done-criterion is `> Tests gate the classification engine.` The gate does not exist. This is not "coverage is thin" — it is that no test process in this repository can select the one test file that was written, and the assertion inside it would survive deleting most of the implementation anyway.

### The configured suite matches zero files

`vitest.config.ts` restricts collection to two directory prefixes [VERIFIED] `vitest.config.ts:4-5`:

```
      "lib/**/__tests__/**/*.test.ts",
      "app/**/__tests__/**/*.test.ts",
```

The only test in the repository sits at the repository root, outside both prefixes [VERIFIED] `__tests__/engine.test.ts:2` — `import { classify } from "../lib/engine";` — and the `../lib` relative import confirms the file is a sibling of `lib/`, not a descendant of it. Neither glob has a branch that reaches a root-level `__tests__/`.

There is also no `package.json` anywhere in the tree, so there is no `test` script and no `vitest` dependency [VERIFIED] `ls package.json` in the fixture root exits 1 with `No such file or directory`; `find . -name "*.test.*"` returns exactly one path.

The failure mode this produces is the dangerous one, not the loud one: `vitest run` with zero matched files exits 0 and prints "No test files found" in most configurations. A CI step that runs the suite and checks the exit code reports green forever, and the green means "nothing ran". Nobody discovers this by watching the pipeline — it is discovered when a classification bug reaches an insurer's report.

**Prescription.** Before this becomes code: add a root glob (or move the test under `lib/__tests__/`), add the `package.json` script and the `vitest` devDependency, and make the CI test step fail on an empty match — `vitest run --passWithNoTests=false` is the flag, and its absence is the reason the empty suite is invisible. Per METHOD 6, the recurring-comment version of this is a rule, not a correction: assert a non-zero collected-test count in CI so "the suite matched nothing" is a red build rather than a green one.

**[UNCONFIRMED]** I am read-only and did not run anything. The command that settles it, once dependencies exist: `npx vitest run --reporter=verbose` from the fixture root, and read the collected-file count, not the exit code.

### The one assertion that exists has no oracle for two of three branches

`classify` has three outcomes; the test pins one. The untested branch is [VERIFIED] `lib/engine.ts:3` — `if (input.source === "greywater") return { category: 2 };` — and the fall-through at `:4` returns `{ category: 1 }`.

The seat question, asked concretely: what edit makes this test fail? Only changing the `sewage` arm. Change `greywater` to return `category: 1`, or delete line 3 entirely so greywater falls through to the default, and the suite is still green. For a tool whose output is distributed to insurers, a silent collapse of category 2 into category 1 is a mis-graded loss, not a cosmetic defect — and the classification engine is the one thing the spec explicitly said tests would gate.

**Prescription.** One case per branch plus one for an unrecognised `source` (which currently returns `category: 1` — a silent default that the test suite should either pin as intended behaviour or reject). Then perform the actual check: stub `classify` to `return { category: 1 }` and confirm the suite goes red. A suite that stays green against that stub has no oracle regardless of how many cases it contains.

### `runWatchdog` returns a success flag that is true when nothing was delivered

`lib/notify.ts` sets the alert flag on the branch, not the outcome [VERIFIED] `lib/notify.ts:27-29`:

```
    await sendEmail({ to, subject: `${problems.length} job(s) unhealthy` });
    alerted = true;
```

`sendEmail` is documented and implemented to swallow everything — it returns early when `RESEND_API_KEY` is unset [VERIFIED] `lib/notify.ts:8` — `console.error("[notify] RESEND_API_KEY unset, dropping mail", payload.subject);` — and catches every throw at `:18`. It returns `Promise<void>` either way.

So `alerted: true` means "`ALERT_EMAIL` was set", not "an alert was sent". Any future test that asserts `expect(result.alerted).toBe(true)` passes identically with the API key missing, Resend returning 500, and the network unreachable. That is the mock-return-value failure in its native form: the assertion target is a variable the code assigns unconditionally, so it verifies the code's bookkeeping rather than its effect. It also fires on `problems.length === 0`, meaning the healthy path attempts a send — a second decision nobody appears to have made.

**Prescription.** Have `sendEmail` return a discriminated result (`{ok: true} | {ok: false, reason}`) and derive `alerted` from it, so the flag is falsifiable and the boundary is checked at compile time rather than in production (METHOD 8). Then the test that matters becomes writable: with the key unset, `alerted` must be `false`. Until the return type carries the outcome, no test of `runWatchdog` can distinguish a working alerting path from a dead one.

**[INFERENCE]** on the consequence, `[VERIFIED]` on the mechanism: the lines above are what I read. I have watched exactly this shape — a boolean set beside a fire-and-forget call — keep a watchdog "green" through a multi-day outage of the notification provider, because the only signal that alerting was broken was the alert that never arrived.

### What I did not find

No test exists for either of the other two spec gates: the checklist-complete precondition on distribution, and the tenant read isolation. `lib/sync-queue.ts` has no test either, and its retry path is the kind that fails on ordering and timing rather than on logic. I am not claiming those categories — `invariants`, `concurrency` and the RLS question belong to seats that own them — but I record here that the phrase "tests gate the classification engine" scopes testing to the one component whose test does not run, and says nothing about the two gates the spec calls non-negotiable in section 2.
