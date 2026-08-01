# Review brief — capabilities 2 & 3, knowledge + wiki-graph — ATTEMPT 3 (FINAL)

You are reviewing a code change. **Flag findings. Do not fix anything. Do not write code.**

This is the **third and last** attempt against a fixed spec. Two prior rounds, both FAIL, both
accepted and fixed:

1. `FAIL — named exemptions are too broad and an unrelated Supabase export is removed.`
2. `FAIL — provenance import map contains a false/dangling WikiEnhanceControl entry and the
   test does not catch stale import judgments.`

**Being the last attempt is not a reason to pass it.** If it still fails, say so and say why —
a FAIL that names a real defect is a better outcome than a PASS that ends the round. Do not
grade on effort or on the fact that prior findings were addressed.

**Judge what is in the diff now, not the history.** Prior findings are summarised only so you
do not spend the round re-deriving them.

## Inputs (these only)

1. This spec
2. The loop (below)
3. The diff: `D:\Pi-Dev-Ops\.harness\cc-02.diff` — read it
4. The tests, both in the diff: `dashboard/__tests__/command-centre-readonly.test.ts`,
   `dashboard/__tests__/command-centre-auth-coverage.test.ts`, and
   `command-centre-provenance.json`

### What changed about the diff itself — read this before judging scope

Attempt 1 correctly flagged that `lib/supabase/server.ts` deletes `createCookieServerClient()`
and that this is unrelated to the capability. It was: that deletion is a separate security
commit that the previous diff range swept in. **The diff is now path-scoped to the capability
surface, and `lib/supabase/server.ts` is deliberately excluded.**

This is disclosed, not hidden. If you think excluding it is itself wrong — that the removal
changes something the capability depends on — say so. `lib/supabase/server.ts` is still
declared `_target_native` in the provenance map and is still in the capability's import graph.

## Spec

Two capabilities ported from `Authority-Site/apps/web` into `Pi-Dev-Ops/dashboard`, shipped as
one unit because knowledge links to wiki-graph.

**Governing instruction: port faithfully, including existing behaviour.** A difference from the
source is a defect whether or not the source's behaviour is ideal.

- **R1. Behaviour matches the source**, except where explicitly declared below.
- **R2. No new network surface** — introduces no network/DB/execution construct the source file
  did not already contain.
- **R3. No npm dependency beyond what the source's closure requires.**
- **R4. Typechecks and builds.**
- **R5. Import paths rewritten for the target's `@/*` → dashboard-root alias.**
- **R6. No new write path, paid-API call, or production-host reach relative to the source.**

**KI-002 — `WikiEnhanceControl` and its route are OMITTED**, founder-ruled, absent not stubbed.
Do not report the omission as a defect. **Do** report a dangling reference or broken control.

## THE NAMED REVIEW ITEM — judge the response to attempt 2 FIRST

Attempt 2's finding was accepted in full and verified by hand: the map declared an import for
`WikiEnhanceControl` that the page does not make, resolving to a file that does not exist.

The response has two halves. **The second is the one to judge hardest.**

1. The dangling entry was deleted. Checking the reverse direction found this was worse than
   reported: **four** phantom entries, not one — the map also carried the entire import closure
   of the non-existent `WikiEnhanceControl.tsx`.
2. Four new assertions make the map checkable against reality: no entry without a real import;
   no real import without an entry; no `resolves_in_target: file: X` where X is absent from
   disk; plus a positive control on the actual-import set so a broken graph walk cannot make
   the first check vacuously green.

The reverse direction also surfaced **three real imports with no map entry at all**, including
`lib/supabase/server.ts :: @supabase/ssr` and `:: @supabase/supabase-js` — the module behind
the service-role client, the most privilege-sensitive file in the graph, previously carrying no
declared judgment. Those files have no source counterpart, so a new judgment value
`no-source-baseline` was added, constrained by a test to files actually declared baseline-free.

**Judge:**
- Do the two directional checks actually close the class, or only the instance? Construct a
  stale-map case that still passes if you can find one.
- `ACTUAL` is built by regex over the import graph. Where does that under-count — dynamic
  imports, re-exports, type-only imports, conditional requires? An under-counting `ACTUAL`
  weakens "no phantom entries" specifically.
- Is `no-source-baseline` a legitimate judgment or a new escape hatch wearing a constraint?
  The constraint is that the importing file must be declared `_rebuilt_not_ported` or
  `_target_native` — **but the same provenance file declares that.** Is that circular?
- Is the positive control on `ACTUAL.size` sufficient, or would a partially-broken graph walk
  still pass it?

## THE PRIOR REVIEW ITEM — attempt 1's findings, for completeness

