# Handoff — Telegram rotation, standing state as of 2026-08-03

**Filed in `docs/` deliberately.** The handoff of record was `.harness/handoff.md`, and `.harness/`
is no longer tracked (see Fix 3). Anything written there is local-only and will not survive a fresh
clone. `.harness/handoff.md` on this machine is still the April 2026 version and is stale.

Companion record: [`INCIDENT-2026-08-03-telegram-bot-takeover.md`](./INCIDENT-2026-08-03-telegram-bot-takeover.md).

**Rotation is PARKED, not finished — deliberately, and it is safe to leave.** The exposed token is
revoked and therefore useless; consumers still holding it fail closed with 401 rather than doing
anything dangerous. Nothing here is urgent. Do not treat the remaining consumers as an incident.

---

## Bot

`@piceoagent_bot`, id `8630069375`. Taken over by a third party while the token was public; display
name changed to "BEST CASINO MINI-APP @Xstakerobot", webhook repointed to `ssh.inkognit.org:8443`
(`82.131.65.219`), privacy mode disabled, inline mode enabled. Full detail in the incident record.

## Rotated and PROVEN

| consumer | evidence |
|---|---|
| **Old token — dead** | `getMe` → **401 Unauthorized**; `getWebhookInfo` → 401. Observed, not inferred. |
| **GitHub Actions** (`CleanExpo/Pi-Dev-Ops`) | secret `updatedAt` moved `2026-04-17T02:38:52Z` → **`2026-08-02T21:02:51Z`**; briefing dispatched on `main` returned Telegram **message id 1909** (run `30767108643`). |

Actions is a single repo-level secret, so that one update covers **all six** token-consuming
workflows: `morning_briefing` (proven), `fable_canary_check`, `sandbox-framework-drift`,
`smoke_pipeline`, `dns_takeover_scan`, `workspace_intel_brief`. `ci.yml` is a false positive — it
names the token only in a comment saying it is deliberately absent from CI.

The proof rested on three legs, and all three held: the credential demonstrably changed (metadata,
no value handled), the old one demonstrably dead (401), and the send chain fail-closed
(`send_telegram.py` raises on `HTTPError` at `:189` and on `ok:false` at `:192`, returns Telegram's
own id at `:194`; `morning_briefing.main()` returns 1 on exception at `:182` under `sys.exit`).

⚠️ Pre-existing, unrelated to rotation: `fable_canary_check.yml:33-37` records that it alone wired
`TELEGRAM_CHAT_ID` from a `TELEGRAM_ALERT_CHAT_ID` secret **that does not exist**. If that job
misbehaves it is a config bug, not the rotation.

## Still holding the DEAD token

| consumer | state | notes |
|---|---|---|
| **Vercel `pi-dev-ops`** | `TELEGRAM_BOT_TOKEN` **not updated — 118d old** | Verified across all three per-scope listings (`production`/`preview`/`development`): one row, all scopes, unchanged. Not a wrong-scope save. |
| **Railway** | **unverified** | Backend running the autonomy poller and bot process. Unreachable from this machine. |
| **n8n — RA-649, RA-826** | not updated | Held as an n8n **environment variable** read via `process.env`, per `RA-649-IMPORT-INSTRUCTIONS.md`, not an n8n credential object. |

**Vercel is ONE project, not two.** An earlier note said `pi-dev-ops` + `dashboard`; there is no
Vercel project named `dashboard` in the `unite-group` team, and `dashboard-unite-group.vercel.app`
404s at root. The `dashboard.json` env-manifest (generated 2026-05-02) is stale.

`/api/telegram` in production is served by **`pi-dev-ops`**, established from route behaviour rather
than the domain: `POST` returns **403** there and **404** on `dashboard-unite-group`, `carsi-web`,
`synthex.social`. The control matters — `POST /api/zzz-nonexistent` on the same host returns **200**,
so a 403 is not a generic response, it is the real guarded handler. See Fix 2.

### What IS set on Vercel `pi-dev-ops`

`TELEGRAM_WEBHOOK_SECRET` was created 2026-08-02 (~21:07Z) on Development, Preview and Production.

Two things about it are **unproven and should not be assumed**:

- **Binding.** The serving deployment is `dpl_FtgTm3hzX4h64Zre5nDpAG6ZRVEt`, created
  `2026-08-02T21:12:55Z`, holding the production aliases. Sampled at one instant, the variable and
  the deployment both read the same minute, and the Vercel CLI (50.13.2) gives env vars
  minute-granularity only with no `--json` for `env ls`. **Ordering could not be established.**
- **Observability.** `route.ts:389-390` returns 403 for all three cases — secret unset, header
  absent, or mismatch. Binding is externally indistinguishable, the same limitation the prior
  incident recorded as `kill_switch_secret: INFERRED BOUND, NOT OBSERVED`.

To settle both: **redeploy once.** The variable is unambiguously older than now, so any deployment
created now provably postdates it.

## THE open question — webhook state

**Unresolved and ranked above everything else here.**

