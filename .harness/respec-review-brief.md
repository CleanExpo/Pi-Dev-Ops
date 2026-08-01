# Review brief — navigation-layer re-spec (C12) — ROUND 4

You are reviewing a change to a **verifier**. Flag findings. Do not fix anything. Do not write
code. Do not edit, create or delete any file in the repository.

**Round 4.** Round 3 returned `FAIL — C12 catches rendered computed links, but the G1
closure/non-coverage claim is still too broad`. Two real defects fixed; on the third finding
**the claim moved rather than the check**:

- **Redirect chains.** A link 307ing to a MISSING destination passed green, because the hop is
  neither 404 nor 5xx. `finalStatus()` now follows same-origin redirects to a final status; an
  external hop ends the walk; a loop is itself a finding. Per-path fetch errors now name the
  path. Control: `--self-test-redirects` stands up a throwaway server (the app has no redirect
  chain to borrow) and asserts 307→404 reports **404**, 307→200 reports 200, and /loop reports
  `redirect-loop`.
- **Build freshness** walked `app/components/lib/proxy.ts` only, so a `next.config` or
  dependency change after a build left *standalone* C12 measuring an old artifact. Now also
  covers `next.config.*`, `package.json`, lockfiles, `tsconfig.json`. Control: touch
  `next.config.ts` → exit 2 naming it.
- **G1 downgraded from CLOSED to SUBSTANTIALLY MITIGATED.** Three rounds each found the claim
  wider than the check. Rounds 1–2 found the mechanism incomplete and it was fixed; round 3
  found the mechanism sound and the *documentation* overclaiming. Extending C12 until "closed"
  became true would be the same mistake as adding the fourth navigation pattern — chasing a
  word. Newly named as out of scope: HTTP method/form semantics (all GET), non-rendered API
  calls, external redirect destinations.

`scripts/prove-controls.sh` is now 16/16 and is the runnable proof for every control named here.

**The question this round is whether the claim and the check now MATCH** — not whether the
check covers everything. If they match, that is a PASS even with named residue; a bounded,
declared gap is a different condition from an undiscovered one. If they still do not match, say
precisely which sentence overclaims and what it should say instead.

**Do not assume those fixes are adequate — judging that is this round's job.**

**You CAN run commands now.** The sandbox restriction that blocked earlier rounds is lifted —
its root cause was Codex's Windows restricted-token sandbox (spawn denied, unlink denied, write
allowed). **Run the loop. Report what you observed. Do not report results you did not run.**

## What changed and why

Four consecutive review rounds each found the same class of defect: **coverage that reads wider
than it is.** Three of the four were the same gap (G1, route existence). The old detector scanned
source for navigation *forms* — `href="/x"`, then `fetch("/x")`, then `router.push("/x…")` — and
each round found the next form it could not see. The fourth found `<Link href={d.href}>`.

The ruling was: **do not add another pattern.** Enumerating navigation forms is not a design that
can be completed. AST extraction with dataflow was explicitly **rejected** as the same
uncompletable enumeration in better clothes — you still choose which patterns count, and wrapper
components and computed values defeat it identically.

**The replacement is `scripts/route-exercise.mjs` (C12): start the built app, authenticate, fetch
every command-centre page, and request every internal link the pages actually rendered.** The
question moves from *what forms did we scan for* to *what did the surface emit*.

The old static check is kept, renamed, and demoted to a tripwire (C9) because it is the only
cover for `router.push` inside a client event handler, which never reaches rendered HTML.

## Scope of this review

**The navigation layer only.** The ruling was explicit that a narrow finding is not licence to
rebuild a sound apparatus. Import provenance, the delta mechanism, auth coverage and the positive
controls were all judged sound and are **not** in scope unless C12 broke them.

Read:
- `scripts/route-exercise.mjs` — the new check
- `scripts/handoff-loop.sh` — how it is gated (section 7b)
- `dashboard/__tests__/command-centre-readonly.test.ts` — the demoted C9 tripwire
- `docs/HARNESS-COVERAGE-MAP-2026-08-01.md` — C12, G1 closure, stated non-coverage

## THE PRIMARY QUESTION

**Is C12 a design, or is it the same reactive patching in a new medium?**

The previous round's diagnosis was that regex form-scanning "is not a design that can be
completed". Runtime exercising is supposed to be different in kind, not just in mechanism.
**Test that claim rather than accepting it.**

- What class of broken navigation still passes C12? Name it concretely.
- C12 measures *what rendered on this run*. Links behind an unrendered branch — an error state, a
  populated-data state, a role the probe session does not have — are not exercised. Is that a
  bounded, statable limit, or is it the same open-ended enumeration wearing new clothes?
- The declared non-coverage is: client-handler navigation, unrendered branches, external links,
  `/_next` assets. **Is that list complete?** What is missing from it?
- C12 depends on a minted session cookie and a built app. What happens to its verdict if either
  is subtly wrong — and does it fail loud or fail green?

## Verify the claimed proof yourself

The commit claims a side-by-side on one planted defect: a `DECKS` entry pointing at a
non-existent route, reached via `<Link href={d.href}>`, where C9 passed 27 tests and C12 failed
naming the route.

**Reproduce it.** Plant the defect, run both, then revert it. If it does not reproduce, that is
the finding.

## Judge the two controls

C12 carries two, both added after they caught real false-greens in its first hour:

1. **Session accepted** — a rejected cookie would redirect every page to login; the run would
   exercise the login page and report success. Entry page must be 200 or it is a hard stop.
2. **Port not already in use** — the first version orphaned its `next start` on Windows, and a
   later run attached to that stale server and measured the *previous build*, reporting a planted
   defect absent.

**Judge:** are these sufficient? Is there a third false-green shape neither covers — and would you
know from reading the script, or only by running it?

## The loop

```
bash scripts/prove-controls.sh                   -> expect 16/16, exit 0
node scripts/route-exercise.mjs --self-test-redirects -> expect 3 PASS, exit 0
bash scripts/handoff-loop.sh                    -> expect pass=8 fail=0 READY
node scripts/route-exercise.mjs                 -> expect exit 0
node scripts/route-exercise.mjs --plant-broken-link  -> expect exit 1 (control)
cd dashboard && npx vitest run __tests__/command-centre-readonly.test.ts   -> 27 passed
cd dashboard && npx vitest run __tests__/command-centre-auth-coverage.test.ts -> 7 passed
```

`handoff-loop.sh` needs env in the shell only — never write `.env.local`, it is a fenced path:

```
PI_CEO_URL=https://x.invalid PI_CEO_PASSWORD=x \
NEXT_PUBLIC_SUPABASE_URL=https://lksfwktwtmyznckodsau.supabase.co \
NEXT_PUBLIC_SUPABASE_ANON_KEY=x SUPABASE_SERVICE_ROLE_KEY=x \
bash scripts/handoff-loop.sh
```

If a command fails, paste the failure. **Silence, timeout or an unrun command is not a pass.**

## Report — two axes, kept separate

### Axis 1 — Standards
JS/Node practice in `route-exercise.mjs`: process handling, error handling, async correctness,
resource cleanup. Cite lines. Hard violations vs judgement calls. Under 400 words.

### Axis 2 — Spec
Does C12 close G1? Is its declared non-coverage accurate and complete? Are the controls
sufficient? Did closing G1 weaken anything else? Under 400 words.

## Verdict

End with exactly one line: `VERDICT: PASS` or `VERDICT: FAIL — <one-line reason>`
