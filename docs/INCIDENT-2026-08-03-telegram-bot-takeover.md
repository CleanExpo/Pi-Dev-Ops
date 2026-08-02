# INC-TELEGRAM-BOT-TAKEOVER — 2026-08-03

**Class:** security-incident · **Blast radius:** high · **Status:** token revoked; consumers not yet updated; webhook state unverified

**This is a SECOND compromise, not a continuation of `INC-TELEGRAM-ANON-EXFIL`.** That incident
was an unauthenticated inbound *route* (`POST /api/telegram` accepted anonymous requests). It was
verified closed on production 2026-08-02 at commit `8fd7fdfa`, and that closure holds. This one is
**credential theft leading to bot takeover**: the bot token itself was committed to the repository
and taken. Closing the route locked a door the attacker already had the key to. The two share a
credential and nothing else — different vector, different fix, independent timelines.

## What was exposed

`TELEGRAM_BOT_TOKEN` for **`@piceoagent_bot`** (bot id `8630069375`), committed in cleartext at
`.harness/n8n-workflows/RA-649-IMPORT-INSTRUCTIONS.md:15` as a value in an operator setup table.

It survived undetected because `scripts/secrets_check.py` lists `".harness/"` in
`_SKIP_PATH_PREFIXES` and therefore **cannot return a finding for any file under it**. Proven
2026-08-03 with a two-arm canary — identical `AKIA`-shaped value, directory the only variable:
DETECTED in `docs/`, MISSED in `.harness/`. Every historic `[PASS]` was silent about this file by
construction, not by luck.

## For how long

