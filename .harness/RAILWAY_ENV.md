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
- `TELEGRAM_BOT_TOKEN` — Telegram bot for alerts
- `TELEGRAM_ALERT_CHAT_ID` — Telegram chat ID for CI failure alerts
- `TELEGRAM_WEBHOOK_SECRET` — Telegram webhook auth secret
- `MORNING_INTEL_SECRET` — morning intel webhook secret (falls back to WEBHOOK_SECRET)
- `ANTHROPIC_API_KEY` — Claude API key