### (a) The auth exemption, and what proving it uncovered

Attempt 1 said the auth exemption was "at best conditionally correct — the diff only states
'Auth is enforced upstream by proxy.ts', it does not prove that matcher coverage."

Proving it showed the stated reason was **false**. `proxy.ts`'s matcher does cover all
non-static routes, but `proxy()` only checks a session for paths in `PROTECTED_PAGE_PREFIXES` /
`PROTECTED_API_PREFIXES`, and `/command-centre` was in neither. All four command-centre pages
and `/api/command-centre/wiki-graph` served anonymous requests — while reading `wiki_pages`
through a **service-role client that bypasses RLS**.

The response: `command-centre-auth-coverage.test.ts` exercises `proxy()` directly with no
cookie; `/command-centre` and `/api/command-centre` added to the protected prefixes.

**Judge:**
- Does the fix actually close it, for every command-centre surface, or only the tested paths?
- Are the positive controls (`/control`, `/api/pi-ceo`) sufficient to make a green run
  non-vacuous — or could this suite pass while enforcement is broken?
- Does prefix-matching leave a bypass? Consider casing, trailing paths, encoded characters,
  route groups, and anything the `(main)` group rewrites.
- **Is the page-level redirect the right response for a data route, or does it mask a 401?**

### (b) The delta mechanism, now magnitude-scoped

`deltaDeclared(file, rule)` became `deltaDeclared(file, rule, from, to)` and matches the exact
count transition. Declared: `auth gate` 3 → 0, `database client` 1 → 2.

**Judge:**
- Is exact-transition matching actually narrower in practice, or does it just move the problem?
- The `database client` reason claims the count reaches 2 because the regex matches both the
  import specifier and the call site — **one client counted twice**. Verify that against the
  file. If it is wrong, the exemption is hiding a second client.
- Is a count-based conformance check the right instrument here at all?

### (c) The declare-not-fix ruling — KI-003 / KI-004

`WikiGraphCanvas.tsx` is a **byte-identical** port. Attempt 1 flagged its leaked `pointerleave`
listener as a hard standards violation. It is one — **and it is present verbatim in the
baseline**, as is a `react-hooks/refs` error on the tooltip's `sizeRef` read.

Founder ruled: **declare, do not fix.** Fixing here forks the port from its source and makes
the conformance comparison lie. Both are annotated in place, `react-hooks/refs` is suppressed
on the single offending line, both recorded in `.harness/known-issues.md`.

**Judge:** given "port faithfully" is the governing instruction, is declare-not-fix defensible
here? Is the lint suppression scoped tightly enough that a *new* violation in this file still
fails? Say so plainly if you think shipping a known leak is the wrong call — the ruling is
disclosed so you can disagree with it, not so you accept it.

## Loop

```
npx tsc --noEmit                                              -> exit 0
npm run build                                                 -> exit 0
npx vitest run __tests__/command-centre-readonly.test.ts      -> 26 passed (26)
npx vitest run __tests__/command-centre-auth-coverage.test.ts -> 7 passed (7)
scripts/handoff-loop.sh                                       -> pass=7 fail=0 READY
```

**Controls run, all non-vacuous:**
- auth: the suite went **5 failed / 2 controls passing** before the prefix fix, 7/7 after.
- delta magnitude: declaring `3 -> 1` against an actual `3 -> 0` **fails**. It passed under the
  old file+rule keying.
- map-vs-reality: the new checks went **3 failed** on the existing map before the phantom
  entries were removed — they were written red and observed red, not written green.

**On attempt 2's evidence:** the reviewer could not execute the suites (`spawn EPERM` loading
the Vite config in its sandbox) and reviewed statically. If the same happens to you, say so
explicitly in your report rather than implying the loop was independently confirmed. Treat the
numbers above as the author's claim unless you have run them yourself.

## What is deliberately NOT claimed

This spec does **not** claim the pages make no network call. That is an unbounded negative. The
claim is diff-relative: *"introduces no network surface the source did not have."* Judge that.

## Report — two axes, kept separate

### Axis 1 — Standards
TypeScript/React/Next.js App Router practice in the diff. Cite the hunk. Hard violations vs
judgement calls. Skip what the compiler or a linter enforces. Under 400 words.

### Axis 2 — Spec
Against R1–R6 and the named review item: (a) requirements unmet; (b) behaviour not asked for;
(c) requirements implemented incorrectly; (d) whether the response to attempt 1 is sound.
Quote the diff. Under 400 words.

## Verdict

End with exactly one line: `VERDICT: PASS` or `VERDICT: FAIL — <one-line reason>`
