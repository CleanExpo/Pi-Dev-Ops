# Review brief — HTTP hardening — ROUND 3 (FINAL)

You are reviewing a security change. **Flag findings. Do not fix anything. Do not write code.
Do not edit, create or delete any file in the repository.**

**Round 3 of 3 — the last attempt under the standing bound.** You can execute commands. Run the
loop and report what you observed; do not report results you did not run.

**Being last is not a reason to pass.** A FAIL naming a real defect is a better outcome than a
PASS that ends the round. Do not grade on effort, and do not manufacture an objection to appear
rigorous — if it is sound, say so plainly.

**Round 2 returned** `FAIL — required scripts/prove-controls.sh failed 17/22 and the shared
session verifier still uses non-constant-time HMAC comparison.` Both accepted and fixed:

1. **Non-constant-time comparison.** `auth-secret.ts` compared `expectedHex === sig`, and
   consolidation had just made that the *single* comparison guarding both `proxy.ts` and
   `/api/kill-switch`. Replaced with a constant-time compare, pure JS so it works from either
   runtime. **Judge whether the replacement is actually constant-time**, including the
   length-inequality early return.
2. **`prove-controls.sh` depended on build state it never established.** You got 17/22 from the
   same tree that gave me 22/22 — five C12 controls were reporting a stale build rather than the
   thing under test. It now detects a stale build and builds. **Expect 23/23.**

**New since round 2, and in scope:**
- `session-verifier-single-source.test.ts` — asserts every session-verification caller resolves
  to one module, recognising a local implementation by what it *does* rather than by name.
- `.github/workflows/kill-switch-proof.yml` — proves the kill switch *accepts* a valid
  credential (400-with / 401-without), with the secret bound to a GitHub Environment, a
  negative-control job that fails if the secret is readable without declaring it, and a standing
  job asserting the deployment branch policy still permits only `main`.

**Judge the kill-switch proof design specifically.** Its claim is that `400` proves acceptance
because auth runs before op validation, which runs before any upstream call. **Verify that
ordering in the deployed handler.** If a correct secret with `op=probe` could reach upstream, the
workflow is unsafe and that is a blocking finding.

**LIVE CONTEXT:** the telegram and kill-switch guards are deployed and verified closed on
production — `POST /api/telegram` without a secret returns 403, `POST /api/kill-switch?op=probe`
without a credential returns 401, and with a *wrong* credential also 401. The exposure ran 117
days and log retention cannot establish whether it was abused. This is not hypothetical.

## What changed

Four defects on unauthenticated inbound edges, plus one structural check.

1. **`/api/kill-switch` POST had no inbound authentication.** The path was in neither
   `PROTECTED_API_PREFIXES` nor `PUBLIC_API_PREFIXES` in `proxy.ts`, so `proxy()` never
   examined it — and the route attaches `Authorization: Bearer PI_CEO_PASSWORD` to its own
   upstream call, so the caller needed no credential. An anonymous POST could kill the swarm or
   **resume** automation that had been deliberately stopped. Now requires a `pi_session` cookie
   or `X-Kill-Switch-Secret`, fail-closed. `GET ?op=status` stays public (read-only, rejects
   other ops with 400, and a CI smoke surface calls it unauthenticated by design).

2. **`/api/telegram` failed open.** The check fired only when a secret was configured AND
   presented AND mismatched — so **omitting the header skipped it entirely**. Now fail-closed
   with a constant-time compare.

3. **`isAuthorized(chatId)` in the same handler also failed open** (`if (!allowed) return true`).
   Now fail-closed: unconfigured means nobody, not everybody.

4. **`/api/curator-proposals` returned the upstream body wholesale** on a public, unauthenticated
   surface reached with `PI_CEO_PASSWORD`. Now fails closed on an unexpected key.

5. **Structural:** every API route must be classified — matched by a proxy prefix, or declared in
   `__tests__/api-auth-classification.json` with a reason and an anonymous-caller status. An
   unclassified route fails.

## THE LOAD-BEARING CLAIMS — verify these independently

