# Harness coverage map — what it catches, what it structurally cannot

**Date:** 2026-08-01 · **Scope:** the command-centre migration harness
**Purpose:** enumerate the gaps now, not at capability 6, where the failure mode is a dry-run surface silently becoming a live one.

---

## The checks that exist

| # | Check | Where | Fails on |
|---|---|---|---|
| C1 | **Provenance** | `command-centre-readonly.test.ts` | any file in the capability import graph with no declared source origin |
| C2 | **Baseline resolvable** | same | a provenance pair whose port or source path does not resolve |
| C3 | **Baseline reachable** | same | the Authority-Site checkout being absent, unless `CC_ALLOW_NO_BASELINE=1` |
| C4 | **Construct-count non-increase** | same | a tracked construct appearing *more times* than in the named baseline |
| C5 | **Typecheck** | `tsc --noEmit` | type errors |
| C6 | **Build** | `next build` | compile failure, missing route |
| C7 | **Fail-open scan** | `fence/fail_open_check.py` | verification code that swallows a signal; evidence files not git-tracked |
| C8 | **Cross-vendor review** | Codex gpt-5.5, fresh session | anything a competent reader spots in spec or standards |
| C9 | **Literal navigation tripwire** | `command-centre-readonly.test.ts` | a **literal** `href="/x"`, `fetch("/x")` or `router.push("/x…")` naming a route that does not exist here. **Tripwire, not proof.** Kept after C12 closed G1 because it is the only cover for `router.push` inside a client event handler, which never reaches rendered HTML. |
| C10 | **Import map vs reality** | same | a provenance entry for an import no file makes; an import with no entry; a `resolves_in_target: file:` that is absent from disk |
| C11 | **Auth coverage** | `command-centre-auth-coverage.test.ts` | any command-centre page or API served to a request with no session, proven against `proxy()` directly with positive controls |
| C12 | **Runtime route exercising** | `scripts/route-exercise.mjs`, gated in `handoff-loop.sh` | any internal link in **rendered** output that 404s or 500s. Starts the built app, authenticates, fetches every command-centre page, requests every link they emitted. **The authority on G1** — C9 is only a tripwire. |

**C4 tracks:** `fetch(`, http clients (axios/got/node-fetch/undici), `WebSocket`/`EventSource`/`XMLHttpRequest`/`sendBeacon`, dynamic `import(`, `require(`, remote-host literals, `.insert/.update/.upsert/.delete(`, `createClient`/`createServerClient`, MCP client names, `"use server"`, and three literal API-key names.

---

## What it structurally cannot catch

These are not tuning gaps. They are outside the shape of a count-based static comparison.

| # | Gap | Why the harness cannot see it | Already bitten us? |
|---|---|---|---|
| G1 | **Route existence** — **CLOSED by C12** (2026-08-01) | C4 compares counts. A `fetch('/api/x')` that exists in both source and port passes even when `/api/x` was never ported. C9 catches the *literal* forms only. **C12 closes it at runtime**: the app is started and every link the pages actually rendered is requested, so computed navigation (`<Link href={expr}>`) is covered by what the surface emitted rather than by what forms a regex looked for. | **YES — capability 2, four times.** Codex found links to `/founder/command-centre` and fetches to two unported API routes; then `router.push(`/founder/wiki/${slug}`)` 404ing on every node click; then `<Link href={d.href}>` invisible to the check. |
| G2 | **Semantic equivalence** | Same count, different endpoint or payload. Swap a URL and the count is unchanged. | Latent |
| G3 | **Runtime behaviour** — **partially mitigated by C12** | C12 now renders every command-centre page and exercises its links, so "does this page render and do its links resolve" IS asked. Still unasked: network interception, and whether a control that renders actually does nothing when clicked. | Latent for the remainder |
| G4 | **Indirect / computed constructs** | `const m = 'fet'+'ch'`, `globalThis[k]()`, string-built URLs, computed property access. | Latent |
| G5 | **Node built-in side effects** | `child_process`, `fs` writes, `process.exit`, `os` — **not tracked at all** | Latent |
| G6 | **Transitive npm behaviour** | The graph stops at `node_modules`. A dependency that fetches is invisible. | Latent |
| G7 | **Server actions defined elsewhere** | `"use server"` is counted only in scanned files; an action imported from outside the graph is not. | Latent |
| G8 | **Env-driven divergence** | Behaviour that differs by env var is identical in source text. | Latent |
| G9 | **CSS-delivered behaviour** | `url()` fetches, `@import` from a remote host. CSS is provenance-checked but not construct-scanned. | Latent |
| G10 | **Deletion of a safety check** | C4 fails on an *increase*. Removing a guard **lowers** counts and passes. | Latent — **directly relevant to capability 6** |

