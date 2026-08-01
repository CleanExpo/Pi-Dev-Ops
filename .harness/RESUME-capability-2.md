# RESUME — command-centre migration, capability 2

**Written:** 2026-08-01 · **Branch:** `feat/command-centre-migration` (25 commits) · **`main` untouched at `9f3be6ec`**

Read this, run the session-open ritual below, and start. Everything here is verifiable on disk — do not take it on trust.

---

## Session-open ritual — run ALL of it, in order, before touching anything

```bash
# 1. Skills drift. FIRST, before any work.
python D:\Pi-Dev-Ops\fence\deploy_skills.py --check    # exit 1 = machine has drifted from repo

# 2. The definition-of-done gate for the whole repo.
cd D:\Pi-Dev-Ops
PI_CEO_URL=https://x.invalid PI_CEO_PASSWORD=x \
NEXT_PUBLIC_SUPABASE_URL=https://lksfwktwtmyznckodsau.supabase.co \
NEXT_PUBLIC_SUPABASE_ANON_KEY=x SUPABASE_SERVICE_ROLE_KEY=x \
bash scripts/handoff-loop.sh                            # expect: pass=7 fail=0 READY

# 3. The capability suites.
cd D:\Pi-Dev-Ops\dashboard
npx vitest run __tests__/command-centre-readonly.test.ts       # expect 27 passed (27)
npx vitest run __tests__/command-centre-auth-coverage.test.ts  # expect 7 passed (7)
```

**Anything other than those numbers: stop and find out why before building.**

**Why `deploy_skills.py --check` is step 1 and not advice.** CI cannot see this machine —
`~/.claude/skills/` is a deploy artifact and gitignored, so `skills-drift-check.yml` can only
police what is committed. A drift check that depends on someone remembering to run it has
already failed open by our own ruling (failure mode 4, the one that bit `proof-discipline`
itself). It runs at session open, every session, or it does not run.

**Why the whole gate and not just the vitest suite.** The previous handoff recorded "22/22
local green" and it was true — of that one suite. The repo gate was `BLOCKED` on lint at the
same moment. One suite passing is not the tree being green, and a handoff that reports the
narrower number reads as the broader claim.

**The code for capability 2/3 is BUILT. The outstanding item is the Codex round —
under the standing rules it is not done until it passes.**

## RE-SPEC REVIEW LEDGER (navigation layer) — and the counter reset, stated

| # | Verdict | Finding | Disposition |
|---|---------|---------|-------------|
| 1 | FAIL | No timeouts; stale build passes standalone; query strings dropped; POSIX cleanup unfixed; scope list incomplete; the side-by-side proof claim overbroad | Fixed |
| 2 | FAIL | Extractor matched slash-prefixed hrefs only, so rendered RELATIVE links were unmeasured | Fixed by RESOLVING hrefs, not by adding a pattern |
| 3 | FAIL | Redirect to a missing target passed green; freshness walk too narrow; **G1 closure claim still too broad** | Two defects fixed; **claim downgraded** |
| — | **COUNTER RESET** | **requirement changed** | see below |
| 4 | running | — | — |

**THE BOUND WAS SPENT AT ROUND 3. Round 4 is legitimate only because the requirement
changed, and that reset is named here rather than assumed.**

Three attempts against a fixed spec is the standing rule; rounds 1–3 were three FAILs and
exhausted it. The standing rule also resets the counter when the **requirement** changes, and it
did: round 3's finding was that the G1 **closure claim** was too broad, and the response was to
**downgrade the claim from CLOSED to SUBSTANTIALLY MITIGATED**. Rounds 1–3 reviewed C12 against
"G1 is closed". Round 4 reviews it against "G1 is substantially mitigated for server-rendered
navigation, with named residue". That is a different requirement, so round 4 is round 1 of the
new spec — not attempt 4 of the old one.

**Why this is written down instead of just done.** A fourth attempt that runs without the reset
being named is the bound going decorative *by accident*, which is the exact failure the bound
exists to prevent. The counter is only a control if the thing that moves it is stated. If the
next reader cannot see which spec each round was judged against, the ledger is decoration too.