| event | date |
|---|---|
| bot token created | ~2026-04-07 (Vercel var age 118d, corroborates the prior incident's 117d) |
| **token committed to the repo** | **2026-04-13** (`24c0597b`) |
| `.harness/` mass-committed by an `autogit` Stop hook, 98MB to a PUBLIC repo | 2026-06-16 (per #607) |
| repo made private | 2026-08-02/03 |
| token revoked via BotFather | 2026-08-03 (verified: `getMe` → 401) |

**Committed and reachable for ~111 days.** The repository was demonstrably public from at least
2026-06-16 until 2026-08-02 (documented in #607). Whether it was public for the earlier window
2026-04-13 → 2026-06-16 is **not established** — GitHub does not expose visibility history via the
API and no local record covers it. Treat the full 111 days as exposed absent contrary evidence.

## Confirmed abuse — this resolves a prior CANNOT DETERMINE

`INC-TELEGRAM-ANON-EXFIL-CLOSED` recorded:

> `abuse_determination: CANNOT DETERMINE. Vercel runtime logs queryable at 6h, time out at 7d,
> ExceedsBillingLimitError at 30d. Hours of retention against a 117-day window.`

That question is now **answered: abuse occurred.** Not from logs — from the bot's own state, which
has no retention limit. Observed read-only before revocation:

- **Display name changed** to `BEST CASINO MINI-APP @Xstakerobot`. Only a token holder can set this.
- **Webhook repointed** to `https://ssh.inkognit.org:8443/hook/8630069375/6541b2efc2f0a4e83700d9c5dff3b9cc`,
  ip `82.131.65.219`, `allowed_updates` = **all 25 update types**. Not Vercel, not ours.
- **Privacy mode disabled** (`can_read_all_group_messages: true`; the default is off). With privacy
  mode off the bot receives *every* message in any group it belongs to, not only commands.
- **Inline mode enabled** (`supports_inline_queries: true`; default off) — lets the bot be invoked
  from any chat, consistent with the casino branding.

The lesson generalises: **bot state is durable forensic evidence where logs are not.** The prior
incident concluded "cannot determine" after querying only logs. `getMe` and `getWebhookInfo` would
have answered it on 2026-08-02, cost nothing, and required no retention.

## What transited the channel

Everything the estate pushed through this bot, for the exposure window. Inbound was delivered to
`82.131.65.219` rather than to the dashboard, and outbound was sendable by anyone holding the token:

- **Morning briefings** (`morning_briefing.yml`, daily 21:03 UTC): ZTE score, overnight Claude Code
  session summaries, open PRs awaiting merge, Pi-SEO digests.
- **Workspace intel briefs** (`workspace_intel_brief.yml`), **pipeline smoke** and **drift-check**
  alerts (`ci.yml`, `fence-drift-check.yml`, `sandbox-framework-drift.yml`, `dns_takeover_scan.yml`,
  `fable_canary_check.yml`, `smoke_pipeline.yml`).
- **`scripts/secrets_check.py` CRITICAL alerts** — the secret-exposure alarm itself routed through
  the compromised bot.
- **One briefing sent 2026-08-03 during this investigation** (message id 1908), dispatched on the
  stated premise that rotation had already occurred. It had not. See "Process failure" below.

RA-649's command interface uses `getUpdates` polling, which returns 409 whenever a webhook is set —
so that workflow has been non-functional since the attacker installed theirs. Its silence was a
symptom that was never read as one.

## Consumer inventory

| consumer | holds this bot's token | state | how established (no values pulled) |
|---|---|---|---|
| GitHub Actions, `CleanExpo/Pi-Dev-Ops` | yes | **stale** | `gh secret list` → `updatedAt 2026-04-17` |
| Vercel `pi-dev-ops`, production | yes | **stale** | `vercel env ls` → created 118d ago |
| Vercel `dashboard`, production | yes | **stale** | env-manifest `vars[]`, repo `CleanExpo/Pi-Dev-Ops` |
| Railway (backend, bot process) | presumed yes | **UNVERIFIED** | CLI fails TLS (`UnknownIssuer`, rustls ignores `SSL_CERT_FILE`); API rejects CLI session token |
| n8n — RA-649, RA-826 | yes | **stale** | import instructions set it as an n8n **env var** read via `process.env`; the specified value is the compromised one |
| Vercel carsi-web, ccw-crm-web, disaster-recovery, restoreassist, synthex, unite-group-ops | **no** | n/a | name appears only in each manifest's static `skipped` exclusion list, not in `vars[]` |

Manifests were generated 2026-05-02 and are three months stale; a variable added since would not
appear. Post-revocation, any consumer still holding the old token now fails with 401 — that failure
is a **detector**, and its absence would mean a consumer was updated.

## What remains unknown

- **Whether the webhook registration is gone.** After revocation the old token returns 401 on
  `getWebhookInfo`, which is the instrument refusing to answer — *not* an observation that the
  registration was removed. Webhooks are bot-level state, not token-level. **Must be checked with
  the new token**; if `ssh.inkognit.org` is still registered, call `deleteWebhook` and re-register
  with a `secret_token`.
- **Which groups/chats the bot was in, and what was read there.** Telegram exposes no API listing a
  bot's chats. Inbound updates were the only signal and they went to the attacker. Structurally
  unknowable from here.
- **Commands, description and short-description** as the attacker left them — requires the new token
  (`getMyCommands`, `getMyDescription`, `getMyShortDescription`, `getMyName`).
- **When the takeover began** within the 111-day window, and whether the repo was public before
  2026-06-16.
- **Whether anything was sent *as* the bot** to real users — no retention covers it.
- **Whether other credentials in the same 111-day public window were also taken.**
  `.harness/pii_test_corpus.jsonl` is a labelled synthetic fixture, but the full 608-file
  `.harness/` tree was never scanned by an instrument that could see it until 2026-08-03.

## Process failure

Two, both worth keeping:

1. **A blind instrument reported clean for 111 days.** `secrets_check.py` excluded `.harness/` on
   the stated ground that it was "not committed" while git tracked 608 files under it. The
   exclusion's premise was false and nothing asserted it until #605. Filed as the canary-placement
   rule in `skills/control-design/SKILL.md`.
2. **"It works" was accepted as "it is ours".** A briefing was sent through this bot to prove the
   channel, before establishing that the token had changed. The test could not distinguish *our new
   token works* from *the attacker's token works* — the exact instrument-blindness the same skill
   documents. **Establish that a credential CHANGED before using it to prove anything.** Metadata
   (`gh secret list` `updatedAt`, `vercel env ls` age) answers it without handling the value.

## Immediate actions

1. ~~Revoke via BotFather~~ — **done, verified 401.**
2. **Verify webhook with the new token; `deleteWebhook` if theirs persists.** Highest priority.
3. Update consumers: GitHub Actions, Vercel `pi-dev-ops` + `dashboard`, Railway, n8n env.
4. Re-register the webhook **with `TELEGRAM_WEBHOOK_SECRET` set**, and set `TELEGRAM_CHAT_ID` —
   both were unset during `INC-TELEGRAM-ANON-EXFIL`.
5. Reset the bot's name, privacy mode (re-enable), and inline mode (disable) in BotFather.
6. Purge or rewrite the token out of git history, or accept it as permanently published.

## Recording gap found while filing this

Every prior incident was appended to `.harness/incidents.jsonl`. **`.harness/` is now untracked** on
`main` (#607) and on this branch, so that file is no longer committed and incident records stopped
propagating. This record is filed in `docs/` for that reason. The convention needs a tracked home.