After revocation the old token returns 401 on `getWebhookInfo`. That is the instrument refusing to
answer — **not** an observation that the attacker's registration was removed. Webhooks are
**bot-level** state, not token-level. If `/revoke` did not clear it, Telegram may still be
delivering updates to `ssh.inkognit.org` under the NEW token.

**Check with the new token:** `getWebhookInfo` → expect empty `url`, or the Vercel URL. If it still
shows `ssh.inkognit.org`, call `deleteWebhook`, then re-register **with `secret_token` set**.

Free side-channel: if n8n RA-649 returns **409 Conflict** on `getUpdates` once its token is updated,
a webhook is still registered — Telegram forbids polling while one exists. RA-649 has been broken
since the hijack for exactly this reason, and its silence was a symptom nobody read.

## Consumer order when resuming

1. **Vercel `pi-dev-ops`** — set `TELEGRAM_BOT_TOKEN`, then redeploy (a variable set without a
   redeploy does not rebind a running deployment). Recovers outbound replies.
2. **Railway** — set, then restart the service. Recovers poller alerts and watchdogs. CLI is
   unusable here; use the dashboard.
3. **n8n RA-826** — simple env var.
4. **n8n RA-649** — last, on purpose: it is the webhook canary above.

Expected everywhere until updated: `Telegram HTTP 401: Unauthorized`. Real faults look different —
**409** means a webhook is still registered; **404** means malformed token; **chat not found** means
a `TELEGRAM_ALLOWED_USERS` / `TELEGRAM_CHAT_ID` mismatch (`TELEGRAM_ALLOWED_USERS` is still
2026-04-17, correctly untouched — it is chat ids, not a credential); **401 persisting after an
update** means the store did not take or a stale deployment is serving.

---

## Three fixes identified and NOT made

### Fix 1 — the `analyze` Telegram send is fail-open

`dashboard/app/api/analyze/route.ts:39-47`:

```js
async function sendTelegramMessage(...): Promise<void> {
  try { await fetch(`https://api.telegram.org/bot${botToken}/sendMessage`, {...});
  } catch { /* non-critical */ }
}
```

It never reads the response, never returns a `message_id`, and swallows every error. A 401 and a
success are indistinguishable from outside.

**Consequence:** this is the only non-`setWebhook` outbound Telegram path in the deployed dashboard,
so **Vercel has no fail-closed send** and cannot be proven the way Actions was. Leg three of the
proof has no instrument there. Fix: check `res.ok`, read `result.message_id`, throw otherwise —
mirroring `scripts/send_telegram.py`. Worth doing independently of the rotation.

(`/api/analyze` is in `PROTECTED_API_PREFIXES`, `proxy.ts:54`, so it needs a session regardless.)

### Fix 2 — catch-all returns 200 for arbitrary `/api/*` paths

`POST https://pi-dev-ops.vercel.app/api/zzz-nonexistent` → **200**. An unknown API path should 404.
A 200 masks a missing or unrouted handler and makes any "does this route exist" inference by status
code unreliable. Found as a control while establishing which project serves `/api/telegram`; it did
not invalidate that result (403 ≠ 200), but it would invalidate a less careful one.

### Fix 3 — the incident convention stopped propagating

Every prior incident was appended to `.harness/incidents.jsonl`. **`.harness/` is untracked** on
`main` (#607) and on `feat/command-centre-migration` (`2deac32c`), so that file is no longer
committed and incident records stopped travelling. Same for `.harness/handoff.md`.

Untracking `.harness/` was correct — it made the scanner's exclusion premise true again. The
oversight is that two live conventions lived inside the directory that was untracked, and nothing
flagged it. The incident record and this handoff are both in `docs/` for that reason. **The
convention needs a tracked home and a pointer left behind.**

---

## Deliberately NOT started

Parked by instruction; recorded so the state is not carried in anyone's memory.

- **The queue** — 156-finding triage with the encoding fix, Linear reconciliation, reviewer
  isolation proposal.
- **The branch merge.** `feat/command-centre-migration` is **65 behind / 75 ahead** of `main`, merge
  base `9f3be6ec`. `git merge-tree` reports **13 conflicting files**. **Merge, not rebase** — main
  took three squash merges (#605, #607, #608) so the branch's commits share no ancestry; a rebase
  re-raises the same conflicts across all 75 commits, a merge resolves each once. Five conflicts are
  `add/add` (the squash signature); for most, **main's version is the one to take** — notably
  `dashboard/__tests__/kill-switch-auth.test.ts`, where main already replaced the hardcoded literals
  with `randomBytes(24).toString("hex")`. The exception is `skills/control-design/SKILL.md`, where
  the branch holds two rule sections main lacks and a genuine union is needed.
- **Main's red CI.** At `2a0ec492`: **Prove-It Evals**, **Smoke Test**, **Linear Evidence Audit**.
  Prove-It Evals broke at `b2d56e1a` (#607), Smoke Test at `62f56512` (#605) — both from the
  exclusion-precondition work. Neither the secrets-check fixture nor the Skills Drift Check is among
  main's red: main's secrets check **passes**, and `skills-drift-check.yml` does not exist on main.
