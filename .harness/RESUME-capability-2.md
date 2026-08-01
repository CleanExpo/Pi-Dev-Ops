# RESUME — command-centre migration, capability 2

**Written:** 2026-08-01 · **Branch:** `feat/command-centre-migration` (16 commits) · **`main` untouched at `9f3be6ec`**

Read this, run the one command below, and start. Everything here is verifiable on disk — do not take it on trust.

---

## The one command

```bash
cd D:\Pi-Dev-Ops\dashboard
npx vitest run __tests__/command-centre-readonly.test.ts
```

**Expected right now: 22 passed (22). Route-existence: 0 broken paths.**

If you see anything other than 22/22, stop and find out why before building.

**The code for capability 2/3 is BUILT. The outstanding item is the Codex round —
it has not been reviewed, and under the standing rules it is not done until it passes.**

## FIRST THING: the Codex round on capability 2/3

Everything else below is done. This is the only outstanding item.

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