**What this does NOT license.** The reset is not available for a requirement that was narrowed
merely to make a failing check pass. The test is whether the new claim is *more honest*, not
whether it is *easier to satisfy* — and here the claim got strictly weaker and more precise
while the check also got strictly stronger (redirects followed, freshness widened). If a future
downgrade weakens the claim without strengthening anything, that is not a changed requirement,
it is moving the goalposts, and the counter does not reset.

## STATUS OF CAPABILITY 2/3 — read this before touching anything

**Unmerged. Unshipped. It has never earned a PASS.**

Hold these two claims apart, because collapsing them is how a green suite starts meaning nothing:

- **The capability is believed good.** Gate green, 34 tests passing, four review rounds' findings
  all fixed, the auth hole closed and proven.
- **The evidence apparatus has not earned the right to say so.** G1 is open. The navigation
  detector misreports its own coverage. Three of four review rounds could not execute the suite,
  so every green loop in that review is the builder's claim alone.

"Believed good" and "verified good" are different claims. This capability has the first and not
the second. Do not merge it, do not ship it, and do not let a future reader see a green gate and
infer the second.

## SCHEDULING RULING (founder, 2026-08-01) — DO NOT START CAPABILITY 4

**Providers waits for the navigation layer.**

Every capability inherits this harness. Building three more on a verifier that is known to
misreport its own coverage stacks the same defect four deep — and the defect is specifically the
kind that makes each one *look* verified. Four capabilities each carrying an unmeasured
navigation surface is not four times the risk; it is four times the false confidence, discovered
at whichever one finally breaks in production.

**Order of work, as ruled:**

1. ~~Rename and re-scope the route-existence check; record G1 as an open gap.~~ **DONE
   2026-08-01** — C9 in the coverage map, gap held open, `docs/HARNESS-COVERAGE-MAP-2026-08-01.md`.
2. ~~**Reviewer sandbox execution** — prerequisite for the re-spec review.~~ **DONE 2026-08-01.**
   Root cause was Codex's Windows *restricted-token* sandbox: spawn denied, write allowed,
   unlink denied. Vitest died on Vite's `exec("net use")`; `next build` died on `unlink`. Use
   **`scripts/codex-review.sh <brief> <out>`** for every review from now on — it runs outside
   that sandbox and replaces the isolation with tree-integrity, execution-proof and plan-auth
   controls, all three proven able to fail. Verified: the reviewer ran the auth suite itself,
   7 passed (7).
3. **Replace the navigation detector with runtime route exercising.** Not AST extraction. Gating
   work before operations, alongside per-capability tokens.
4. Capability 4 (providers) — **blocked on 3.**

## The Codex round on capability 2/3 — CLOSED AT ATTEMPT 4. Do not open a fifth.

**Ledger — keep this current, it is the thing the last handoff claimed to have written and did not.**

| # | Verdict | Finding | Disposition |
|---|---------|---------|-------------|
| 1 | FAIL | Named exemptions too broad; unrelated Supabase export in the diff | **Fixed** in `b9080e1a` |
| 2 | FAIL | Provenance import map has a dangling `WikiEnhanceControl` entry; the import test cannot catch a stale map | **Fixed** in `c8685f92` |
| 3 | FAIL | `importGraph()` seeds only from `page.tsx`, so the API route's own imports — including the service-role client — could change with no provenance entry. Plus a broken control: node clicks went to `/founder/wiki/…`, which 404s here | **Fixed** (uncommitted at time of writing → see git log) |

| 4 | FAIL | Route-existence coverage still overclaims — blind to `<Link href={d.href}>` on the index page | **NOT FIXED. Deliberately.** |

**STOP. THE CONDITION TRIGGERED — the harness goes back for re-spec, not a fifth attempt.**

The founder granted attempt 4 as a per-instance release valve with one condition: *if it returns
another instance of "coverage that reads wider than it is", stop and re-spec the harness rather
than patch again.* It did exactly that. So attempt 4's finding is **recorded and left unfixed** —
adding another regex form is the reactive patch the ruling forbids.

**Note what the finding is and is not.** All three current `DECKS` hrefs resolve. There is no
live 404. The defect is that the test is named "every internal href/fetch resolves" while being
structurally unable to see `href={expr}`, so a future bad entry passes silently.

### The diagnosis is narrower than "the harness is wrong" — read it carefully

