---
name: dead-checks
description: Use BEFORE trusting any check, guard, test, gate, verifier or metric that reports success — and before writing a new one. A check that cannot fail is worse than no check, because its green gets quoted as proof. Fires on "passed", "clean", "0 findings", "no matches", "verified", "green", "nothing found", or any decision resting on a check's silence.
updated: 2026-08-18
---

# Dead checks

A dead check is one that **cannot report failure**. It runs, exits 0, prints a tick, and proves nothing.

This is the estate's most expensive recurring defect. Measured 2026-08-18: **30 files** across
mission-control, autopilot-runner, verify-runtime-evidence, verify-deployment, backup-system and
audit-ai-call-sites carry one known dead-check idiom. CARSI's licence guard carried it too and
exited 0 on all input for an unknown period while real violations shipped to production.

## The one rule

**Never trust a pass until you have seen that check fail.**

Before you write "passed", "clean", "verified", "0 findings": break it on purpose, watch it go
red, put it back. If you cannot make it fail, you do not have a check — you have a decoration.

## How to prove a check works

1. Plant a defect the check is supposed to catch.
2. Run it. It must fail, and name the thing you planted.
3. Remove the defect.
4. Run it. It must pass.
5. Only now is step 4's pass evidence.

Do this in an isolated copy when the tree is shared. Never leave a planted defect where another
agent or a build can pick it up.

## Known dead-check patterns

**1. The CLI guard that is always false.**
```js
const isCli = import.meta.url === `file://${process.argv[1]}`;   // DEAD on any path with a space
```
`import.meta.url` percent-encodes. `/Volumes/Storage Unit/…` becomes `/Volumes/Storage%20Unit/…`,
never matches, the whole reporting block is skipped, exit 0 with no output.
Fix: `import.meta.url === pathToFileURL(process.argv[1]).href`.
Sweep: `grep -rln 'file://\${process\.argv\[1\]}' --include="*.mjs" --include="*.js" --include="*.ts" . | grep -v node_modules`

**2. `.pathname` used as a filesystem path.**
`new URL('..', import.meta.url).pathname` returns `/Volumes/Storage%20Unit/…`, which does not
exist. Fails loudly (ENOENT) rather than silently — better, still broken.
Fix: `fileURLToPath(new URL('..', import.meta.url))`.

**3. Scope that excludes where the content actually lives.**
CARSI's licence guards scan repo paths. 56 of 80 live courses exist only in the production
database, so the guards' ceiling was 24 of 80 — 30% — no matter how well written. Three banned
titles sat in the other 70%.
Ask: **where does the thing I am checking actually live?** If the answer is a database, an API,
or a running service, a repo scan cannot see it.

**4. Silent truncation.**
`swarm_review.py` cut a 283,638-char diff to 90,000 with no warning: 30 of 87 files reviewed,
the security file not among them, "0 findings" reported. An over-reporting model returning zero
was the only tell.
Ask: **did the whole input reach the check?** Any budget, cap, limit, `head`, `[:N]` or
`maxdepth` must announce what it dropped.

**5. A search whose pattern cannot match.**
`grep -iE "claude|carsi|nexus"` over output that says `nightshift` returns nothing and looks
like "not running". Verify the pattern matches a known-present string first.

**6. A test that pins the defect.**
CARSI's `course-page-integration.test.tsx` asserted a title ending `"… | CARSI"` — the exact
duplication that was the bug. It passed for as long as the defect existed.
Ask: **would this test fail if the behaviour were correct?**

**7. A network check that passes by reaching nothing.**
Zero items fetched must exit non-zero. "I could not look" must never read as "nothing is wrong".
Every clean run states the count it checked; a clean verdict without a number is worthless.

**8. A rule with no enforcement.**
`GOAL.md` mandates reporting RWR — recurring weekly revenue — every session. Nothing checks it,
so sessions ran for months without it. A documented rule behaves exactly like a dead check.
Ask: **what would fire if this rule were broken?** If the answer is "a human notices", it is dead.

## Writing a new check

- Ship the non-vacuity proof in the same commit. Every rule gets a fires-on-violation test and a
  stays-silent-on-clean test.
- Export the scanning function so the test can drive it without the banned content existing in
  the repo.
- Print what was inspected — counts, file totals, what was skipped.
- Fail closed. Cannot-determine exits non-zero, never 0.

## Red flags in your own output

| You are about to write | Do this first |
|---|---|
| "0 findings" / "no matches" | plant one, watch it appear |
| "all tests pass" | break one, watch it go red |
| "guards green" | name what they scanned, and what they did not |
| "verified" / "confirmed" | name the tool call that proves it |
| "nothing found" from a search | prove the pattern matches something present |
| "the whole X was checked" | compare items-checked against items-total |

## Estate cleanup status

The 30-file sweep for pattern 1 is recorded; those files are unfixed as of 2026-08-18 and include
`backup-system.js`, `audit-ai-call-sites.ts`, `mission-control.mjs`, `verify-runtime-evidence.mjs`,
`verify-deployment.js` and `autopilot-runner/src/index.ts`. Fixing them is foundation work: a
verifier that cannot fail has been reporting success across the estate for an unknown period.
