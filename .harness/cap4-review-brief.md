# Review brief — capability 4, providers (read-only half) — ROUND 1

You are reviewing a code change. **Flag findings. Do not fix anything. Do not write code. Do not
edit, create or delete any file in the repository.**

Round 1 of 3 against this spec. You can execute commands — run the loop and report what you
observed. Do not report results you did not run.

## What this capability is, and what deliberately is not here

The source app's providers deck has three surfaces. **Only the read-only one is ported.**

- **PORTED** — `provider-usage`: which provider keys are PRESENT in the environment, and quota
  signals derived from that. Metadata only; no key value is read.
- **OMITTED, absent not stubbed — `provider-test` (KI-006).** Its whole function is to spend:
  `executeChat` posts to `api.openai.com`, `api.minimax.io`, `openrouter.ai` and
  `generativelanguage.googleapis.com` with a resolved key. Founder ruling: there is no version
  that is a button with a gate — here it becomes a spend path reachable over HTTP by anything
  holding the shared dashboard password, on a surface the fence cannot observe.
- **OMITTED, absent not stubbed — `provider-accounts` (KI-007).** Credential custody, deferred
  and bound to per-capability tokens. This app is single-operator behind one shared password:
  no per-capability scoping, no audit of which capability read which key, no identity to
  attribute a read to.

**Do not report either omission as a defect.** **Do** report a dangling reference, a broken
control, or anything that makes the surface claim a capability it does not have.

## Files, and how each is declared

| File | Category | Claim |
|---|---|---|
| `lib/command-centre/provider-usage.ts` | ported | byte-identical to baseline; pure, zero imports |
| `components/command-centre/provider-usage/ProviderUsageCockpit.tsx` | ported | diff vs baseline is exactly two alias rewrites |
| `app/api/command-centre/provider-usage/route.ts` | **rebuilt** | source `getUser` has no equivalent here |
| `app/(main)/command-centre/providers/page.tsx` | **rebuilt** | source composes 3 tiles, 1 is ported |

Baseline: `D:/Authority-Site/apps/web/src`. Provenance: `dashboard/__tests__/command-centre-provenance.json`.

## THE NAMED REVIEW ITEM — verify these three claims independently

**1. The vault claim.** `provider-accounts`'s route header says "metadata only — never the key …
no secrets cross this boundary." A header comment is an assertion. I traced it instead:
`credentials_vault` appears nowhere in `lib/provider-pool/repository.ts`; the GET path runs
`listAccounts` + `loadAccounts`, which select only from `provider_accounts` and
`provider_quota_events`; `vault_entry_id` is carried as an id and never dereferenced.

**Check that tracing.** If the metadata path reaches the vault by any route I missed — a helper,
a view, an RPC, a trigger — that is the finding. Also judge my conclusion that it *still* does
not port on the same terms, because the same module carries `.insert()` into
`provider_quota_events` and probes `process.env` provider keys via `hasEnvKey`.

**2. The rebuilt route is genuinely read-only and leaks nothing.**
`app/api/command-centre/provider-usage/route.ts` reads `process.env` for provider-key
**presence**. Judge: can any key VALUE reach the response? Consider the payload shape from
`buildProviderCockpit`, the error path, and what `readProviderSignalsFromEnv` puts in the
signals. This route's whole safety story is "presence, never value" — test that claim.

**3. The port fidelity claims.** Verify both, do not take them from this table:
```
diff D:/Authority-Site/apps/web/src/lib/command-centre/provider-usage.ts \
     D:/Pi-Dev-Ops/dashboard/lib/command-centre/provider-usage.ts
diff D:/Authority-Site/apps/web/src/components/command-centre/provider-usage/ProviderUsageCockpit.tsx \
     D:/Pi-Dev-Ops/dashboard/components/command-centre/provider-usage/ProviderUsageCockpit.tsx
```

## Also judge

- **The page.** It is rebuilt and states in its footer what is absent and why. Is that the right
  call versus rendering disabled controls? Is anything on it a control that claims a capability
  the app does not have (the KI-002/KI-005 rule)?
- **The auth suite change.** It had a hard-coded list of four pages; a page added later would
  have been unprotected AND unnoticed. It now discovers pages from the route tree. Is the
  discovery correct — route groups, dynamic segments, nested routes? Is its positive control
  sufficient?
- **Governing instruction: port faithfully, including existing behaviour.** A difference from
  the source is a defect whether or not the source's behaviour is ideal.

## The loop

```
bash scripts/prove-controls.sh                                                 -> 18/18, exit 0
PI_CEO_URL=https://x.invalid PI_CEO_PASSWORD=x \
NEXT_PUBLIC_SUPABASE_URL=https://lksfwktwtmyznckodsau.supabase.co \
NEXT_PUBLIC_SUPABASE_ANON_KEY=x SUPABASE_SERVICE_ROLE_KEY=x \
bash scripts/handoff-loop.sh                                                   -> pass=8 fail=0
node scripts/route-exercise.mjs                                                -> exit 0, 5 pages
cd dashboard && npx vitest run __tests__/command-centre-readonly.test.ts       -> 27 passed
cd dashboard && npx vitest run __tests__/command-centre-auth-coverage.test.ts  -> 9 passed
```

Never write `.env.local` — it is a fenced path; env goes in the shell only. If a command fails,
paste the failure. **Silence, timeout or an unrun command is not a pass.**

## Report — two axes, kept separate

### Axis 1 — Standards
TypeScript/React/Next.js App Router practice in the new files. Cite the hunk. Hard violations vs
judgement calls. Skip what the compiler or linter enforces. Under 400 words.

### Axis 2 — Spec
Requirements unmet; behaviour not asked for; requirements implemented incorrectly; whether the
three named claims hold. Quote the diff. Under 400 words.

## Verdict

End with exactly one line: `VERDICT: PASS` or `VERDICT: FAIL — <one-line reason>`