The reviewer did **not** say the apparatus is incoherent. It said there is a real design:
*define the capability surface, require provenance for every reachable file and import, fail
closed when the baseline is absent, compare ported files by bounded construct counts, prove
declared exemptions separately.* Its words: "a real design, not just random test accumulation."

It also found two halves in different health:

- **Import provenance — sound, and its class is closed.** Seeding from pages plus API routes,
  bidirectional map checks, and the missing-target assertion close the phantom-entry class for
  statically-discoverable imports. Remaining misses are *known and namable*: dynamic imports,
  computed requires, package side effects, route handlers outside the seeded subtree, and the
  semantic case where a count holds steady while the target changes.
- **Boundary/navigation detection — not sound.** Regex form-scanning "is not a design that can be
  completed". Next navigation appears as `<Link href={expr}>`, object hrefs, local arrays, helper
  components, `window.location`, callbacks passed as props, server redirects, form actions, and
  `router` wrappers. There is always another form.

- **Positive controls and fail-closed checks — load-bearing, not decorative.** Explicitly. They
  prevent vacuous green. What they cannot do is surface the *next* blind spot; they only prove
  the current detectors are alive.

### What the re-spec should target

**Not the whole harness. The navigation/route-coverage layer.** The reviewer's proposed sound
version: AST-based extraction with limited dataflow for local constants and wrapper components,
or runtime route exercising from rendered output. And the honesty fix that costs nothing —
**regex is a cheap tripwire and must not be described as proving every internal navigation
resolves.** Half of this finding is a naming problem: the test claims more than it checks.

### Attempt 4's other note, reinforcing scheduled work

The reviewer again could not execute the suites (`spawn EPERM` on the Vite config) and this time
`npm run build` also failed in its sandbox (EPERM unlinking `.next/app-path-routes-manifest.json`).
It confirmed `tsc --noEmit` only. The green loop remains **my** claim, not an independent one —
which is already recorded as gating work before operator-gateway.

### What attempt 2 cleared (do not re-litigate, do not rebuild)

Codex independently confirmed: the auth fix closes the gap with no bypass it could find; the
page-redirect / API-401 split is the right response for a data route; the `database client`
`1 -> 2` declaration is genuinely one client counted twice, not a hidden second client; the
magnitude-scoped delta is narrower in practice; declare-not-fix on KI-003/004 is defensible and
the lint suppression is scoped tightly enough that a new violation still fails.

### What attempt 3 found (historical — fixed in c8685f92/b1f5ad99)

`command-centre-provenance.json` declares
`app/(main)/command-centre/knowledge/page.tsx :: @/components/command-centre/WikiEnhanceControl`
resolving to `components/command-centre/WikiEnhanceControl.tsx`. **That file does not exist and
the page does not import it** — KI-002 omitted it. The import test iterates map entries, so it
validates the map against itself: a phantom entry reads as coverage. Verified by hand, the
finding is correct.

Two halves, and the second is the real one:
1. Delete the dangling entry.
2. **Make a stale map fail.** The map must be checked against the actual imports in both
   directions — no entry without a real import, no real import without an entry, and no
   `resolves_in_target: file: X` where X is absent from disk. Without (2), (1) is a one-off
   patch on a hole that reopens the next time a file is dropped.

### Caveat on attempt 2's evidence

Codex could not execute the suites — `spawn EPERM` loading the Vite config in its sandbox — so
it reviewed statically against the supplied loop. Its reasoning about the code stands; treat
"tests pass" in that report as **my** claim, not an independent one. The local runs are the
evidence for that half.

Use `.harness/cc-01-review-brief.md` as the template. Bounded at three attempts against a
fixed spec, each materially different.

**Make the declared deltas a NAMED review item.** Give the reviewer the list explicitly —
file, rule, stated reason — from `_declared_deltas` in
`__tests__/command-centre-provenance.json`, and ask directly whether any of them is wrong.

Currently two, both on `app/(main)/command-centre/wiki-graph/page.tsx`:
- **auth gate** — `getUser()`+`redirect('/auth/login')` removed; auth enforced upstream by `proxy.ts`
- **database client** — `await createClient()` (anon-key, RLS) → `createServerClient()`

**These are exemptions the builder wrote to its own checks.** The builder must not be the one
grading them. Ask the reviewer to judge each on its merits, not to accept the stated reason.