**G10 deserves emphasis.** The comparison is one-directional by design: "no new surface". A port that *deletes* an existing safety check passes every check in the harness, because deleting a guard reduces the tracked-construct count.

---

## Operator-gateway's five constraints, assessed honestly

Its own header states the contract:

> *"SANDBOX DRY-RUN + CONTROLLED REAL-LOCAL FOUNDATION MODE … no production DB writes, no external execution, no live runner, no API keys, no web-session scraping. No real execute button."*

**Would any current check catch the loss of each?**

| # | Constraint | Caught? | Reasoning |
|---|---|---|---|
| **OG1** | **No production DB writes** | **PARTIAL** | C4 catches an *added* `.insert/.update/.upsert/.delete(`. It does **not** catch: a write via `.rpc(`, a write through an existing call whose target changed to a prod ref, a write through a helper outside the graph, or a write where the count stays level because another call was removed. The fence's `prod-db` predicate catches a prod ref *at runtime*, but the fence is in **shadow** and does not gate CI. |
| **OG2** | **No external execution** | **NO** | `child_process`, `exec`, `execSync`, `spawn`, `fork` are **not tracked by any check**. Zero coverage. A ported file could shell out and every check would pass. |
| **OG3** | **No live runner** | **NO** | "A runner is wired" is a *system property*, not a construct. Nothing models it. Not expressible as a count. |
| **OG4** | **No API keys** | **PARTIAL** | C4 matches three literal names only (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `STRIPE_SECRET`). Misses every other key name, `process.env[dynamic]`, and keys read from a config object or a secrets helper. |
| **OG5** | **No real execute button** | **NO** | Requires inspecting rendered output and handler wiring. Nothing renders anything. A button whose `onClick` posts to a live endpoint is invisible to a static count. |

**Three of five have zero coverage. Two are partial. None is fully covered.**

Combined with **G10** — deleting a guard passes — the position for capability 6 is: *the harness that will review the operator gateway cannot detect the loss of the properties that make the operator gateway safe.*

That is the finding this map exists to surface.

---

## What follows from this

1. **Capability 6 must not be ported against the current harness.** The founder ruling already requires a hand-established baseline for it. This map shows the automated layer would add close to nothing on the five constraints.
2. ~~**G1 (route existence) is buildable now.** Bounded and decidable: every internal `href`/`fetch` path in a ported capability must resolve to a route that exists in the target.~~ **This was wrong, and the record keeps it visible rather than editing it away.** G1 is *not* bounded and decidable as stated. Three rounds of "add the next form" — literal `href`, then `router.push` template literals, then `<Link href={expr}>` — established that enumerating navigation forms cannot be completed: object hrefs, wrapper components, `window.location`, callbacks passed as props, server redirects and form actions all remain, and the list has no end. **See "G1 — the standing ruling" below.**
3. **OG2 (external execution) is buildable now** — add `child_process`/`exec`/`spawn`/`execSync` to C4's tracked set. Cheap, and it closes total-zero coverage on one named constraint.
4. **G10 (guard deletion) needs a second direction** — a *decrease* check on a named safety-construct subset, not on everything.
5. **OG3 and OG5 are not static problems.** They need either a render test with network interception, or an architectural boundary that makes execution structurally unreachable from the page.

---

---

## G1 — CLOSED by runtime route exercising (2026-08-01)

**Status: CLOSED by C12.** C9 remains, downgraded to a cheap tripwire. The ruling that produced this is kept below because the reasoning is the reusable part.

Four review rounds each found the same class — *coverage reading wider than it is* — and three
of the four were G1 specifically. The response after the fourth is deliberately **not** another
detector.

**What was done today (item 1 of 4, and only this):**
- The check was **renamed to what it verifies**: literal `href`/`fetch`/`router` paths, described
  in its own name and failure message as a **tripwire**, not a proof. A share of the fourth
  finding was simply the test's name overclaiming, and that half was free to fix.
- **The gap stays open on this map.** Renaming is necessary and not sufficient. G1 closes when
  something actually closes it.

**What closed it: runtime route exercising. Not AST extraction.**

AST with dataflow was the reviewer's proposal and was **rejected**. It is the same uncompletable
enumeration in better clothes — you still have to decide which patterns count, and wrapper
components and computed values defeat it identically. Runtime changes the evidence from *what
forms we looked for* to *what the surface actually does*.

That is the same fact-versus-claim distinction that made operator-gateway a rebuild rather than
a port, and it is the distinction this whole harness keeps failing on in one direction: a static
check can only ever report what it was told to look for, and then gets described as though it
reported on the surface.

