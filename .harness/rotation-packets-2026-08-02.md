# Rotation packets — INC-TELEGRAM-ANON-EXFIL

**PREPARED, NOT EXECUTED.** Two packets with a mandatory gate between them. Packet B does not
start until the gate passes.

---

# PACKET A — `TELEGRAM_BOT_TOKEN`

## Recommendation: ROTATE

The token was set and functional across the entire 117-day exposure. An anonymous caller could
drive the bot and have `send()` deliver output using it. The value was never returned in a
response, but its *effects* were available to anyone who found the endpoint, and log retention
(hours, against 117 days) **cannot establish whether that happened.** Cannot-determine plus a
confirmed live fail-open is a rotation, not a wait.

## Every caller — 13 holders

**GitHub Actions (8 workflows)** — read the org/repo secret:
`ci.yml`, `dns_takeover_scan.yml`, `fable_canary_check.yml`, `fence-drift-check.yml`,
`morning_briefing.yml`, `sandbox-framework-drift.yml`, `smoke_pipeline.yml`,
`workspace_intel_brief.yml`

**Env manifests (4)** — `.harness/env-manifests/`: `carsi-web.json`, `ccw-crm-web.json`,
`dashboard.json`, `disaster-recovery.json`

**Runtime (1)** — `dashboard/app/api/telegram/route.ts`, the outbound `send()`

**Store:** Vercel production (`pi-dev-ops`), plus the GitHub Actions secret.

## Blast radius — and the sharp edge

Rotating this **blinds the alert path during its own rotation.** `scripts/secrets_check.py`
fires its CRITICAL Telegram alert through this token. Between revocation and every consumer
being updated, the estate's *secret-exposure alarm is silent* — the alarm that would tell us
about the next exposure. That is the whole reason the gate below exists.

Also: `morning_briefing`, `workspace_intel_brief` and the drift checks lose their reporting
channel. They will still run and still pass or fail; they simply cannot tell anyone.

## Procedure — founder-executed

1. **BotFather** → `/mybots` → select bot → *API Token* → **Revoke current token**.
   Revocation is immediate; the old token dies at once.
2. **GitHub Actions secret first.** This is what the 8 workflows read, and doing it first
   minimises the window where alerting is dead.
3. **Vercel production:**
   `vercel env rm TELEGRAM_BOT_TOKEN production` then `vercel env add TELEGRAM_BOT_TOKEN production`
4. **The 4 env manifests**, if they carry values rather than names.
5. **REDEPLOY.** Env binds per-deployment; the running deployment keeps the old token until a
   new build. This is the trap that made the telegram env-only mitigation useless.
6. **Re-point the webhook and set `TELEGRAM_WEBHOOK_SECRET` in the same step:** `setWebhook`
   with `secret_token`. The route is fail-closed and refuses everything until this is done, and
   `TELEGRAM_CHAT_ID` must also be set or `isAuthorized` authorises nobody. **The bot is inert
   until all three are set. That is intended, not a fault.**

---

# GATE — prove the notification channel is live again, end to end

**Packet B does not start until this passes.** A channel that went dark must be proven live
again, not assumed. This is the estate's own rule applied to a credential: the first run of a
restored control is the one you have to watch.

**The proof must be end-to-end — a message that actually arrives — not "the token looks set".**

1. **Outbound, from the dashboard runtime:** trigger a path that calls `send()` and confirm the
   message *arrives in the founder's chat*. Arrival is the evidence; a 200 from the Telegram API
   is not, because a valid token can still post to a chat nobody reads.
2. **Outbound, from CI:** run `secrets_check.py` against a planted fake secret in a scratch
   branch (the fixture pattern: generate it, never a literal) and confirm the CRITICAL alert
   **arrives**. This is the specific path that goes dark during rotation, so it is the specific
   path that must be proven back.
3. **Inbound, fail-closed still holding:** re-run the production probe —
   `POST /api/telegram` with no secret must still return **403**. Rotation must not have
   loosened the guard, and a new webhook secret is exactly the moment to check.

**If any of the three fails, stop.** Do not proceed to Packet B with a blind alert channel —
`PI_CEO_PASSWORD` rotation is the larger, riskier operation and it is the one you least want to
run without notifications.

---

# PACKET B — `PI_CEO_PASSWORD`

## Recommendation: ROTATE

**The case against, stated fairly:** the value was never echoed. No response body contained it.
An attacker driving the bot obtained *the output of privileged calls*, not the credential.

**The case for, which I judge stronger:**

1. **It is the bearer token for the entire dashboard-to-upstream trust boundary** — every
   `/api/pi-ceo/*` proxy call, kill-switch, curator-proposals, swarm-status, zte, and the login
   secret resolution path. Everything an anonymous caller reached through those routes was
   reached *with this credential's authority*.
2. **`/status` returned upstream state to an attacker-chosen chat**, and we cannot enumerate what
   that output contained across 117 days. One plausible content is configuration detail that
   narrows guessing the credential.
3. **Cannot-determine is the deciding fact.** Declining to rotate would treat "no evidence of
   theft" as "evidence of no theft" — the precise inversion this session has spent the day
   correcting, and the same shape as a null result from a check that cannot see.
4. **Cost is bounded and known** (below), against an unbounded unknown.

## Every caller — 12 files plus two stores

`.github/workflows/ci.yml`, `app/server/routes/health.py`,
`dashboard/app/(main)/builds/page.tsx`, `dashboard/app/api/auth/login/route.ts`,
`dashboard/app/api/curator-proposals/route.ts`, `dashboard/app/api/kill-switch/route.ts`,
`dashboard/app/api/pi-ceo/[...path]/route.ts`, `dashboard/app/api/swarm-status/route.ts`,
`dashboard/app/api/telegram/route.ts`, `dashboard/app/api/zte/route.ts`,
`dashboard/lib/auth-secret.ts`, `dashboard/next.config.ts`

**Stores:** Railway (upstream — must accept the new value) and Vercel production (dashboard).

## What breaks — stated plainly

- **EVERY LIVE SESSION DROPS.** `lib/auth-secret.ts` resolves
  `DASHBOARD_PASSWORD || PI_CEO_PASSWORD`. If `PI_CEO_PASSWORD` is the effective session-signing
  secret, rotating it **invalidates every `pi_session` cookie in existence** — every logged-in
  browser is signed out mid-session. Not dangerous, but do not discover it afterwards.
- **A window where every proxied call 401s**, between updating upstream and updating the
  dashboard. Unavoidable; keep it short and deliberate.
- **Both sides need a redeploy.** Env binds per-deployment, on Vercel and on Railway.
- **The kill switch's session path breaks until you re-login.** The `X-Kill-Switch-Secret` path
  is unaffected — which is a good argument for having proven that path works first.

## Order

1. Railway upstream accepts the new value.
2. Vercel production updated.
3. **Redeploy both.**
4. Verify a proxied route returns non-401 — observe it, do not infer it.
5. Re-login to the dashboard and confirm a session is issued.
6. Only then retire the old value upstream.

---

## Not for rotation

`KILL_SWITCH_SECRET` — created 2026-08-02, after the exposure, never present during it.
