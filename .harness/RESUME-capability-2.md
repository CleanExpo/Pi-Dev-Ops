# RESUME — command-centre migration, capability 2

**Written:** 2026-08-01 · **Branch:** `feat/command-centre-migration` (16 commits) · **`main` untouched at `9f3be6ec`**

Read this, run the one command below, and start. Everything here is verifiable on disk — do not take it on trust.

---

## The one command

```bash
cd D:\Pi-Dev-Ops\dashboard
npx vitest run __tests__/command-centre-readonly.test.ts
```

**Expected right now: 1 failed | 21 passed (22).** The single failure is the work:

```
internal paths with no matching route in the target app (these would 404):
  app/(main)/command-centre/knowledge/page.tsx        -> /founder/command-centre
  components/command-centre/WikiEnhanceControl.tsx    -> /api/command-centre/lanes/wiki/enhance
  components/command-centre/wiki-graph/WikiGraphTile.tsx -> /founder/command-centre/wiki-graph
  components/command-centre/wiki-graph/WikiGraphTile.tsx -> /api/command-centre/wiki-graph
```

If you see anything other than 1 failed / 21 passed, stop and find out why before building.

## The job, already approved by the founder

Capabilities **2 (knowledge) and 3 (wiki-graph) ship as one unit** — knowledge links to wiki-graph, so knowledge cannot pass route-existence without it.

1. **Port the UI** for knowledge + wiki-graph — faithful port, source verbatim, then only the `@/*` alias rewrites.
2. **Rebuild the two API routes**, do not port them:
   - `/api/command-centre/lanes/wiki/enhance` (source: 40 lines)
   - `/api/command-centre/wiki-graph` (source: 58 lines)
   Write them against the target's `createServerClient` from `@/lib/supabase/server`. **Do not port the source versions** — they import a `@/lib/supabase/server` that resolves to an anon-key RLS-enforced client, while the target's is service-role and bypasses RLS. Same specifier, compatible shapes, clean typecheck, silent privilege change. That is why these two are a rebuild.
3. **Retarget the two `/founder/...` links** to their target paths under `/command-centre/...`.
4. Add provenance entries for every new file **and** every new import (`node __tests__/build-import-provenance.mjs` generates the skeleton; each needs a judgment: `same` | `different-but-checked` | `must-change`).
5. Run the harness, then the Codex review.

## The harness

`npx tsc --noEmit` · `npm run build` · the vitest suite above.

Build needs env in the **shell only** — never write `.env.local`, it is a fenced path:

```
PI_CEO_URL=https://x.invalid PI_CEO_PASSWORD=x \
NEXT_PUBLIC_SUPABASE_URL=https://lksfwktwtmyznckodsau.supabase.co \
NEXT_PUBLIC_SUPABASE_ANON_KEY=x SUPABASE_SERVICE_ROLE_KEY=x npm run build
```

What the suite enforces: file provenance · import provenance · baseline reachable (fails closed) · construct-count non-increase · **route existence** · **guard non-decrease** · external execution.

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

## Open, not blocking capability 2

`/api/kill-switch` POST · `/api/telegram` POST · three webhook routes calling `.update(` — enumerated, unscoped.

**The design question that outlives this migration:** the fence intercepts tool calls and cannot see HTTP. In a single shared-password system "authenticated" includes our own automation. Per-capability tokens instead of one shared `DASHBOARD_PASSWORD` is the real fix. Everything done so far narrows the agent-curl path and does nothing about the app calling itself.