**Built and proven.** `scripts/route-exercise.mjs`, wired as a `handoff-loop.sh` gate.

The proof is a side-by-side on one planted defect — a `DECKS` entry pointing at a route that
does not exist, reached through `<Link href={d.href}>`, which is exactly the form attempt 4
found:

| detector | verdict on the identical defect |
|---|---|
| C9 regex tripwire | **27 passed — missed it** |
| C12 runtime exercising | **FAIL — named `/command-centre/hermes-DOES-NOT-EXIST`** |

**Correction (round-1 review).** That side-by-side was really run — `DECKS` was edited to
`/command-centre/hermes-DOES-NOT-EXIST`, the app rebuilt, C9 passed 27, C12 failed naming the
route — but **it left no reproducible artifact**, and the reviewer was right to call the claim
overbroad. What ships in the repo is `--plant-broken-link`, which injects an `<a>` into
already-fetched HTML *inside* C12. That is a weaker control: it proves the fetch-and-assert half
and never touches C9, so nobody can reproduce the comparison from the repo alone.

For a verifier that gap matters more than usual — the whole point is that claims be checkable.
**Reproduce it like this:**

```bash
# 1. plant a computed-navigation defect in source
perl -pi -e 's{href: "/command-centre/hermes"}{href: "/command-centre/hermes-NOPE"}'   'dashboard/app/(main)/command-centre/page.tsx'
# 2. C9 — the static tripwire — passes, missing it
cd dashboard && npx vitest run __tests__/command-centre-readonly.test.ts   # 27 passed
# 3. rebuild, then C12 catches it
npm run build && cd .. && node scripts/route-exercise.mjs                  # FAIL, names the route
# 4. revert and rebuild
git checkout -- 'dashboard/app/(main)/command-centre/page.tsx'
```

**What C12 does NOT cover, stated now rather than found in a later round:**
- Navigation that only fires in a client event handler (`router.push` in `onClick`) is not in
  server-rendered HTML. C9's literal scan is the only cover for that, which is why C9 stays.
- **CLIENT-HYDRATED navigation** — added after round-1 review named it as the largest remaining
  hole. C12 reads server-rendered HTML; it does not run a browser or hydrate components. A
  `<Link>` that appears only after `useEffect`, from localStorage, at a viewport size, or once
  client data arrives is **not exercised**. Closing this needs a real browser, which is a
  different tool at a different cost — it is a bounded, statable limit, not an open enumeration.
- Links behind a branch this run does not render (an error state, a populated-data state) are
  not exercised. Coverage is what rendered, not what could render. Every entry page is asserted
  200 so a page that fails to render cannot pass by emitting nothing — but an unrendered
  *branch* is genuinely unmeasured.
- External links are skipped by design; the question is whether OUR routes exist.
- `/_next/*` build assets are excluded — not navigation, and `npm run build` owns them.

**Two controls it carries, both of which caught real false-greens in its own first hour:**
1. *Session accepted* — if the minted cookie were rejected, every page would redirect to login
   and the run would happily exercise the login page and report success. A non-200 entry page
   is a hard stop.
2. *Port not already in use* — the first version orphaned its `next start` on Windows
   (`shell: true` + `server.kill()` kills the shell, not the grandchild). A later run attached
   to that stale server, measured the **previous build**, and reported the planted defect
   absent. It was caught only because a positive control expected failure and got a pass.
   A live port is now a hard stop, and the process tree is killed with a synchronous
   `taskkill /T /F` — an async kill registered on `exit` never runs, which was the second bug.

**Scope discipline, explicitly.** Re-spec the navigation detector and **nothing else**. The
diagnosis was narrow: the design is sound, import provenance is closed, the positive controls
are load-bearing. A narrow finding is not licence to rebuild the apparatus.

**Prerequisite — the reviewer must be able to execute.** The cross-vendor reviewer could not run
the suites on three of four rounds and its build failed on the fourth; only `tsc --noEmit` was
ever independently confirmed. That is tolerable for structural claims about code. It is **not**
tolerable for reviewing a verifier: the re-spec's entire claim is *these checks fail red when
they should*, which can only be confirmed by running them. Re-speccing the harness and grading
it by assertion reproduces the exact defect being fixed. **Fix the sandbox before the re-spec
review, not after.**

---

*Compiled 2026-08-01 after capability 2 attempt 1 failed on G1 — a class the harness could not see, found by the reviewer rather than the harness. Amended after attempt 4 found G1 a third time, which is what turned it from a gap to be patched into a design to be replaced.*
