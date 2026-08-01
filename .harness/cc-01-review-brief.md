# Review brief — capability 1 of 6, hermes-control-panel port (REVISED SPEC)

You are reviewing a code change. **Flag findings. Do not fix anything. Do not write code.**

## Inputs (these four only)

1. **This spec** (below)
2. **The loop** (below)
3. **The diff**: `D:\Pi-Dev-Ops\.harness\cc-01.diff` — read it
4. **The test**: `dashboard/__tests__/command-centre-readonly.test.ts` and `command-centre-provenance.json`, both in the diff

## Spec — revised 2026-08-01 by founder ruling

A capability is being ported between two Next.js apps.

**Source:** `Authority-Site/apps/web/src/app/(founder)/founder/command-centre/hermes-control-panel/`
**Target:** `Pi-Dev-Ops/dashboard/app/(main)/command-centre/hermes/`

**The governing instruction is: port faithfully, including existing behaviour.** This migration moves behaviour between apps. It does not improve it. A difference from the source is a defect *whether or not the source's own behaviour is ideal*.

- **R1. Behaviour matches the source.** Rendered output, data, and controls are as the source produces them.
  - **Known and intentional:** the page renders the first 8 of 13 registry modules with a `+N more` line. **This cap is in the source** (`DECK_LIST_CAP`) and is preserved deliberately. It is logged as KI-001 and will be fixed as separate work with its own review. **Do not report the cap as a defect of this port.** Do report it if the port's cap *differs* from the source's.
- **R2. No new network surface.** The port introduces no network/DB/execution construct the source file did not already contain.
- **R3. No new npm dependencies.**
- **R4. Typechecks and builds.**
- **R5. Import paths correctly rewritten for the target's `@/*` → dashboard-root alias.**
- **R6. No new write path, paid-API call, or production-host reach relative to the source.**

### What is deliberately NOT claimed

**This spec does not claim the page makes no network call, and you should not evaluate it as if it did.**

That is an unbounded negative — there is always another path (dynamic import, `require`, `WebSocket`, `sendBeacon`, server actions, transitive side effects), so no evidence could ever satisfy it. Three prior attempts were correctly failed for exactly this reason, and the finding was right each time: **the spec was the defect, not the code.**

The claim now under review is bounded and diff-relative: **"introduces no network surface the source did not have."** Judge that claim. If you believe it is the wrong claim to be making, say so as a separate remark — but assess the work against the claim actually made.

## Loop

```
npx tsc --noEmit                                            -> exit 0
npm run build                                               -> exit 0, route /command-centre/hermes present
npx vitest run __tests__/command-centre-readonly.test.ts     -> 15 passed
```

## Test — what it does and its proven capability

Walks the transitive import graph from each capability page, then for each ported file compares the **count** of tracked constructs against its declared source baseline. The port fails if any count **increases**. Tracked: `fetch`, http clients, `WebSocket`/`EventSource`/`XMLHttpRequest`/`sendBeacon`, dynamic `import(`, `require(`, remote-host literals, DB writes, DB client construction, MCP client, `"use server"`, paid API key names.

Baselines are declared per-file in `command-centre-provenance.json`. **A file with no declared origin fails the test**, so nothing can enter the capability surface without a stated baseline.

**Proven capable, not assumed:** a real `fetch('https://evil.example.com')` was planted into the ported page; the suite failed 2 tests with `network: fetch increased vs baseline`. Removing it returned all 15 to green. The check can return non-null.

**Stated limits:** the comparison runs only where the Authority-Site checkout exists; in CI it warns `[BASELINE UNAVAILABLE]` and the comparison does not run. Counting is token-based, so it bounds *added* constructs, not obfuscated ones.

## Prior rounds

Attempts 1–3 were failed under the **old** spec, which demanded absolute read-only proof. The founder has since changed the spec. This is **attempt 3 under the revised spec**. Attempt 2 FAILed on R1: force-dynamic and the Chakra font had been stripped to satisfy the OLD spec and were not restored when the spec changed. Both are now back; page.tsx and DeckDetails.tsx are verbatim from source apart from the R5 alias rewrites and one corrected comment. DeckDetails.tsx is byte-identical to source. Earlier: Attempt 1 under it FAILed on: unrelated  changes in the diff (now split into a separate commit; this diff is scoped to  only),  letting the suite pass unverified (now fails closed unless ), and the import graph matching only  (now also matches side-effect ).

Judge this on its own merits. Do not pass it because prior rounds were corrected.

## What to report — two axes, kept separate

### Axis 1 — Standards
TypeScript/React/Next.js App Router practice in the diff. Cite the hunk. Distinguish hard violations from judgement calls. Skip what the compiler or a linter already enforces. Under 400 words.

### Axis 2 — Spec
Against R1–R6 as written above:
- (a) requirements not met or only partly met
- (b) behaviour introduced that was not asked for
- (c) requirements implemented incorrectly
- (d) whether the test genuinely supports the **diff-relative** claim, or whether the claim can be false while the test passes

Quote the diff for each finding. Under 400 words.

## Verdict

End with exactly one line:

`VERDICT: PASS` or `VERDICT: FAIL — <one-line reason>`
