# Railway Environment Variables

## Required
- `TAO_PASSWORD` — dashboard auth password
- `LINEAR_API_KEY` — Linear API key
- `WEBHOOK_SECRET` — GitHub webhook HMAC secret
- `LINEAR_WEBHOOK_SECRET` — Linear webhook HMAC secret
- `SUPABASE_URL` — Supabase project URL
- `SUPABASE_SERVICE_ROLE_KEY` — Supabase service role key (quarterly rotation — see SECURITY.md)
- `GITHUB_TOKEN` — GitHub PAT for pushing feature branches
- `GITHUB_REPO` — target GitHub repo (e.g. CleanExpo/Pi-Dev-Ops)

## Performance
- `ENABLE_PROMPT_CACHING_1H=1` — enable 1-hour Anthropic prompt cache (reduces costs up to 90% on repeated sessions)

## Optional / Feature flags
- `TAO_AUTONOMY_ENABLED=1` — enable autonomous Linear issue polling
- `TAO_MACHINE_SHIP_MODE=1` — enable machine spec-pipeline ship gate (judge → STORM → SPM → boardroom → build → PR merge). Default off; required for `pi-dev:machine-ship` tickets.
- `TAO_USE_AGENT_SDK=1` — use Agent SDK (required, must be 1)
- `TAO_SWARM_SHADOW=0` — swarm active mode (set 0 for production)
- `TAO_SWARM_MAX_DAILY_PRS=3` — **operator knob (RA-3019)** — max autonomous PRs the Builder may open per UTC day. Defaults to `3`. Auto-clamped to `SAFE_FALLBACK_MAX_DAILY_PRS=3` regardless of override until `.harness/swarm/green_merge_counter.json` shows `consecutive_green >= 20`. Recommended progression once threshold met: `3 → 5 → 8 → 12`. Raise/lower with `scripts/raise_pr_cap.sh <N>`. Inspect live state via `GET /api/swarm/status` → `pr_quota`.
- `TELEGRAM_BOT_TOKEN` — Telegram bot for alerts
- `TELEGRAM_ALERT_CHAT_ID` — Telegram chat ID for CI failure alerts
- `TELEGRAM_WEBHOOK_SECRET` — Telegram webhook auth secret
- `MORNING_INTEL_SECRET` — morning intel webhook secret (falls back to WEBHOOK_SECRET)
- `ANTHROPIC_API_KEY` — Claude API key

## Pilot V1 (scheduler / dispatcher — ADRs 001-004)
Set these before the `swarm.pilot.scheduler` cron is enabled. The scheduler runs on the existing FastAPI service; `dispatcher.send()` raises `KeyError` at runtime on the first "sent" cycle if the bot vars are missing.
- `PILOT_BOT_TOKEN` — Telegram bot token (BotFather). **Use a SEPARATE bot from `TELEGRAM_BOT_TOKEN`** — pilot suggestions are higher-volume than CI alerts and would otherwise flood the alerts channel.
- `PILOT_BOT_CHAT_ID` — chat ID to send suggestion cards into
- `PILOT_TENANT_SLUG=phill` — tenant identifier; keys `pilot_suggestions.tenant_slug` + feeds the RLS policy (`current_setting('app.current_tenant_slug')`)
- `PILOT_DISABLED=0` — kill switch. Set to `1` to halt the scheduler without a redeploy (verified by `scheduler.run_cycle()` returning `"disabled"`)

---

## Dashboard (Vercel) — security-relevant vars

The dashboard is a separate deployment (`dashboard/vercel.json`); these are its vars, not
Railway's.

- `DASHBOARD_PASSWORD` (or `PI_CEO_PASSWORD`) — signs and verifies the `pi_session` cookie.
  Resolved in one place, `lib/auth-secret.ts`, because two callers once resolved it
  differently and login succeeded while every protected page bounced.
- `KILL_SWITCH_SECRET` — **required for the headless kill path.** `/api/kill-switch` POST
  (`?op=kill|resume`) accepts a valid `pi_session` cookie OR `X-Kill-Switch-Secret` matching
  this value, compared in constant time. It is **fail-closed**: while this is unset, the only
  way to kill or resume is a browser session. Set it so the scripted path exists.
  Generate and set without the value passing through a terminal transcript:

  ```bash
  node -e "console.log(require('crypto').randomBytes(32).toString('hex'))" \
    | vercel env add KILL_SWITCH_SECRET production
  ```

  Callers then send `X-Kill-Switch-Secret: <value>`. Rotate by repeating the command.
- `TELEGRAM_WEBHOOK_SECRET` — **required for the Telegram webhook to accept anything.**
  Fail-closed since 2026-08-02: unset means every inbound POST is refused. Must match the
  `secret_token` given to Telegram's `setWebhook`.
- `TELEGRAM_CHAT_ID` — **required for the bot to answer anyone.** Fail-closed since
  2026-08-02: unset means nobody is authorised, where it previously meant everybody.
