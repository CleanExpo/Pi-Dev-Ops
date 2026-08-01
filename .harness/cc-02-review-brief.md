# Review brief — capabilities 2 & 3, knowledge + wiki-graph — ATTEMPT 2

You are reviewing a code change. **Flag findings. Do not fix anything. Do not write code.**

Attempt 1 returned `FAIL — named exemptions are too broad and an unrelated Supabase export is
removed.` Both findings were accepted. This attempt is the response to them. **Do not assume
the response is adequate** — the point of this round is to judge whether it is, and whether it
introduced anything new.

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

## THE NAMED REVIEW ITEM — judge the response to attempt 1

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
npx vitest run __tests__/command-centre-readonly.test.ts      -> 22 passed (22)
npx vitest run __tests__/command-centre-auth-coverage.test.ts -> 7 passed (7)
scripts/handoff-loop.sh                                       -> pass=7 fail=0 READY
```

**Controls run, both non-vacuous:**
- auth: the suite went **5 failed / 2 controls passing** before the prefix fix, 7/7 after.
- delta magnitude: declaring `3 -> 1` against an actual `3 -> 0` **fails**. It passed under the
  old file+rule keying.

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
