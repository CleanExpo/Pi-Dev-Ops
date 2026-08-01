# RESUME — command-centre migration, capability 2

**Written:** 2026-08-01 · **Branch:** `feat/command-centre-migration` (23 commits) · **`main` untouched at `9f3be6ec`**

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
npx vitest run __tests__/command-centre-readonly.test.ts       # expect 22 passed (22)
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

## FIRST THING: the Codex round on capability 2/3 — ATTEMPT 3 OF 3 IS THE LAST ONE

**Ledger — keep this current, it is the thing the last handoff claimed to have written and did not.**

| # | Verdict | Finding | Disposition |
|---|---------|---------|-------------|
| 1 | FAIL | Named exemptions too broad; unrelated Supabase export in the diff | **Fixed** in `b9080e1a` |
| 2 | FAIL | Provenance import map has a dangling `WikiEnhanceControl` entry; the import test cannot catch a stale map | **Fixed** in `c8685f92` |
| 3 | FAIL | `importGraph()` seeds only from `page.tsx`, so the API route's own imports — including the service-role client — could change with no provenance entry. Plus a broken control: node clicks went to `/founder/wiki/…`, which 404s here | **Fixed** (uncommitted at time of writing → see git log) |

**THE BOUND IS EXHAUSTED. Three attempts, three FAILs, all three findings real and all three
fixed. There is no attempt 4 without a founder ruling** — the three-attempt bound against a
fixed spec is a standing rule, not a judgement call, and quietly running a fourth would make
the bound decorative.

**This is the one genuinely open decision.** Options, with the basis for each:
- **Raise the bound** (e.g. to five). Each round has found a real defect and the findings are
  getting narrower, which is what convergence looks like — not what a stuck loop looks like.
  Cheapest, and the evidence supports it.
- **Re-spec and restart the count.** Defensible if you think three rounds of fixes have moved
  the artifact far enough that the original spec no longer describes it.
- **Accept as-is with findings recorded.** The capability works, the gate is green, and every
  finding is fixed — but it never earned a PASS, and "not done until it passes" is the standing
  rule. This one needs you to say it explicitly.

My read: **raise the bound.** Three rounds, three real defects, each smaller than the last, and
the last round's findings were both fixed in under an hour. That is a review working, not a
review failing. But the bound is yours.

Raw output: `.harness/cc-02-review-1.txt`, `.harness/cc-02-review-2.txt`. Brief: `.harness/cc-02-review-brief.md`.

### What attempt 2 cleared (do not re-litigate, do not rebuild)

Codex independently confirmed: the auth fix closes the gap with no bypass it could find; the
page-redirect / API-401 split is the right response for a data route; the `database client`
`1 -> 2` declaration is genuinely one client counted twice, not a hidden second client; the
magnitude-scoped delta is narrower in practice; declare-not-fix on KI-003/004 is defensible and
the lint suppression is scoped tightly enough that a new violation still fails.

### What attempt 3 must fix first

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