## What was built (done, for context)

Capabilities **2 (knowledge) and 3 (wiki-graph) shipped as one unit**.

- UI ported faithfully; `/founder/*` links retargeted
- `/api/command-centre/wiki-graph` **rebuilt** against `createServerClient` — the source's
  `@/lib/supabase/server` is anon-key/RLS/per-user, the same specifier here is service-role
  with no identity. A verbatim port would have typechecked while swapping RLS-enforced for
  RLS-bypassing.
- wiki-graph **page** data access rebuilt the same way
- `/command-centre` index written fresh; links only to routes that exist
- `WikiEnhanceControl` and its route **omitted — KI-002**, founder-ruled. Absent, not stubbed.
- `d3-force`/`d3-selection`/`d3-zoom` added at baseline versions

## The harness

`npx tsc --noEmit` · `npm run build` · the vitest suite above.

Build needs env in the **shell only** — never write `.env.local`, it is a fenced path:

```
PI_CEO_URL=https://x.invalid PI_CEO_PASSWORD=x \
NEXT_PUBLIC_SUPABASE_URL=https://lksfwktwtmyznckodsau.supabase.co \
NEXT_PUBLIC_SUPABASE_ANON_KEY=x SUPABASE_SERVICE_ROLE_KEY=x npm run build
```

What the suite enforces: file provenance · import provenance · baseline reachable (fails closed) ·
construct-count non-increase · route existence · guard non-decrease · external execution.

Files are categorised: **ported** (compared against baseline) · **rebuilt** · **target-native** ·
**declared-delta** (per-file per-rule exemption with a stated reason — only the NAMED rule is
exempt for the NAMED file, so any other divergence in the same file still fails).

## The review

Cross-vendor, on the founder's Codex Max plan. **Verify the plan first** — `auth_mode` must be `chatgpt` and `OPENAI_API_KEY` absent in `~/.codex/auth.json`. If the plan is unreachable, **stop and ask**; do not fall back to a paid per-call API.

```bash
codex exec --skip-git-repo-check -m gpt-5.5 "<prompt>" < /dev/null > out.txt 2>&1
```

`< /dev/null` is required — `codex exec` reads stdin and hangs forever without it. Never background it.

Copy `.harness/cc-01-review-brief.md` as the template; it is the spec that finally passed. **Bounded at three attempts** against a fixed spec, each materially different. Reviewer silence, timeout or crash is **not** a pass.

## Rules that are settled — do not re-litigate

- **Never spec an unbounded negative.** The claim is diff-relative: *"introduces no network surface the source did not have."* Not absolute read-only proof. Three attempts died on this.
- **A review is never coverage.** It does not appear as a row in any coverage map.
- **Port faithfully, including existing behaviour** — including the 8-of-13 module cap (KI-001, deliberate).
- **operator-gateway is a REBUILD, not a port.** Decided; the hand-baseline is its spec input.
- Do not build render-test infrastructure.

## Gates

Stop for exactly two things: **spending real money**, and **touching production**. Step 4 (before operations and operator-gateway) is an additional pause, not a substitute. Everything else — plan, sandbox, review vendor, evidence standard, build order — is settled; carry it yourself.

## State to trust

- Capability 1 (hermes) **passed** cross-vendor review and re-verified clean through import provenance
- Fence in **shadow**, 19 hosts, 17 databases, no `HARD_STOP`
- Auto-commit hook **dead** and proven — nothing commits or pushes unless you do
- 7 incident records in `.harness/incidents.jsonl` (tracked; it was gitignored once, force-tracked now)

## Scheduled work — founder-confirmed, with positions

**HTTP hardening — BEFORE step 4.** `/api/kill-switch` POST · `/api/telegram` POST · three
webhook routes calling `.update(`. Operations ships approvals and would add to this surface,
so it lands first.

**Per-capability tokens replacing `DASHBOARD_PASSWORD` — AT step 4, as gating work.**

The reason is sharper than "it closes the class". **Operations ships approvals, and an approval
endpoint reachable by anything holding the shared password — including the agents whose work is
being approved — is not an approval gate.** It is a button. Tokens land *before* operations, not
alongside it.

This is also a prerequisite for the enhance route (KI-002) ever existing here: that route needs
a per-user identity, which is exactly what tokens would supply.
