# Rotation prep — INC-TELEGRAM-ANON-EXFIL (prepared, NOT executed)

Every caller enumerated first, so what breaks is known before anything changes.

## TELEGRAM_BOT_TOKEN — recommend ROTATE

**Why.** The token was set and functional throughout the 117-day exposure. An anonymous
caller could drive the bot and have `send()` deliver output using this token. The token
value itself was never returned in a response, but its *effects* were available to anyone,
and log retention cannot establish whether that happened. **Cannot-determine plus a live
fail-open is a rotation, not a wait.**

**Holders (8 workflows + 4 env manifests + the route):**
- `.github/workflows/` — ci, dns_takeover_scan, fable_canary_check, fence-drift-check,
  morning_briefing, sandbox-framework-drift, smoke_pipeline, workspace_intel_brief
- `.harness/env-manifests/` — carsi-web, ccw-crm-web, dashboard, disaster-recovery
- `dashboard/app/api/telegram/route.ts` (outbound `send()`)
- Vercel production env (`pi-dev-ops`)

**What breaks on rotation:** every workflow that sends a Telegram alert fails silently-ish
until its secret is updated — including `secrets_check.py`'s CRITICAL alert path, which is a
security notifier. That is the sharp edge: rotating the token temporarily blinds the alarm
that would tell us about the next secret exposure.

**Procedure (founder-executed):**
1. BotFather → `/mybots` → select bot → *API Token* → **Revoke current token**. Revocation is
   immediate; the old token stops working at once.
2. Update **GitHub Actions org/repo secret** `TELEGRAM_BOT_TOKEN` first — this is what the 8
   workflows read. Doing this first minimises the window where alerting is dead.
3. Update **Vercel production** for `pi-dev-ops`:
   `vercel env rm TELEGRAM_BOT_TOKEN production` then `vercel env add TELEGRAM_BOT_TOKEN production`
4. Update the 4 `.harness/env-manifests/*.json` consumers if they carry values rather than names.
5. **Redeploy** — env binds per-deployment; the running deployment keeps the old token until
   a new build. This is the same trap that made the telegram env-only mitigation useless.
6. Re-point the webhook with the new token AND set `TELEGRAM_WEBHOOK_SECRET` at the same time:
   `setWebhook` with `secret_token` — the route is fail-closed and will refuse everything until
   this is done. **The bot is inert until both are set.** That is intended.

## PI_CEO_PASSWORD — recommend ROTATE, with reasoning

**The case against:** its value was never echoed. No response body contained it. An attacker
driving the telegram bot got *the output of privileged calls*, not the credential.

**The case for, which I judge stronger:**

1. **The blast radius is the whole dashboard-to-upstream trust boundary.** It is the bearer
   token for every `/api/pi-ceo/*` proxy call, kill-switch, curator-proposals, swarm-status,
   zte, and the login secret resolution path. Anything an anonymous caller could reach through
   those routes was reached *with this credential's authority*.
2. **`/status` returned upstream state to an attacker-chosen chat.** We cannot enumerate what
   that output contained across 117 days, and one plausible content is configuration detail
   that narrows guessing the credential itself.
3. **Cannot-determine is the deciding fact.** Log retention is hours against a 117-day window.
   The estate's own standard is that a null result from a check that cannot see is not
   evidence of absence. Declining to rotate would be treating "no evidence of theft" as
   "evidence of no theft" — the exact inversion this session has been correcting all day.
4. **Rotation cost is low and bounded** relative to the alternative of carrying an unknown.

**Holders (12 files):** `.github/workflows/ci.yml`, `app/server/routes/health.py`,
`dashboard/app/(main)/builds/page.tsx`, `dashboard/app/api/auth/login/route.ts`,
`dashboard/app/api/curator-proposals/route.ts`, `dashboard/app/api/kill-switch/route.ts`,
`dashboard/app/api/pi-ceo/[...path]/route.ts`, `dashboard/app/api/swarm-status/route.ts`,
`dashboard/app/api/telegram/route.ts`, `dashboard/app/api/zte/route.ts`,
`dashboard/lib/auth-secret.ts`, `dashboard/next.config.ts`
Plus: Railway (upstream side — it must accept the new value), Vercel production.

**What breaks on rotation, and this one is not trivial:**
- `lib/auth-secret.ts` resolves `DASHBOARD_PASSWORD || PI_CEO_PASSWORD`. If `PI_CEO_PASSWORD` is
  the effective session-signing secret, rotating it **invalidates every live `pi_session`
  cookie** — every logged-in session drops. Acceptable, but know it before, not after.
- Upstream (Railway) and dashboard (Vercel) must be updated **together**; between the two
  updates every proxied call 401s. Plan a short window.
- Redeploy required on both sides. Env binds per-deployment.

**Order:** Railway upstream accepts new value → Vercel updated → redeploy → verify a proxied
route returns non-401 → then retire the old value upstream.

## NOT recommended for rotation

`KILL_SWITCH_SECRET` — created today, after the exposure, never present during it.
