> Moved from SKILL.md. Read when wiring or debugging auth-failure detection and the cfo_alert escalation.

## Auth-failure detection (CFO-bot integration)

After every Sandcastle run, the runner inspects `log_tail` for these patterns:

```
401 Unauthorized
403 Forbidden
Invalid API key
Authentication failed
authentication_error
permission_denied
```

If found AND the run consumed any var with `criticality: "blocker"`:

1. `audit_emit.row("cfo_alert", ..., alert_type="env_var_auth_failed", project_slug=..., var_name=NAME)` — name only, never value.
2. `draft_review.post_draft(draft_text=f"🚨 Auth failure on {project_slug}: {var_name} likely rotated", drafted_by_role="CFO", ...)` — Telegram alert.
3. Set in-memory escalation lock: no new Sandcastle runs against that project until manifest review.

The lock auto-expires after 1 hour OR when the operator manually clears it via Telegram `/sandcastle clear-lock {project_slug}`.
