# Improvement Proposal: Deployment

**Generated:** 2026-07-01  
**Source:** lessons.jsonl — 8 entries (5 warnings)  
**Proposed action:** Create a SKILL.md entry  
**Target:** new skill file: `skills/DEPLOYMENT.md`

## Recurring Lessons (8 occurrences)

- ⚠️ **[architecture-review]** Railway terminates TLS and proxies requests. Do NOT add TrustedHostMiddleware restricting to 127.0.0.1 — it blocks all cloud traffic. Use ALLOWED_ORIGINS for CORS control instead.
- ℹ️ **[anthropic-refresh-loop]** Anthropic docs URLs (docs.claude.com) redirect to platform.claude.com and code.claude.com. Any httpx fetcher must set follow_redirects=True. Filename collisions can occur if URLs are keyed by last path segment alone — use two-segment extraction or full URL hash.
- ℹ️ **[marathon-session]** Telegram push from any sandboxed Python environment needs only TELEGRAM_BOT_TOKEN + a chat_id (first entry in ALLOWED_USERS works). Full python-telegram-bot package is NOT required — urllib + POST to api.telegram.org/bot{token}/sendMessage is sufficient. See scripts/send_telegram.py.
- ⚠️ **[RA-1043-1049-review]** The claude CLI sets ANTHROPIC_API_KEY="" in the parent shell env as a security measure. Any service launched from that shell (telegram-bot, Python SDKs) inherits the empty string and sends it as x-api-key, causing HTTP 401. Fix: call os.environ.pop("ANTHROPIC_API_KEY", None) before delegating to the Claude SDK when no valid key is configured so the subprocess picks up its own OAuth tokens.
- ⚠️ **[sprint-12-review]** GitHub Actions dependency-review-action@v4 fails with 'Dependency review is not supported on this repository' when the repo's Dependency Graph is not yet indexed. This is not a package license/vulnerability issue — it is a repo configuration issue. Fix: enable vulnerability alerts via 'gh api repos/OWNER/REPO/vulnerability-alerts -X PUT'. Interim: add continue-on-error: true to the job so it doesn't block merges while the graph indexes. NPM Audit + Trivy provide equivalent coverage.
- 🔴 **[sprint-12-review]** A stale Vercel project rootDirectory config (e.g. 'apps/web' set from a monorepo that was later flattened) causes build failures with 'directory not found'. The UI setting is unreliable for clearing this. Use the Vercel API: PATCH /v9/projects/{projectId} with body {"rootDirectory": null} and header Authorization: Bearer <token>. Get projectId from .vercel/project.json in the repo.
- ℹ️ **[sprint-12-review]** Before trying to merge a PR, always check branch protection required status checks: 'gh api repos/OWNER/REPO/branches/main/protection --jq .required_status_checks'. A failing CI job that is NOT in the required_status_checks list does not block the merge. Only checks listed there are gates. Dependency Review, E2E tests, and accessibility tests are typically advisory-only.
- ⚠️ **[sprint-12-review]** A macOS LaunchAgent plist that launches cloudflared must explicitly include the tunnel subcommand args: ['cloudflared', 'tunnel', 'run', '<tunnel-name>']. Without the 'tunnel run <name>' args, cloudflared starts but does not route any traffic — the service appears running but the tunnel is inactive. After editing the plist, reload with: launchctl unload ~/Library/LaunchAgents/<label>.plist && launchctl load ~/Library/LaunchAgents/<label>.plist.

## Proposed Content

Add a new skill or expand an existing one covering these deployment patterns:

```markdown
# SKILL: Deployment Best Practices

## When to apply
Whenever code touches deployment-related logic.

## Rules
- Railway terminates TLS and proxies requests. Do NOT add TrustedHostMiddleware restricting to 127.0.0.1 — it blocks all cloud traffic. Use ALLOWED_ORIGINS for CORS control instead.
- Anthropic docs URLs (docs.claude.com) redirect to platform.claude.com and code.claude.com. Any httpx fetcher must set follow_redirects=True. Filename collisions can occur if URLs are keyed by last path segment alone — use two-segment extraction or full URL hash.
- Telegram push from any sandboxed Python environment needs only TELEGRAM_BOT_TOKEN + a chat_id (first entry in ALLOWED_USERS works). Full python-telegram-bot package is NOT required — urllib + POST to api.telegram.org/bot{token}/sendMessage is sufficient. See scripts/send_telegram.py.
- The claude CLI sets ANTHROPIC_API_KEY="" in the parent shell env as a security measure. Any service launched from that shell (telegram-bot, Python SDKs) inherits the empty string and sends it as x-api-key, causing HTTP 401. Fix: call os.environ.pop("ANTHROPIC_API_KEY", None) before delegating to the Claude SDK when no valid key is configured so the subprocess picks up its own OAuth tokens.
- GitHub Actions dependency-review-action@v4 fails with 'Dependency review is not supported on this repository' when the repo's Dependency Graph is not yet indexed. This is not a package license/vulnerability issue — it is a repo configuration issue. Fix: enable vulnerability alerts via 'gh api repos/OWNER/REPO/vulnerability-alerts -X PUT'. Interim: add continue-on-error: true to the job so it doesn't block merges while the graph indexes. NPM Audit + Trivy provide equivalent coverage.
- A stale Vercel project rootDirectory config (e.g. 'apps/web' set from a monorepo that was later flattened) causes build failures with 'directory not found'. The UI setting is unreliable for clearing this. Use the Vercel API: PATCH /v9/projects/{projectId} with body {"rootDirectory": null} and header Authorization: Bearer <token>. Get projectId from .vercel/project.json in the repo.
- Before trying to merge a PR, always check branch protection required status checks: 'gh api repos/OWNER/REPO/branches/main/protection --jq .required_status_checks'. A failing CI job that is NOT in the required_status_checks list does not block the merge. Only checks listed there are gates. Dependency Review, E2E tests, and accessibility tests are typically advisory-only.
- A macOS LaunchAgent plist that launches cloudflared must explicitly include the tunnel subcommand args: ['cloudflared', 'tunnel', 'run', '<tunnel-name>']. Without the 'tunnel run <name>' args, cloudflared starts but does not route any traffic — the service appears running but the tunnel is inactive. After editing the plist, reload with: launchctl unload ~/Library/LaunchAgents/<label>.plist && launchctl load ~/Library/LaunchAgents/<label>.plist.
```

## Review Required

This proposal was auto-generated. A human must review and apply it.
Close this Linear ticket when applied or explicitly rejected.