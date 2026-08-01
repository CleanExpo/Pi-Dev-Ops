# Review brief — capabilities 2 & 3, knowledge + wiki-graph — ATTEMPT 4

You are reviewing a code change. **Flag findings. Do not fix anything. Do not write code.**

Three prior rounds, all FAIL, all findings accepted and fixed:

1. `FAIL — named exemptions are too broad and an unrelated Supabase export is removed.`
2. `FAIL — provenance import map contains a false/dangling WikiEnhanceControl entry and the test
   does not catch stale import judgments.`
3. `FAIL — the import-map reality check omits the fetched API route, so route imports can enter
   the capability surface without any provenance judgment.`

The standing bound is three attempts. This fourth was granted by the founder as a **per-instance
release valve, explicitly not precedent** — and not because the reviewer is "converging". It was
granted because all three findings were holes in the **evidence apparatus** rather than code
failing a spec, which is the inverse of the case the bound was written for.

**This is the last attempt under any circumstances.** A fifth will not be granted; if the
apparatus is still wrong, the ruling is to re-spec it rather than patch again.

---

## THE PRIMARY QUESTION — answer this first and at length

Every finding across three rounds has been the **same class: coverage that reads wider than it
actually is.**

- an exemption keyed on file+rule, so it excused any magnitude of loss forever
- a provenance map validated only against itself, so a phantom entry read as coverage
- an import graph seeded only from `page.tsx`, so an entire API route's imports were outside it
- a route-existence check scanning only string literals, blind to a template literal in
  `router.push()` — every graph node click 404'd

Each was fixed. **The question is whether fixing them amounts to a design.**

**Is this apparatus architecturally sound, or is it being patched reactively, one reviewer
finding at a time?**

Be concrete. Consider at minimum:

- Is there a coherent principle behind what it checks, or is the check-set simply the union of
  four rounds of reviewer findings? If there is a principle, state it back — and say whether the
  implementation actually follows it.
- **What class of divergence can still pass?** Not "what did I miss" — what does the *design*
  structurally fail to see. Regex-based construct counting, filesystem-reachability graphs, and
  count-non-increase comparisons each have inherent blind spots. Name them.
- Every one of these holes was found by a reviewer, never by the harness itself. Is there
  anything in the design that would surface the *next* one without a reviewer?
- The suite asserts things about its own honesty (positive controls, fail-closed on a missing
  baseline). Are those load-bearing or decorative?

**If your answer is that this is still reactive patching, say so and say what a sound design
would look like instead.** That verdict is more useful than a PASS, and it is the answer the
founder has pre-committed to acting on: another finding of this same class ends the round and
sends the harness back to be re-specified rather than patched again. Do not soften it to be
agreeable, and do not manufacture a structural objection to seem rigorous — if the apparatus is
sound, say that plainly too.

---

## THE RESPONSE TO ATTEMPT 3 — judge this second

Attempt 3 found two things. Both accepted, both verified by hand, both fixed.

**(i) `importGraph()` seeded only from `app/(main)/command-centre/**/page.tsx`**, so
`app/api/command-centre/**/route.ts` was never in the graph. Its imports — `next/server`,
`@/lib/command-centre/wiki-graph`, and `@/lib/supabase/server`, **the service-role client that
bypasses RLS** — had no provenance entries, so "no real import without an entry" was false for
the most privilege-sensitive file in the capability. The route was checked for *existence* and
never for what it *pulls in*. Now seeded from the API directory as well; the three imports are
declared `no-source-baseline` (the route is `_rebuilt_not_ported`).

**(ii) `router.push(`/founder/wiki/${slug}`)` — a route that does not exist here**, so every
node click 404'd. The route-existence check missed it because it scanned `href=` and `fetch(`
string literals. It now also scans `router.push`/`router.replace`, truncating at the first `${`
and testing the static prefix.

The **fix** for (ii) changed between rounds and the founder overruled my first attempt at it. I
retargeted every click to `/command-centre/knowledge`; the ruling is that a click which appears
to navigate somewhere specific and always lands somewhere unrelated is a lie about
interactivity, so **the click path is removed entirely** — handlers, listeners, the orphaned
`useRouter`, and the page caption that still advertised "click to open the page". Same rule that
made `WikiEnhanceControl` absent rather than stubbed: a surface must not claim a capability it
does not have.

**Judge:**
- Are `page.tsx` and `route.ts` the right roots, or is the graph still under-seeded? What else
  is capability surface — `layout.tsx`, `middleware`/`proxy.ts`, `not-found.tsx`, server actions?
- The route-existence check now handles one more syntactic form. **That is the reactive-patch
  concern in miniature** — is scanning for navigation *forms* a design that can be completed, or
  will there always be another form? Say which.
- Was removing the click the right call, or does the graph now under-deliver against what a
  wiki-graph should do?

## THE NAMED REVIEW ITEM — judge the response to attempt 2

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

`WikiGraphCanvas.tsx` **was** byte-identical to its baseline when this was established — that is
how the two defects were shown to be inherited rather than introduced. It is **no longer
byte-identical**: KI-005 removed the click path and the KI annotations added comments. Do not
re-derive inheritance by diffing today and expecting empty. Attempt 1 flagged its leaked
`pointerleave` listener as a hard standards violation. It is one — **and it is present verbatim
in the baseline**, as is a `react-hooks/refs` error on the tooltip's `sizeRef` read.

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
npx vitest run __tests__/command-centre-readonly.test.ts      -> 27 passed (27)
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
