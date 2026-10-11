> Moved from SKILL.md. Read when creating, editing or reviewing a manifest under .harness/env-manifests/.

## Manifest format

`Pi-Dev-Ops/.harness/env-manifests/{project-slug}.json`:

```json
{
  "version": "1.0",
  "generated_at": "2026-05-02T07:30:00Z",
  "vercel_team": "unite-group",
  "vercel_project_id": "prj_AbCdEf123",
  "project_slug": "restoreassist",
  "vars": [
    {
      "name": "ANTHROPIC_API_KEY",
      "target": "production",
      "category": "ai-provider",
      "criticality": "blocker"
    },
    {
      "name": "DATABASE_URL",
      "target": "production",
      "category": "database",
      "criticality": "blocker"
    },
    {
      "name": "STRIPE_SECRET_KEY",
      "target": "production",
      "category": "payments",
      "criticality": "blocker"
    },
    {
      "name": "NEXT_PUBLIC_SUPABASE_URL",
      "target": "production",
      "category": "client-public",
      "criticality": "skip"
    }
  ],
  "skipped": [
    "DASHBOARD_PASSWORD",
    "TAO_PASSWORD",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "PLAUSIBLE_*",
    "POSTHOG_*",
    "NEXT_PUBLIC_*"
  ]
}
```

### Field semantics

| Field | Allowed values | Effect |
|---|---|---|
| `category` | `ai-provider`, `database`, `payments`, `observability`, `analytics`, `client-public`, `dashboard-only`, `telegram-only`, `unknown` | Drives default skipped behaviour + auth-failure routing |
| `criticality` | `blocker`, `degraded`, `optional`, `skip` | `blocker` failure → halt all in-flight runs; `degraded` → continue + alert; `optional` → silent fallback; `skip` → never injected |
| `target` | `production`, `preview`, `development` | Which Vercel target to pull from. Default `production` for autonomy runs. |