**1. `/api/kill-switch` POST is now unreachable without a credential, and GET is still safe.**
Judge: can any request reach the kill/resume path without a valid session or the correct secret?
Consider cookie parsing (`pi_session` extraction), header casing, the fail-closed branch when
`KILL_SWITCH_SECRET` is unset, and whether `GET` can be induced to mutate. `verifySessionToken`
moved into `lib/auth-secret.ts` and is now shared with `proxy.ts` — **check the two verifiers
still agree**, because that module exists precisely because two callers once diverged.

**2. The telegram webhook cannot be reached by omitting a header.** That was the original
defect. Judge the new guard for any remaining path to the handler: empty strings, whitespace,
casing, `trim()` behaviour, and whether `timingSafeEqual` over digests can throw or be bypassed.

**3. The forensic claim about what the pre-fix telegram route could do.** I claim: with
`TELEGRAM_CHAT_ID` unset, an anonymous forged POST could supply its own `chat.id`, execute
commands, and have `send()` deliver output **to the attacker** — `/status` reaches upstream with
credentials, making it exfiltration rather than spoofing. With it set, an attacker could still
forge inbound commands to the owner's chat and reach `HISTORY.delete(chatId)`.
**Check that reading of the pre-fix control flow.** If it overstates or understates, say so —
this severity assessment is recorded and will be cited.

**4. The three public reads cannot widen silently.** `zte` and `swarm-status` project into named
fields; `curator-proposals` fails closed on an unexpected key. Judge whether a widened upstream
payload can still reach an anonymous caller by any route — nested objects, arrays of objects,
error branches, headers.

**5. Nothing was made LESS available than intended.** These fixes deliberately trade availability
for safety: the headless kill path is unavailable until `KILL_SWITCH_SECRET` is set, and the
Telegram bot is inert until `TELEGRAM_WEBHOOK_SECRET` and `TELEGRAM_CHAT_ID` are set. Judge
whether any fix breaks a path that was legitimate — in particular the CI smoke surfaces in
`.github/smoke-surfaces.json`, which assert specific statuses for these routes unauthenticated.

## Also judge

- Do the new tests actually detect the defects they describe, or only their symptoms? Each was
  proven red by reverting the fix; **reproduce at least one** of those reversions yourself.
- Is `timingSafeEqual` over sha256 digests the right comparison here, given both inputs are
  attacker-influenced in length?
- Does the classification check have a hole — a route shape it would not discover?

## The loop

```
bash scripts/prove-controls.sh                                                  -> 23/23, exit 0
cd dashboard && npx vitest run __tests__/session-verifier-single-source.test.ts  -> 4 passed
cd dashboard && npx vitest run __tests__/security-fix-contracts.test.ts         -> 7 passed
PI_CEO_URL=https://x.invalid PI_CEO_PASSWORD=x \
NEXT_PUBLIC_SUPABASE_URL=https://lksfwktwtmyznckodsau.supabase.co \
NEXT_PUBLIC_SUPABASE_ANON_KEY=x SUPABASE_SERVICE_ROLE_KEY=x \
bash scripts/handoff-loop.sh                                                    -> pass=8 fail=0
cd dashboard && npx vitest run __tests__/kill-switch-auth.test.ts               -> 8 passed
cd dashboard && npx vitest run __tests__/telegram-webhook-auth.test.ts          -> 7 passed
cd dashboard && npx vitest run __tests__/public-read-shape.test.ts              -> 5 passed
cd dashboard && npx vitest run __tests__/api-auth-classification.test.ts        -> 5 passed
```

Never write `.env.local` — it is a fenced path; env goes in the shell only. If a command fails,
paste the failure. **Silence, timeout or an unrun command is not a pass.**

## Report — two axes, kept separate

### Axis 1 — Standards
TypeScript/Node practice in the changed files: comparison safety, error handling, header and
cookie parsing, async correctness. Cite the line. Under 400 words.

### Axis 2 — Spec
Are the five load-bearing claims true? Is any inbound edge still forgeable? Did any fix break a
legitimate path? Under 400 words.

## Verdict

End with exactly one line: `VERDICT: PASS` or `VERDICT: FAIL — <one-line reason>`
