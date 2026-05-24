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
