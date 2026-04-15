# Security Operations

## SUPABASE_SERVICE_ROLE_KEY

**Risk:** Bypasses all Row Level Security (RLS). Full database access.
**Usage:** Scoped to observability writes only (gate_checks, alert_escalations, heartbeat_log, triage_log, workflow_runs, claude_api_costs, notebooklm_health).
**Rotation schedule:** Quarterly (January, April, July, October).
**Rotation procedure:**
1. Generate new service role key in Supabase dashboard → Project Settings → API
2. Update Railway environment variable SUPABASE_SERVICE_ROLE_KEY
3. Verify /health endpoint returns healthy after deploy
4. Revoke old key in Supabase dashboard

## WEBHOOK_SECRET / LINEAR_WEBHOOK_SECRET

**Rotation schedule:** Every 6 months or immediately on suspected compromise.
**Rotation procedure:**
1. Generate new secret (openssl rand -hex 32)
2. Update in GitHub webhook settings for each repo
3. Update Railway environment variable
4. Update Linear webhook settings

## TELEGRAM_WEBHOOK_SECRET

**Rotation schedule:** Every 6 months.
**Procedure:** Regenerate via BotFather, update Railway env var, re-register webhook URL.

## LINEAR_API_KEY

**Rotation schedule:** Annually or on team member departure.
**Procedure:** Generate new Personal API key in Linear settings, update Railway and Claude Desktop MCP config.
